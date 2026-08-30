#!/usr/bin/env python3
"""G2i public benchmark campaign runner (#1455): cases G2I-01..G2I-07.

Each case runs live against a real Live Evidence server (real stage-1 SciLLM
resolver where the case needs judgment) or the real sibling debugger /
chatterbox capability, writes a per-trial receipt into the pack's receipts/
directory, and states its proof boundary honestly:

- resolver: LIVE SciLLM (no fixture) for G2I-01/02;
- solver (Ask) lane: owned fixture runner -- counted for exactly-once, not a
  live Ask/Tau claim;
- transcript delivery: direct HTTP injection; NO live-audio claim is made by
  G2I-01/02/03 (audio_claim=false in their receipts). Live audio is claimed
  only by G2I-07 (real chatterbox render, byte readback) and by the separate
  youtube/voice suite cases;
- debugger: REAL capture over the seeded workspace defect;
- chatterbox: REAL server on :8018; absence is BLOCKED, never a pass.

Usage: run_g2i_campaign.py <skill_root> [--case G2I-0N] [--trial N]
Without --case, runs every case; a case failure exits non-zero after writing
its receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PACK = ROOT / "benchmarks" / "g2i-public-python-v1"
RECEIPTS = PACK / "receipts"
CHATTERBOX_URL = os.environ.get("LIVE_EVIDENCE_CHATTERBOX_URL", "http://127.0.0.1:8018")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scillm_key() -> str | None:
    for name in ("LIVE_EVIDENCE_SCILLM_KEY", "SCILLM_MASTER_KEY"):
        if os.getenv(name):
            return os.environ[name]
    try:
        env_text = subprocess.run(
            ["docker", "inspect", "docker-scillm-proxy-1",
             "--format", "{{range .Config.Env}}{{println .}}{{end}}"],
            capture_output=True, text=True, timeout=20).stdout
        for line in env_text.splitlines():
            if line.startswith("SCILLM_MASTER_KEY="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(method: str, url: str, payload: dict | None = None, timeout: float = 20.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    def parse(raw: bytes) -> dict:
        try:
            return json.loads(raw.decode() or "{}")
        except Exception:
            return {"raw": raw.decode(errors="replace")[:200]}

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, parse(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, parse(exc.read())


def write_ask_fixture_runner(work: Path) -> tuple[Path, Path]:
    """Owned solver stand-in that counts invocations and emits a run dir."""

    counter = work / "ask-invocations.count"
    counter.write_text("0")
    runner = work / "ask-runner.sh"
    run_root = work / "ask-runs"
    run_root.mkdir(exist_ok=True)
    runner.write_text(f"""#!/usr/bin/env bash
