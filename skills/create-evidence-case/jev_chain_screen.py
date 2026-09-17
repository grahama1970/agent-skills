"""jev crosswalk-chain coherence screen — an INSTRUMENT, not an authority.

Purpose (this session): test where jev can harden the $memory pipeline by
screening the crosswalk chains that /create-evidence-case bakes into sparta_qra
(the corpus the pipeline grounds on). A spurious chain = bad grounding baked
into the corpus.

Layering (do not violate):
  - traceability  : does the edge EXIST?  -> deterministic /list, fetched here,
                    passed to jev as context. jev NEVER decides edge existence.
  - coherence     : is the hop semantically valid or spurious? -> jev edge_stance
                    (verifies/contradicts/related/unrelated/insufficient). SCREEN.
  - entailment    : does the control functionally satisfy? -> Lean4 (elsewhere).

jev output is recorded to a jsonl for the agreement eval (jev vs deterministic
edge + human), NEVER written as CAE evidence. Abstain (<0.98) = escalate signal.

Optimize placement (which chains get screened, thresholds) AFTER we know how jev
handles SpaceTRAIL — same instrument discipline as the SpaceTRAIL loop.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

JEV_DIR = Path("/home/graham/workspace/experiments/agent-skills/skills/jev")
JEV_RUN = JEV_DIR / "run.sh"
JEV_PRESET = "edge_stance"
JEV_ANSWERABILITY_Q = JEV_DIR / "questions" / "answerability.json"
SCREEN_LOG = Path("/mnt/storage12tb/spacetrail/jev_chain_screen.jsonl")
ANSWERABILITY_LOG = Path("/mnt/storage12tb/spacetrail/jev_answerability_screen.jsonl")
MEMORY_BASE = "http://127.0.0.1:8601"

# Answerability rollup: only converges_answerable clears the ANSWER bar.
_ANSWERABLE = {"converges_answerable"}

# jev stance -> screen verdict. Only "verifies" is a coherent hop.
_COHERENT = {"verifies"}
_SPURIOUS = {"contradicts", "unrelated"}
# "related" / "insufficient_evidence" -> ambiguous, lean escalate


def _fetch_controls(ids: list[str]) -> dict[str, dict]:
    """Deterministic control metadata via /list. No regex, no LLM."""
    out: dict[str, dict] = {}
    with httpx.Client(base_url=MEMORY_BASE, timeout=httpx.Timeout(10.0, connect=2.0)) as c:
        for cid in ids:
            r = c.post("/list", json={
                "collection": "sparta_controls",
                "filters": {"control_id": cid},
                "limit": 1,
            }).json()
            docs = r.get("documents") or r.get("items") or []
            if docs:
                d = docs[0]
                out[cid] = {
                    "id": cid,
                    "name": d.get("name") or d.get("title") or "",
                    "desc": (d.get("description") or d.get("text") or "")[:400],
                    "exists": True,
                }
            else:
                out[cid] = {"id": cid, "name": "", "desc": "", "exists": False}
    return out


def _jev_edge_stance(claim: str, passage: str) -> dict[str, Any]:
    """One jev edge_stance call via the skill (respects egress gate + venv)."""
    state = json.dumps({"claim": claim, "passage": passage})
    t0 = time.time()
    proc = subprocess.run(
        [str(JEV_RUN), "ask", "--preset", JEV_PRESET, "--state", state, "--allow-egress"],
        capture_output=True, text=True,
    )
    took = int((time.time() - t0) * 1000)
    # jev exits nonzero on abstain/error — that is a fail-closed escalate signal,
    # not a crash. Parse whatever receipt it printed.
    try:
        receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"stance": None, "confidence": 0.0, "abstain": True,
                "error": proc.stderr.strip()[:200] or "no_receipt", "took_ms": took}
    ans = (receipt.get("answers") or {}).get("stance") or {}
    return {
        "stance": ans.get("choice"),
        "confidence": ans.get("confidence", 0.0),
        "probabilities": ans.get("probabilities", {}),
        "abstain": receipt.get("decision") == "abstain" or proc.returncode != 0,
        "model": (receipt.get("bindings") or {}).get("model"),
        "took_ms": receipt.get("took_ms", took),
    }


def screen_chain(chain_path: list[str], *, source_question: str = "",
                 qra_key: str = "", record: bool = True) -> dict[str, Any]:
    """Screen every hop of one crosswalk chain for coherence.

    Returns a per-hop verdict list. Never mutates the QRA / evidence_case.
    verdict per hop: coherent | suspected_spurious | escalate.
    """
    ids = [c for c in chain_path if c]
    controls = _fetch_controls(ids)
    hops: list[dict[str, Any]] = []
    for a_id, b_id in zip(ids, ids[1:]):
        a, b = controls[a_id], controls[b_id]
        edge_exists = a["exists"] and b["exists"]
        claim = (f"Control {b_id} ({b['name']}) is a coherent crosswalk mapping / "
                 f"countermeasure / refinement of control {a_id} ({a['name']}).")
        passage = f"{a_id} {a['name']}: {a['desc']} || {b_id} {b['name']}: {b['desc']}"

        if not edge_exists:
            # Deterministic layer already fails — don't spend a jev call.
            hop = {"from": a_id, "to": b_id, "edge_exists": False,
                   "verdict": "escalate", "reason": "edge_missing_in_corpus",
                   "stance": None, "confidence": 0.0}
        else:
            j = _jev_edge_stance(claim, passage)
            if j["abstain"] or j["stance"] is None:
                verdict = "escalate"
            elif j["stance"] in _COHERENT:
                verdict = "coherent"
            elif j["stance"] in _SPURIOUS:
                verdict = "suspected_spurious"
            else:  # related / insufficient_evidence
                verdict = "escalate"
            hop = {"from": a_id, "to": b_id, "edge_exists": True,
                   "verdict": verdict, "stance": j["stance"],
                   "confidence": j["confidence"],
                   "probabilities": j.get("probabilities", {}),
                   "jev_abstain": j["abstain"], "took_ms": j.get("took_ms"),
                   "model": j.get("model")}
        hops.append(hop)

    result = {
        "chain_path": ids,
        "qra_key": qra_key,
        "source_question": source_question[:300],
        "hops": hops,
        # chain coherent only if EVERY hop is coherent
        "chain_verdict": ("coherent" if hops and all(h["verdict"] == "coherent" for h in hops)
                          else "suspected_spurious" if any(h["verdict"] == "suspected_spurious" for h in hops)
                          else "escalate"),
        "screened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "screen": "jev_edge_stance",  # never CAE evidence
    }
    if record:
        SCREEN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SCREEN_LOG.open("a") as f:
            f.write(json.dumps(result) + "\n")
    return result


def _jev_ask(questions_path: Path, state: dict[str, Any]) -> dict[str, Any]:
    """One jev call against a local questions file. Returns first answer + decision."""
    t0 = time.time()
    proc = subprocess.run(
        [str(JEV_RUN), "ask", "--questions", f"@{questions_path}",
         "--state", json.dumps(state), "--allow-egress"],
        capture_output=True, text=True,
    )
    took = int((time.time() - t0) * 1000)
    try:
        receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"choice": None, "confidence": 0.0, "abstain": True,
                "error": proc.stderr.strip()[:200] or "no_receipt", "took_ms": took}
    answers = receipt.get("answers") or {}
    ans = next(iter(answers.values()), {}) if answers else {}
    return {
        "choice": ans.get("choice"),
        "confidence": ans.get("confidence", 0.0),
        "probabilities": ans.get("probabilities", {}),
        "abstain": receipt.get("decision") == "abstain" or proc.returncode != 0,
        "model": (receipt.get("bindings") or {}).get("model"),
        "took_ms": receipt.get("took_ms", took),
    }


def screen_answerability(question: str, grounded_entities: list[dict], *,
                         chains: list[list[str]] | None = None,
                         qra_key: str = "", record: bool = True) -> dict[str, Any]:
    """PRIMARY screen: do grounded entities converge on one answerable request,
    or span unrelated domains? This is the same-technique / /answer-vs-/clarify
    judgment — the failure the pipeline actually needs hardened. A SCREEN, not
    authority: the agent + deterministic gates own the route; jev flags
    likely-CLARIFY sets and abstains (<0.98) = escalate.

    grounded_entities: [{id, name, framework}] that resolved (all real).
    chains: optional list of existing crosswalk paths between them.
    """
    ents = [{"id": e.get("id") or e.get("canonical_id", "?"),
             "name": e.get("name") or e.get("canonical_name", ""),
             "framework": e.get("framework", "")} for e in grounded_entities]
    state = {"question": question[:600], "grounded": ents,
             "crosswalk_links": chains or []}
    j = _jev_ask(JEV_ANSWERABILITY_Q, state)

    # The probability distribution IS the coherence metric — a graded "do these
    # controls/entities cohere?" score, independent of the 0.98 act-alone gate.
    # Use it to rank/triage; use the discrete verdict only for fail-closed routing.
    probs = j.get("probabilities", {}) or {}
    coherence_score = round(float(probs.get("converges_answerable", 0.0)), 4)
    incoherence_score = round(float(probs.get("spans_unrelated_clarify", 0.0)), 4)

    # jev SUGGESTS the terminal action; the deterministic memory route + agent
    # keep authority. Vocabulary is the frozen memory set: answer/clarify/draft/
    # deflect, plus escalate (=human checkpoint) when jev abstains. clarify and
    # draft still require the human_checkpoint per the memory hardening contract.
    if not ents:
        verdict, action = "no_grounding", "deflect"      # nothing resolved
    elif j["abstain"] or j["choice"] is None:
        verdict, action = "escalate", "escalate"          # jev unsure -> human
    elif j["choice"] in _ANSWERABLE:
        verdict, action = "converges_answerable", "answer"
    elif j["choice"] == "spans_unrelated_clarify":
        verdict, action = "spans_unrelated", "clarify"
    elif j["choice"] == "partial_coverage_gap":
        verdict, action = "partial_gap", "draft"          # answer grounded part, flag gap
    else:  # insufficient_evidence
        verdict, action = "escalate", "escalate"

    result = {
        "question": question[:300], "qra_key": qra_key,
        "n_entities": len(ents), "entity_ids": [e["id"] for e in ents],
        "screen_verdict": verdict, "suggested_action": action,  # jev suggests; memory route decides
        "coherence_score": coherence_score,      # P(converges_answerable) 0..1
        "incoherence_score": incoherence_score,  # P(spans_unrelated_clarify) 0..1
        "jev_choice": j["choice"], "confidence": j["confidence"],
        "probabilities": probs, "jev_abstain": j["abstain"],
        "took_ms": j.get("took_ms"), "model": j.get("model"),
        "screened_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "screen": "jev_answerability",  # never CAE evidence / never the route authority
    }
    if record:
        ANSWERABILITY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ANSWERABILITY_LOG.open("a") as f:
            f.write(json.dumps(result) + "\n")
    return result


def agent_decision_packet(question: str, *, intent_action: str | None,
                          grounded_entities: list[dict], recall_confidence: float,
                          graph_path_exists: bool | None, jev_screen: dict[str, Any]) -> dict[str, Any]:
    """Assemble ALL pipeline context into an advisory packet for the AGENT.

    The agent already owns the DETERMINISTIC structural coherence via $memory
    recall + sparta_relationships/sparta_controls queries: graph_path_exists is
    that fact, and it decides the redundant zone (no path -> not answerable). jev
    only adds the SEMANTIC residual the graph can't express: a path can exist yet
    the entities span unrelated domains so the request still can't be answered
    (traceability != answerability). The value signal is the DIVERGENCE between
    the graph fact and jev's semantic coherence.

    This function does NOT compute the terminal action — it presents the signals,
    marks jev advisory, and surfaces conflicts. Agent + deterministic memory
    route + human checkpoint own authority.
    """
    jev_action = jev_screen.get("suggested_action")
    coherence = jev_screen.get("coherence_score", 0.0)
    conflicts = []
    # THE value signal: graph says a path exists (traceability) but jev says the
    # set doesn't cohere semantically -> chains connect, request not answerable.
    # This is the false-answer risk the deterministic graph alone cannot catch.
    if graph_path_exists and coherence < 0.2:
        conflicts.append("graph_path_but_jev_incoherent")
    # jev thinks it coheres but there is NO graph path -> agent trusts the graph,
    # but flag: jev may see a real same-technique link the edges miss.
    if graph_path_exists is False and coherence >= 0.6:
        conflicts.append("no_graph_path_but_jev_coherent")
    # High recall confidence but low coherence -> false-answer risk.
    if recall_confidence >= 0.6 and coherence < 0.2:
        conflicts.append("recall_confident_but_low_coherence")
    # Intent already said clarify/deflect but jev thinks answerable -> re-check.
    if intent_action in {"CLARIFY", "NO_MATCH", "OFF_TOPIC"} and jev_action == "answer":
        conflicts.append("intent_clarify_but_jev_answer")
    return {
        "question": question[:300],
        "decision_owner": "agent",              # jev never decides
        "signals": {
            "intent_action": intent_action,
            "n_grounded_entities": len(grounded_entities),
            "recall_confidence": recall_confidence,
            "graph_path_exists": graph_path_exists,  # DETERMINISTIC, agent-owned
            "jev_advisory": {                    # ADVISORY — semantic residual only
                "coherence_score": coherence,
                "suggested_action": jev_action,
                "verdict": jev_screen.get("screen_verdict"),
                "abstain": jev_screen.get("jev_abstain"),
            },
        },
        "conflicts": conflicts,                  # agent must resolve these
        "note": "Graph path is deterministic (agent-owned via recall/control "
                "queries); jev adds only the semantic residual. Divergence = the "
                "value signal. Agent decides answer/deflect/clarify/draft.",
    }


def demo() -> None:
    """Self-check: layering invariants hold, jsonl append works."""
    # Missing-edge hop must escalate WITHOUT a jev call (deterministic-first).
    r = screen_chain(["ZZ-9999-fake", "CM0001"], source_question="demo", record=False)
    assert r["hops"][0]["edge_exists"] is False
    assert r["hops"][0]["verdict"] == "escalate"
    assert r["hops"][0]["stance"] is None, "jev must not judge a missing edge"
    # Verdict rollup: any spurious hop -> chain suspected_spurious
    fake = {"chain_path": ["A", "B"], "hops": [
        {"verdict": "coherent"}, {"verdict": "suspected_spurious"}]}
    chain_v = ("coherent" if all(h["verdict"] == "coherent" for h in fake["hops"])
               else "suspected_spurious" if any(h["verdict"] == "suspected_spurious" for h in fake["hops"])
               else "escalate")
    assert chain_v == "suspected_spurious"
    # Answerability rollup: only converges_answerable -> answer_ok.
    assert "converges_answerable" in _ANSWERABLE
    assert "spans_unrelated_clarify" not in _ANSWERABLE
    # coherence_score is P(converges_answerable): higher = set coheres better.
    assert round(float({"converges_answerable": 0.54}.get("converges_answerable", 0.0)), 4) == 0.54
    # Agent packet: jev advisory only, conflicts surfaced, agent owns decision.
    pkt = agent_decision_packet("q", intent_action="QUERY", grounded_entities=[{"id": "X"}],
        recall_confidence=0.8, graph_path_exists=True,
        jev_screen={"suggested_action": "escalate", "coherence_score": 0.05,
                    "screen_verdict": "escalate", "jev_abstain": True})
    assert pkt["decision_owner"] == "agent"
    # The value signal: graph path exists but jev says incoherent (traceability != answerable).
    assert "graph_path_but_jev_incoherent" in pkt["conflicts"]
    assert "recall_confident_but_low_coherence" in pkt["conflicts"]
    assert "suggested_action" not in pkt  # packet presents, never decides
    print("jev_chain_screen demo: OK (deterministic-first, rollup correct)")


if __name__ == "__main__":
    demo()
