from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project_dream.common import digest_object, sha256_text, write_json
from project_dream.validate_candidate import validate_candidate


def source(id: str, kind: str, authority: str, text: str, *, project_id="agent-skills", **extra):
    data = {"id": id, "kind": kind, "authority": authority, "project_id": project_id, "text": text, "sha256": sha256_text(text), "visibility": "project"}
    data.update(extra)
    return data


def packet(*sources, active_authority="current_code", contradictions=None, max_changed=2):
    doc = {
        "schema_version": "project_dream_evidence_packet.v1",
        "project_id": "agent-skills",
        "run_id": "dream-run-test",
        "input_head": {"generation": 7, "digest": "head-digest"},
        "evidence_refs": list(sources),
        "active_topics": [{"topic_id": "topic-1", "authority": active_authority, "status": "active"}],
        "contradictions": contradictions or [],
        "policy": {"mutation_budget": {"max_changed_topics": max_changed, "max_changed_percent": 100}},
    }
    doc["input_digest"] = digest_object(doc, {"input_digest"})
    return doc


def candidate(pkt, action="REVISE_CANDIDATE", authority="current_code", ref_id="code", ref_sha=None, span=None, **proposal_extra):
    ref = {"id": ref_id}
    if ref_sha:
        ref["sha256"] = ref_sha
    if span:
        ref["span"] = span
    prop = {
        "topic_id": "topic-1",
        "topic_kind": "practice",
        "title": "Use current code",
        "action": action,
        "text": "Current code is authoritative.",
        "retrieval_text": "Current code is authoritative.",
        "claims": [{"text": "Current code is authoritative.", "authority": authority, "confidence": 0.8, "uncertainty": "low", "evidence_refs": [ref]}],
        "expected_head": pkt["input_head"],
    }
    prop.update(proposal_extra)
    return {
        "schema_version": "project_dream_candidate.v1",
        "project_id": pkt["project_id"],
        "run_id": pkt["run_id"],
        "input_digest": pkt["input_digest"],
        "input_head": pkt["input_head"],
        "model": {"provider": "opencode-go", "id": "opencode-go/test-cheap"},
        "prompt": {"id": "consolidate_project_memory.v1", "sha256": "prompt"},
        "policy": {"exclude_from_learning": True, "dream_run_id": pkt["run_id"]},
        "proposals": [prop],
    }


def assert_blocked(receipt, needle):
    assert receipt["status"] == "blocked"
    assert any(needle in err for err in receipt["errors"])


def test_explicit_user_correction_overrides_assistant_assertion():
    pkt = packet(source("user", "session", "explicit_user_decision", "Use Tau, not raw Graph Memory."), active_authority="explicit_user_decision")
    cand = candidate(pkt, authority="assistant_statement", ref_id="user")
    assert_blocked(validate_candidate(pkt, cand), "lower-authority")


def test_current_code_overrides_stale_transcript_prose():
    pkt = packet(source("code", "code", "current_code", "def project_memory_stage(): pass"), active_authority="current_code")
    cand = candidate(pkt, authority="resolved_session_compaction", ref_id="code")
    assert_blocked(validate_candidate(pkt, cand), "lower-authority")


def test_repeated_observations_do_not_outrank_current_code():
    pkt = packet(source("obs", "session", "repeated_session_observation", "Three sessions said the old wrapper worked."), active_authority="current_code")
    cand = candidate(pkt, authority="repeated_session_observation", ref_id="obs")
    assert_blocked(validate_candidate(pkt, cand), "lower-authority")


def test_equal_authority_contradiction_routes_to_human_review():
    pkt = packet(source("code", "code", "current_code", "A"), contradictions=[{"topic_id": "topic-1", "authority": "current_code"}])
    assert_blocked(validate_candidate(pkt, candidate(pkt)), "NEEDS_HUMAN_REVIEW")
    review = candidate(pkt, action="NEEDS_HUMAN_REVIEW")
    assert validate_candidate(pkt, review)["status"] == "accepted"


def test_incremental_code_blocks_absence_deprecation_but_full_reconciliation_can_be_considered():
    inc = source("code", "code", "current_code", "No Foo class here.", coverage_scope="incremental", reconciliation_eligible=False)
    pkt = packet(inc)
    dep = candidate(pkt, action="DEPRECATE_WITH_REPLACEMENT", text="No Foo class exists; delete old topic.", replacement_topic_id="topic-2", replacement_evidence_policy="code lineage")
    assert_blocked(validate_candidate(pkt, dep), "incremental code evidence")

    full = source("code", "code", "current_code", "Full tree has replacement Foo2.", coverage_scope="full", reconciliation_eligible=True)
    pkt2 = packet(full)
    dep2 = candidate(pkt2, action="DEPRECATE_WITH_REPLACEMENT", replacement_topic_id="topic-2", replacement_evidence_policy="code lineage")
    assert validate_candidate(pkt2, dep2)["status"] == "accepted"