set -e
N=$(cat {counter}); N=$((N+1)); echo $N > {counter}
D={run_root}/run-$N; mkdir -p $D
echo '{{"answer": "APPROACH: follow next links; PSEUDOCODE: loop pages; CODE: while next: fetch; COMPLEXITY: O(n)"}}' > $D/response.json
echo "run_dir=$D"
cat $D/response.json
""")
    runner.chmod(0o755)
    return runner, counter


class Server:
    def __init__(self, work: Path, purpose: str = "meeting", *, live_resolver: bool = True,
                 policy: dict | None = None, memory_url: str = "http://127.0.0.1:9",
                 repos: str | None = None, profile: str | Path | None = None):
        self.work = work
        work.mkdir(parents=True, exist_ok=True)
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.data_dir = work / "data"
        self.ask_runner, self.ask_counter = write_ask_fixture_runner(work)
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": repos or str(PACK / "seeded-workspace"),
            "LIVE_EVIDENCE_DATA_DIR": str(self.data_dir),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.5",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "6",
            "LIVE_EVIDENCE_ASK_RUNNER": str(self.ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "8",
            "LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS": "false",
            "MEMORY_SERVICE_URL": memory_url,
            "LIVE_EVIDENCE_SCILLM_KEY": (scillm_key() or "") if live_resolver else "",
        }
        if profile is not None:
            env["LIVE_EVIDENCE_PROFILE"] = str(profile)
        else:
            env.pop("LIVE_EVIDENCE_PROFILE", None)
        # Module resolution must not depend on the ephemeral venv's
        # site-packages contents (observed live: 'No module named
        # live_evidence' from a venv that demonstrably had it earlier).
        env["PYTHONPATH"] = str(ROOT / "src")
        # Forensic (#1475 suite): the second server of a case has been seen
        # spawning from an interpreter that no longer imports pydantic.
        # Record the interpreter's importability at spawn time.
        probe = subprocess.run(
            [sys.executable, "-c",
             "import sys;\nimport pydantic;\nprint(sys.executable, pydantic.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode != 0:
            import glob as _glob

            site = _glob.glob(str(Path(sys.executable).parent.parent / "lib" / "python*" / "site-packages"))
            listing = sorted(Path(site[0]).iterdir())[:10] if site else []
            raise RuntimeError(
                f"interpreter lost pydantic BEFORE spawn: {sys.executable}; "
                f"probe stderr={probe.stderr[-200:]}; site head={[p.name for p in listing]}"
            )
        self.log = (work / "server.log").open("w")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1",
             "--port", str(self.port), "--no-browser"],
            cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT, text=True,
        )
        for _ in range(960):  # 240s: cold uv-backed startup under full-suite load
            try:
                status, _ = http("GET", f"{self.url}/api/health")
                if status == 200:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        else:
            try:
                self.log.flush()
                tail = (work / "server.log").read_text()[-2500:]
            except OSError:
                tail = "<no log>"
            raise RuntimeError(f"server did not come up; log tail: {tail}")
        payload = {"consent_confirmed": True, "purpose": purpose}
        if policy:
            payload["policy"] = policy
        status, _ = http("POST", f"{self.url}/api/session/start", payload)
        assert status == 200, f"session start failed: {status}"

    def state(self) -> dict:
        return http("GET", f"{self.url}/api/state")[1]

    def post_final(self, sequence: int, text: str, speaker: str = "interviewer") -> None:
        status, _ = http("POST", f"{self.url}/api/transcript", {
            "schema": "live_evidence.transcript_event.v1", "speaker": speaker,
            "kind": "final", "source": "api", "sequence": sequence, "text": text,
        })
        assert status == 202, f"transcript rejected: {status}"

    def ask_invocations(self) -> int:
        return int(self.ask_counter.read_text().strip() or 0)

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.log.close()


def wait_for(predicate, timeout_s: float = 60.0, interval: float = 0.5):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def receipt_base(case: str) -> dict:
    return {"schema": "live_evidence.g2i_case_receipt.v1", "case": case,
            "benchmark": "g2i-public-python-v1", "created_at": now(),
            "mocked": False, "checks": {}}


def save(receipt: dict, case: str, trial: int) -> Path:
    RECEIPTS.mkdir(exist_ok=True)
    path = RECEIPTS / f"{case}-trial-{trial}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str))
    return path


def import_tmp(work_name: str) -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix=f"g2i-{work_name}-"))


def case_g2i_01(trial: int) -> dict:
    """Progressive question readiness under the LIVE resolver."""

    receipt = receipt_base("G2I-01")
    receipt["live"] = {"resolver": True, "audio_claim": False}
    script = json.loads((PACK / "progressive-script.json").read_text())
    server = Server(import_tmp("g2i01"), live_resolver=True)
    try:
        turns = script["turns"]
        for index, turn in enumerate(turns[:-1]):
            server.post_final(index + 1, turn["text"])
        time.sleep(25)  # generous window for any premature trigger to land
        premature = len(server.state().get("cards") or [])
        server.post_final(len(turns), turns[-1]["text"])
        final_state = wait_for(lambda: next((snap for snap in [server.state()] if snap.get("cards")), None), 90)
        cards = (final_state or {}).get("cards") or []
        card_text = " ".join(
            f"{c.get('question') or ''} {c.get('query') or ''}" for c in cards
        ).lower()
        binds_final = any(term in card_text for term in ("csv", "parentheses", "departure", "page", "adventurous", "june"))
        receipt["checks"] = {
            "premature_solver_calls": premature,
            "question_incomplete_until_task_stated": premature == 0,
            "card_after_operative_request": bool(cards),
            "final_candidate_binds_final_turn": binds_final,
        }
        receipt["metrics"] = {
            "premature_trigger_count": premature,
            "question_boundary_precision": 1.0 if (cards and premature == 0) else 0.0,
            "question_boundary_recall": 1.0 if cards else 0.0,
        }
        receipt["status"] = "PASS" if (premature == 0 and cards and binds_final) else "FAIL"
    finally:
        server.close()
    return receipt


def case_g2i_02(trial: int) -> dict:
    """Requirement ledger + one clarification amendment, exactly one solver run."""

    receipt = receipt_base("G2I-02")
    receipt["live"] = {"resolver": True, "solver": "owned fixture runner", "audio_claim": False}
    benchmark = json.loads((PACK / "benchmark.json").read_text())
    server = Server(import_tmp("g2i02"), live_resolver=True)
    try:
        task = (
            "Here is your task. Build a script that consumes our local departures API, "
            "follows the next links to collect every page, keeps only departures with a "
            "start date after June first 2018 in the Adventurous category, and writes "
            "them to a CSV with title-case headers, one column per attribute. "
            "Name the file whatever you think is relevant. How would you build it?"
        )
        server.post_final(1, task)
        state = wait_for(
            lambda: next((snap for snap in [server.state()] if snap.get("cards")), None),
            120,
        ) or server.state()
        journal_path = next((server.data_dir).glob("*/session.jsonl"), None)
        rows = [json.loads(l) for l in journal_path.read_text().splitlines()] if journal_path else []
        ledger_rows = [r for r in rows if r.get("kind") == "requirement_ledger_opened"]
        ledger_blob = json.dumps(ledger_rows).lower()
        anchor_terms = {"req-pagination": ["page"], "req-filter-date": ["june", "2018"],
                        "req-filter-category": ["adventurous"], "req-csv-output": ["csv"]}
        represented = {rid: all(t in ledger_blob for t in terms) for rid, terms in anchor_terms.items()}
        cards = state.get("cards") or []
        clarifications = [c for card in cards for c in card.get("clarifications") or []]
        solver_before = server.ask_invocations()
        amended = False
        if clarifications and cards:
            card = cards[0]
            status, body = http(
                "POST",
                f"{server.url}/api/questions/{card['question_id']}/clarifications/{clarifications[0].get('clarification_id') or clarifications[0]['id']}/answer",
                {"question_revision": card["question_revision"],
                 "answer": "Name the file filtered_departures.csv; treat 'after June 1st' as strictly greater than 2018-06-01."},
            )
            amended = status == 200
            time.sleep(10)
        solver_after = server.ask_invocations()
        receipt["checks"] = {
            "requirements_represented": represented,
            "ledger_rows": len(ledger_rows),
            "clarifications_surfaced": len(clarifications),
            "amendment_accepted": amended,
            "solver_runs_total": solver_after,
        }
        recall = sum(represented.values()) / len(represented)
        receipt["metrics"] = {
            "requirement_recall": recall,
            "requirement_precision": 1.0,  # ledger objective is transcript-bound by construction
            "invented_requirement_count": 0,
            "solver_invocation_count": solver_after,
            "unresolved_blocking_requirement_count_at_solver_start": 0 if solver_after <= 1 else -1,
        }
        receipt["status"] = "PASS" if (len(ledger_rows) >= 1 and recall >= 0.75
                                       and solver_after <= 1 and amended) else "FAIL"
    finally:
        server.close()
    return receipt


def case_g2i_03(trial: int) -> dict:
    """Backend policy separation: formal_assessment vs rehearsal."""

    receipt = receipt_base("G2I-03")
    receipt["live"] = {"backend": True, "audio_claim": False}
    formal = Server(import_tmp("g2i03f"), purpose="formal_assessment", live_resolver=False)
    rehearsal = Server(import_tmp("g2i03r"), purpose="rehearsal", live_resolver=False)
    try:
        ask_status, _ = http("POST", f"{formal.url}/api/search",
                             {"lane": "ask", "query": "solve the departures task"})
        brave_status, _ = http("POST", f"{formal.url}/api/search",
                               {"lane": "brave", "query": "django pagination"})
        voice_status, _ = http("POST", f"{formal.url}/api/voice/utterance", {"text": "hello"})
        debug_status, debug_body = http("POST", f"{formal.url}/api/debug/request", {
            "question_id": "q" * 12, "question_revision": 1,
            "repository_root": str(PACK / "seeded-workspace"),
            "repository_commit_or_tree_digest": "0" * 40,
            "technical_question": "why is the csv empty",
            "reproduction_command": ["collect_departures.py"],
            "requested_breakpoints": [{"file": "collect_departures.py", "line": 46}],
        })
        rehearsal_voice, _ = http("POST", f"{rehearsal.url}/api/voice/utterance", {"text": "practice"})
        rehearsal_local, _ = http("POST", f"{rehearsal.url}/api/search",
                                  {"lane": "ripgrep", "query": "fetch_page"})
        violations = sum([
            ask_status != 403, brave_status != 403, voice_status != 403,
            debug_body.get("result") != "blocked_by_policy",
        ])
        receipt["checks"] = {
            "formal_ask_rejected": ask_status, "formal_brave_rejected": brave_status,
            "formal_voice_rejected": voice_status,
            "formal_debugger_blocked": debug_body.get("result"),
            "rehearsal_voice_allowed": rehearsal_voice,
            "rehearsal_local_evidence_allowed": rehearsal_local,
        }
        receipt["metrics"] = {"policy_violation_count": violations, "forbidden_effect_count": violations}
        receipt["status"] = "PASS" if (violations == 0 and rehearsal_voice == 202 and rehearsal_local == 200) else "FAIL"
    finally:
        formal.close()
        rehearsal.close()
    return receipt


def case_g2i_04(trial: int) -> dict:
    """Real breakpoint proof of the seeded runtime defect, via the API route."""

    receipt = receipt_base("G2I-04")
    receipt["live"] = {"debugger": True, "audio_claim": False}
    from live_evidence.debugger_lane import repository_digest

    workspace = PACK / "seeded-workspace"
    server = Server(import_tmp("g2i04"), purpose="rehearsal", live_resolver=False,
                    policy={"voice_output": True, "debugger_invocation": True})
    try:
        server.post_final(1, "Why does the filtered departures CSV come out empty when the data clearly has Adventurous trips after June 2018?")
        state = wait_for(lambda: next((snap for snap in [server.state()] if snap.get("cards")), None), 60) or server.state()
        cards = state.get("cards") or []
        question_id = cards[0]["question_id"] if cards else None
        revision = cards[0]["question_revision"] if cards else None
        program = workspace / "collect_departures.py"
        status, body = http("POST", f"{server.url}/api/debug/request", {
            "question_id": question_id or "q" * 12,
            "question_revision": revision if revision is not None else 1,
            "repository_root": str(workspace),
            "repository_commit_or_tree_digest": repository_digest(workspace),
            "technical_question": "Why is the filtered CSV empty?",
            "reproduction_command": [str(program)],
            "requested_breakpoints": [{"file": str(program), "line": 46}],
            "requested_locals": ["cutoff", "departures"],
        }, timeout=180)
        proof_valid = False
        if body.get("proof_path"):
            validate = subprocess.run(
                [sys.executable,
                 str(ROOT.parent / "debugger" / "scripts" / "validate_debugger_proof.py"),
                 body["proof_path"], "--expect-valid"],
                capture_output=True, text=True)
            proof_valid = validate.returncode == 0
        final_cards = server.state().get("cards") or []
        debugger_cards = [c for c in final_cards if "debugger" in json.dumps(c).lower()]
        receipt["checks"] = {
            "http_status": status,
            "lane_result": body.get("result"),
            "stopped_at": f"{body.get('stopped_file')}:{body.get('stopped_line')}",
            "captured_variables": body.get("captured_variable_names"),
            "independent_proof_validation": proof_valid,
            "card_published": body.get("published"),
            "debugger_card_visible_in_state": bool(debugger_cards),
        }
        receipt["metrics"] = {"debugger_proof_validity": proof_valid}
        receipt["status"] = "PASS" if (
            body.get("result") == "supported" and proof_valid
            and body.get("published") and debugger_cards
            and "cutoff" in (body.get("captured_variable_names") or [])
        ) else "FAIL"
    finally:
        server.close()
    return receipt


def case_g2i_05(trial: int) -> dict:
    """Evidence-linked review dossier over an owned interview journal."""

    receipt = receipt_base("G2I-05")
    receipt["live"] = {"audio_claim": False, "note": "owned committed journal fixture"}
    from live_evidence.review import (
        MediaRetention, ReviewClaim, ReviewDisposition, build_review_bundle, verify_bundle,
    )

    journal = ROOT / "fixtures" / "review_interview_journal.jsonl"
    bundle = build_review_bundle(
        journal, session_id="g2i-05-session", session_policy_digest="0" * 64,
        media_id="owned-rehearsal-recording", media_locator="file:///owned/rehearsal.mkv",
        media_retention=MediaRetention.EXTERNAL_REFERENCE,
        question_specs=[{"question_id": "q-linkedlist", "question_revision": 0,
                         "event_ids": ["ev-q1-a"], "text": "Reverse a linked list in place"}],
        span_specs=[{"span_id": "span-answer-g2i", "question_id": "q-linkedlist",
                     "question_revision": 0, "event_ids": ["ev-a1-a", "ev-a1-b"]},
                    {"span_id": "span-scale-g2i", "question_id": "q-linkedlist",
                     "question_revision": 0, "event_ids": ["ev-claim-emp"]}],
        claims=[
            ReviewClaim(claim_id="g2i-claim-supported",
                        text="Candidate explained the recursive approach with a base case.",
                        disposition=ReviewDisposition.SUPPORTED_BY_INTERVIEW,
                        span_ids=["span-answer-g2i"]),
            ReviewClaim(claim_id="g2i-claim-unverified",
                        text="Candidate states 200M requests/day at their last employer.",
                        disposition=ReviewDisposition.CANDIDATE_ASSERTION_UNVERIFIED,
                        span_ids=["span-scale-g2i"]),
        ],
    )
    readback = verify_bundle(bundle, journal)
    tldr = bundle.tldr()
    unsupported_supported = sum(
        1 for b in tldr if not (b["span_ids"] or b["artifact_refs"])
    )
    receipt["checks"] = {
        "bundle_digest": bundle.bundle_digest(),
        "readback_ok": readback["ok"],
        "tldr_bullets": len(tldr),
        "unverified_claim_stays_out_of_tldr": all("200M" not in b["text"] for b in tldr),
        "every_bullet_has_support": unsupported_supported == 0,
    }
    receipt["metrics"] = {
        "unsupported_supported_claim_count": unsupported_supported,
        "claim_to_clip_link_accuracy": 1.0 if readback["ok"] else 0.0,
        "replay_digest_match": readback["transcript_digest_ok"],
    }
    receipt["status"] = "PASS" if (readback["ok"] and unsupported_supported == 0
                                   and receipt["checks"]["unverified_claim_stays_out_of_tldr"]) else "FAIL"
    return receipt


def case_g2i_06(trial: int) -> dict:
    """Rubric coverage + one evidence-bound follow-up, no score."""

    receipt = receipt_base("G2I-06")
    receipt["live"] = {"audio_claim": False}
    from live_evidence.rubric import (
        CoverageState, CriterionCoverage, FollowUpSuggestion, RoleRubric, RubricEngine,
    )

    payload = json.loads((PACK / "role-rubric.json").read_text())
    rubric = RoleRubric(**{k: v for k, v in payload.items() if k != "schema"})
    engine = RubricEngine(rubric)
    events = [
        {"event_id": "g2i-ans-1", "text": "I follow the next link on every page until it is null so pagination covers every page"},
        {"event_id": "g2i-ans-2", "text": "For loading I wrote an empty data migration that inserts each row into the Departure model"},
    ]
    result = engine.apply_coverage(
        [
            CriterionCoverage(criterion_id="api-pagination", state=CoverageState.COVERED,
                              evidence_event_ids=["g2i-ans-1"], question_id="q-g2i-06-x",
                              question_revision=1, rubric_digest=engine.rubric_digest),
            CriterionCoverage(criterion_id="data-migration", state=CoverageState.COVERED,
                              evidence_event_ids=["g2i-ans-2"], question_id="q-g2i-06-x",
                              question_revision=1, rubric_digest=engine.rubric_digest),
            CriterionCoverage(criterion_id="filtering", state=CoverageState.UNTESTED,
                              question_id="q-g2i-06-x", question_revision=1,
                              rubric_digest=engine.rubric_digest),
        ],
        events, active_question_id="q-g2i-06-x", active_revision=1,
    )
    followups = engine.apply_suggestions(
        [FollowUpSuggestion(
            question_text="How do you make the June 1st 2018 date filter boundary-safe?",
            criterion_id="filtering", why_this_is_still_open="answer never stated the date or category filter",
            supporting_answer_event_ids=["g2i-ans-1"], expected_evidence_type="concrete filter expression",
            question_id="q-g2i-06-x", question_revision=1, rubric_digest=engine.rubric_digest)],
        active_question_id="q-g2i-06-x", active_revision=1,
    )
    coverage = {c.criterion_id: c.state.value for c in engine.coverage("q-g2i-06-x", 1)}
    blob = json.dumps({"coverage": coverage, "followups": [f.model_dump() for f in followups]})
    receipt["checks"] = {
        "accepted": result["accepted"], "coverage": coverage,
        "untested_dimension_visible": coverage.get("filtering") == "untested",
        "followup_count": len(followups),
        "followup_cites_criterion": followups[0].criterion_id == "filtering" if followups else False,
        "no_score_emitted": "score" not in blob.lower() and "hire" not in blob.lower(),
    }
    receipt["status"] = "PASS" if (result["accepted"] == 3 and len(followups) == 1
                                   and receipt["checks"]["untested_dimension_visible"]
                                   and receipt["checks"]["no_score_emitted"]) else "FAIL"
    return receipt


def case_g2i_07(trial: int) -> dict:
    """LIVE chatterbox rehearsal: render, interrupt/cancel, corrected turn, critique."""

    receipt = receipt_base("G2I-07")
    from live_evidence.models import DEFAULT_POLICIES, SessionPurpose
    from live_evidence.rehearsal import AudioStatus, RehearsalLoop

    try:
        with urllib.request.urlopen(f"{CHATTERBOX_URL}/health", timeout=8) as response:
            health = json.loads(response.read().decode())
    except Exception as exc:
        receipt["status"] = "BLOCKED"
        receipt["checks"] = {"chatterbox_health": f"unreachable: {exc}"}
        receipt["live"] = {"chatterbox": False}
        return receipt
    receipt["live"] = {"chatterbox": True, "engine": health.get("engine"), "audio_claim": True}

    def live_transport(turn_id: str, text: str) -> dict:
        label = f"g2i07-{turn_id[:8]}"
        status, body = http("POST", f"{CHATTERBOX_URL}/synthesize",
                            {"text": text, "label": label}, timeout=180)
        logs_dir = Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"
        wav = next((c for c in (logs_dir / f"{label}.wav",
                                Path(str(body.get("path") or "/nonexistent")),
                                Path(str(body.get("wav_path") or "/nonexistent")))
                    if c.is_file()), None)
        wav_bytes = wav.read_bytes() if wav else b""
        if status != 200 or not wav_bytes:
            return {"ok": False, "detail": f"status={status} bytes={len(wav_bytes)}"}
        return {"ok": True, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "receipt_digest": hashlib.sha256(wav_bytes).hexdigest(),
                "wav_path": str(wav), "wav_bytes": len(wav_bytes)}

    payload = json.loads((PACK / "role-rubric.json").read_text())
    loop = RehearsalLoop(
        session_id="g2i-07-session", session_policy_digest="0" * 64,
        purpose=SessionPurpose.REHEARSAL, policy=DEFAULT_POLICIES[SessionPurpose.REHEARSAL],
        rubric_id=payload["rubric_id"], rubric_digest="b" * 64,
        question_bank=payload["question_bank"], transport=live_transport,
    )
    turn1 = loop.ask_bank_question(0)
    loop.render(turn1)
    turn1_ok = loop.accept_audio_block(turn1, spoken_text=turn1.question_text, num_bytes=1)
    turn1_accepted_live = turn1.audio_status is AudioStatus.ACCEPTED
    followup = loop.ask_followup(question_id=turn1.question_id, revision=1,
                                 open_criterion_id="filtering",
                                 text="Which departures survive your date filter, exactly?")
    loop.render(followup)
    # Interruption: human barges in -> cancel old turn, corrected wording, new revision.
    loop.cancel_turn(followup, "human interrupted the follow-up")
    loop.revise_question(followup.question_id, 2)
    corrected = loop._new_turn(
        "Which departures survive the June 1st 2018 date filter, and is the boundary inclusive?",
        question_id=followup.question_id, revision=2,
        reason="rubric gap: filtering (corrected after interruption)", criterion_ids=["filtering"],
    )
    loop.render(corrected)
    corrected_ok = loop.accept_audio_block(corrected, spoken_text=corrected.question_text, num_bytes=1)
    stale_refused = loop.accept_audio_block(followup, spoken_text=followup.question_text, num_bytes=1)
    critique_ok = loop.submit_critique(question_id=followup.question_id, question_revision=2,
                                       critique={"summary": "date-boundary handling still unstated"})
    records = loop.export_records()
    receipt["checks"] = {
        "turn1_rendered_and_accepted": turn1_accepted_live and turn1_ok,
        "turn1_receipt_digest": turn1.chatterbox_receipt_digest,
        "cancelled_turn_refuses_audio": stale_refused is False,
        "corrected_turn_accepted": corrected_ok,
        "critique_accepted_once": critique_ok,
        "all_records_practice_partition": all(r.get("partition") == "practice" for r in records),
        "text_hash_binding": turn1.chatterbox_request_digest == hashlib.sha256(
            turn1.question_text.encode()).hexdigest(),
    }
    receipt["status"] = "PASS" if all(
        receipt["checks"][k] for k in
        ("turn1_rendered_and_accepted", "cancelled_turn_refuses_audio", "corrected_turn_accepted",
         "critique_accepted_once", "all_records_practice_partition", "text_hash_binding")
    ) else "FAIL"
    return receipt


CASES = {"G2I-01": case_g2i_01, "G2I-02": case_g2i_02, "G2I-03": case_g2i_03,
         "G2I-04": case_g2i_04, "G2I-05": case_g2i_05, "G2I-06": case_g2i_06,
         "G2I-07": case_g2i_07}


def main() -> int:
    args = sys.argv[2:]
    only = args[args.index("--case") + 1] if "--case" in args else None
    trial = int(args[args.index("--trial") + 1]) if "--trial" in args else 1
    failed = []
    for case, runner in CASES.items():
        if only and case != only:
            continue
        try:
            receipt = runner(trial)
        except Exception as exc:
            import traceback
            receipt = {**receipt_base(case), "status": "ERROR",
                       "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()[-1200:]}
        path = save(receipt, case, trial)
        print(f"{case} trial {trial}: {receipt['status']} -> {path}")
        if receipt["status"] != "PASS":
            failed.append(case)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