def test_deprecated_practice_requires_replacement_and_lineage_evidence():
    pkt = packet(source("code", "code", "current_code", "Replacement exists.", coverage_scope="full", reconciliation_eligible=True))
    dep = candidate(pkt, action="DEPRECATE_WITH_REPLACEMENT")
    assert_blocked(validate_candidate(pkt, dep), "deprecation requires")


def test_stale_but_not_disproved_practice_gets_warning_not_deletion():
    pkt = packet(source("session", "session", "resolved_session_compaction", "Might be stale."), active_authority="resolved_session_compaction")
    stale = candidate(pkt, action="MARK_FRESHNESS_STALE", authority="resolved_session_compaction", ref_id="session")
    receipt = validate_candidate(pkt, stale)
    assert receipt["status"] == "accepted"
    assert receipt["warnings"]


def test_hash_mutation_cross_project_self_citation_secret_and_mutation_budget_block():
    pkt = packet(source("code", "code", "current_code", "safe"), max_changed=0)
    assert_blocked(validate_candidate(pkt, candidate(pkt, ref_sha="bad")), "hash mismatch")
    pkt_cross = packet(source("other", "session", "current_code", "foreign", project_id="other"))
    assert_blocked(validate_candidate(pkt_cross, candidate(pkt_cross, ref_id="other")), "cross-project")
    assert_blocked(validate_candidate(pkt, candidate(pkt, ref_id="candidate:self")), "recursively cites")
    secret = candidate(pkt)
    secret["proposals"][0]["text"] = "api_key=abcd1234abcd1234"
    assert_blocked(validate_candidate(pkt, secret), "secret-like")
    assert_blocked(validate_candidate(pkt, candidate(pkt)), "mutation budget exceeded")


def test_malformed_synthesis_retains_raw_and_rejects(tmp_path):
    pkt = packet(source("code", "code", "current_code", "safe"))
    packet_path = tmp_path / "packet.json"
    write_json(packet_path, pkt)
    spec = {"argv": [sys.executable, "-c", "print('prose before json but no candidate')"]}
    spec_path = tmp_path / "spec.json"
    write_json(spec_path, spec)
    out = tmp_path / "candidate.json"
    proc = subprocess.run([str(ROOT / "run.sh"), "synthesize", "--packet", str(packet_path), "--model", "opencode-go/test-cheap", "--output", str(out), "--command-spec", str(spec_path), "--json"], text=True, stdout=subprocess.PIPE)
    assert proc.returncode == 1
    assert not out.exists()
    assert (tmp_path / "candidate.json.raw-output.txt").exists()


def test_synthesis_cache_reuses_only_matching_hashes(tmp_path):
    pkt = packet(source("code", "code", "current_code", "safe"))
    packet_path = tmp_path / "packet.json"
    write_json(packet_path, pkt)
    cand = candidate(pkt)
    spec = {"argv": [sys.executable, "-c", "import json, os; open(os.environ['PROJECT_DREAM_OUTPUT'], 'w').write(json.dumps(%r))" % cand]}
    spec_path = tmp_path / "spec.json"
    write_json(spec_path, spec)
    cache = tmp_path / "cache"
    out1 = tmp_path / "one.json"
    out2 = tmp_path / "two.json"
    base = [str(ROOT / "run.sh"), "synthesize", "--packet", str(packet_path), "--model", "opencode-go/test-cheap", "--command-spec", str(spec_path), "--cache-dir", str(cache), "--json"]
    assert subprocess.run(base + ["--output", str(out1)]).returncode == 0
    proc = subprocess.run(base + ["--output", str(out2)], text=True, stdout=subprocess.PIPE)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["cache_hit"] is True


def test_stage_reads_back_refs_and_blocks_head_changes(tmp_path):
    pkt = packet(source("code", "code", "current_code", "safe"))
    cand = candidate(pkt)
    validation = validate_candidate(pkt, cand)
    candidate_path = tmp_path / "candidate.json"
    validation_path = tmp_path / "validation.json"
    memory = tmp_path / "memory.sh"
    write_json(candidate_path, cand)
    write_json(validation_path, validation)
    memory.write_text("#!/usr/bin/env bash\necho '{\"head_before\":{\"generation\":7},\"head_after\":{\"generation\":7},\"candidate_ref\":\"staged\"}'\n")
    memory.chmod(0o755)
    env = os.environ.copy()
    env["PROJECT_DREAM_MEMORY_RUN"] = str(memory)
    proc = subprocess.run([str(ROOT / "run.sh"), "stage-candidate", "--candidate", str(candidate_path), "--validation", str(validation_path), "--json"], env=env, text=True, stdout=subprocess.PIPE)
    assert proc.returncode == 0
    receipt = json.loads(proc.stdout)
    assert receipt["active_head_unchanged"] is True
    assert receipt["candidate_digest"] == digest_object(cand)
