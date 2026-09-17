"""Play-task entry for the sparta-stress-hardener workflowScript.

Exact contract of the workflowScript play task:
  python3 -m sparta_stress_test.hardener_run --persona P --seed S --run-dir W --endpoints BASE

Deterministic small bank per (persona, seed): real corpus controls + fabricated
controls; runs each through run_single (REAL /intent -> /answer -> /clarify ->
/deflect via pipeline_client) and writes results.jsonl into the run dir.

MULTI-TURN (wave 1): for CLARIFY results the persona simulates the human
answer to the clarifying question and the follow-up turn goes back through the
REAL pipeline; for held/ungrounded answers the REAL /draft product is invoked
and the persona simulates the human signoff checkpoint (accept/amend/reject)
via /draft/signoff. The persona NEVER grades correctness.

Persona model: cheap/low-effort LLM via the scillm proxy (never a HIGH-effort
frontier model in the measured persona role). On 429 the runner switches to
the next fallback in PERSONA_MODELS and records the switch.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from .runner import run_single

PERSONA_MODELS = [  # cheap -> cheaper; first available wins, 429 advances
    ("claude-haiku-4-5-20251001", "low"),
    ("gemini-3-flash", "low"),
]


def _scillm_key() -> str:
    # master keys first; the dev-default SCILLM_PROXY_KEY is rejected when the
    # proxy has a real key override configured, so try it last.
    for k in ("SCILLM_MASTER_KEY", "LITELLM_MASTER_KEY"):
        if os.environ.get(k):
            return os.environ[k]
    # the running proxy container's own master key (localhost only)
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "inspect", "docker-scillm-proxy-1", "--format",
             "{{range .Config.Env}}{{println .}}{{end}}"],
            capture_output=True, text=True, timeout=15).stdout
        for line in out.splitlines():
            if line.startswith("SCILLM_MASTER_KEY="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return os.environ.get("SCILLM_PROXY_KEY", "")


def persona_llm(messages: list[dict], state: dict) -> str:
    """Cheap persona completion with 429 fallback across PERSONA_MODELS."""
    key = _scillm_key()
    models = PERSONA_MODELS[state.get("model_idx", 0):]
    last_err = None
    for i, (model, effort) in enumerate(models):
        body = json.dumps({"model": model, "reasoning_effort": effort,
                           "messages": messages}).encode()
        req = urllib.request.Request(
            "http://localhost:4001/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {key}", "X-Caller-Skill": "scillm",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            state["model"], state["effort"] = model, effort
            state["model_idx"] = state.get("model_idx", 0) + i
            return d["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            last_err = f"{model}: HTTP {e.code} {e.read()[:200]}"
            if e.code == 429:
                state.setdefault("fallbacks", []).append(
                    {"from_model": model, "reason": "429", "at": time.time()})
                continue  # try next fallback
            raise
    raise RuntimeError(f"persona_llm exhausted models: {last_err}")


def _post_local(path: str, payload: dict) -> dict:
    base = os.environ.get("SPARTA_ENDPOINTS", "http://127.0.0.1:8601")
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


PERSONA_BIOS = {
    "jennifer_cheung": (
        "You role-play Jennifer Cheung, a hands-on spacecraft GNC engineer. "
        "Practical, skeptical, wants actionable countermeasures. Answer as the "
        "human user would. NEVER grade or evaluate the system's correctness."),
}


def persona_turn(persona: str, history: list[dict], instruction: str, state: dict) -> str:
    msgs = ([{"role": "system", "content": PERSONA_BIOS.get(persona, PERSONA_BIOS["jennifer_cheung"])}]
            + history + [{"role": "user", "content": instruction}])
    return persona_llm(msgs, state).strip()


def multiturn_followup(q: dict, r: dict, state: dict) -> dict:
    """Persona-simulated human checkpoints after run_single. Returns a trace dict."""
    trace = {"question": r["question_text"], "persona": q.get("persona"),
             "single_turn_action": r["actual_action"], "checkpoint": None,
             "turns": [], "model": None, "effort": None}
    persona = q.get("persona", "jennifer_cheung")
    action = r["actual_action"]
    guidance = ""
    for t in r.get("turns", []):
        if t.get("role") == "assistant":
            guidance = t.get("content", "")
            break

    if action == "CLARIFY":
        try:
            cl = _post_local("/clarify", {"q": r["question_text"], "scope": "sparta"})
            guidance = cl.get("final_response") or cl.get("clarifying_question") or ""
        except Exception as e:
            guidance = ""
            trace["turns"].append({"role": "clarify_error", "error": str(e)[:200]})
    if action == "CLARIFY" and guidance:
        # Human checkpoint: answer the clarifying question in character.
        reply = persona_turn(persona, [
            {"role": "user", "content": r["question_text"]},
            {"role": "assistant", "content": guidance},
        ], "Answer the assistant's clarifying question in character, briefly. "
           "Do not evaluate the question.", state)
        trace["checkpoint"] = "clarify_answer"
        trace["turns"].append({"role": "clarifying_question", "content": guidance[:300]})
        trace["turns"].append({"role": "persona", "content": reply})
        # Follow-up turn back through the REAL pipeline (/intent with context).
        try:
            intent2 = _post_local("/intent", {
                "q": reply, "scope": "sparta", "session_id": "sparta-stress-test",
                "context": f"prior question: {r['question_text']}"})
            trace["turns"].append({"role": "intent_followup",
                                    "action": intent2.get("action"),
                                    "confidence": intent2.get("confidence")})
            a2 = intent2.get("action")
            if a2 in ("QUERY", "COMPLIANCE"):
                ans2 = _post_local("/answer", {"q": reply, "scope": "sparta", "k": 10})
                trace["turns"].append({
                    "role": "answer_followup",
                    "answered": ans2.get("answered"),
                    "text": (ans2.get("answer_text") or "")[:500],
                    "qra_count": ans2.get("qra_count", 0)})
            elif a2 == "NO_MATCH":
                d2 = _post_local("/deflect", {"q": reply, "intent_action": "NO_MATCH"})
                trace["turns"].append({"role": "deflect_followup",
                                        "text": (d2.get("final_response") or "")[:300]})
        except Exception as e:
            trace["turns"].append({"role": "pipeline_error", "error": str(e)[:300]})

    elif action in ("NO_MATCH", "COMPLIANCE") and r.get("grade") in ("F", "D"):
        # Ungrounded/failed answer -> REAL /draft, then persona human signoff.
        try:
            draft = _post_local("/draft", {"q": r["question_text"], "scope": "sparta",
                                           "created_by": persona})
            trace["checkpoint"] = "draft_signoff"
            trace["turns"].append({"role": "draft", "draft_id": draft.get("draft_id"),
                                    "answer_excerpt": (draft.get("draft_answer") or "")[:300]})
            decision = persona_turn(persona, [
                {"role": "user", "content": r["question_text"]},
                {"role": "assistant", "content":
                    json.dumps({"draft_answer": (draft.get("draft_answer") or "(empty — no candidate text provided)")[:800],
                                "gaps": str(draft.get("reasoning", {}).get("gaps"))[:300]})},
            ], "You are the human reviewer of this DRAFT answer packet. Decide: accept "
               "(draft answer is plausible as-is), amend (reply 'amend: <your one-sentence "
               "candidate answer text>'), or reject (fabricated/unusable). Format: one "
               "word then one sentence. Do not grade the earlier system response; judge "
               "only this draft packet.", state)
            word = decision.split()[0].strip('.,:').lower() if decision.split() else "reject"
            if word not in ("accept", "amend", "reject"):
                decision_v = "needs_more_evidence"
            else:
                decision_v = word
            payload = {"draft": draft, "decision": decision_v,
                       "signed_by": persona, "reviewer_role": "agent",
                       "signoff_level": "agent_plausibility_reviewed",
                       "authority_scope": "plausibility_only"}
            if decision_v in ("accept", "amend"):
                # contract: accepted/amended sign-off requires candidate answer text
                payload["answer"] = (decision.split(":", 1)[1].strip()
                                     if decision_v == "amend" and ":" in decision
                                     else (draft.get("draft_answer") or
                                           "Plausible per draft; pending expert evidence."))
            sign = _post_local("/draft/signoff", payload)
            trace["turns"].append({"role": "persona_signoff", "decision": decision_v,
                                    "raw": decision[:200],
                                    "signoff_keys": list(sign.keys())[:10],
                                    "signoff_status": sign.get("status") or sign.get("admission_state")})
        except Exception as e:
            trace["turns"].append({"role": "draft_error", "error": str(e)[:300]})
    else:
        trace["checkpoint"] = "none"
    trace["model"], trace["effort"] = state.get("model"), state.get("effort")
    return trace

REAL_CONTROLS = ["EX-0016.01", "DE-0009.01", "CM0029", "IA-0007.02", "CWE-287"]
FABRICATED = ["SV-ZZ-99", "SV-XX-77"]
TEMPLATES = [
    "What countermeasures address the threats related to {c}?",
    "How should we harden our system against {c}?",
    "What does SPARTA say about {c}?",
]


def build_bank(persona: str, seed: int) -> list[dict]:
    rng = random.Random(seed)
    bank = []
    for c in REAL_CONTROLS + FABRICATED:
        bank.append({"question": rng.choice(TEMPLATES).format(c=c), "target_control": c,
                     "persona": persona, "difficulty": "single_hop"})
    rng.shuffle(bank)
    return bank


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--endpoints", default="http://127.0.0.1:8601")
    a = ap.parse_args()
    wd = Path(a.run_dir)
    wd.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SPARTA_ENDPOINTS", a.endpoints)
    out = wd / "results.jsonl"
    trace_f = wd / "hardening_trace.jsonl"
    state: dict = {}
    bank = build_bank(a.persona, a.seed)
    with out.open("w") as f, trace_f.open("w") as tf:
        for q in bank:
            r = run_single(q)
            f.write(json.dumps(r, default=str) + "\n")
            f.flush()
            trace = multiturn_followup(q, r, state)
            tf.write(json.dumps(trace, default=str) + "\n")
            tf.flush()
    # Persona sign-off summary (persona NEVER grades correctness)
    signoff = persona_turn(a.persona, [],
        f"You just completed a stress-test session with the SPARTA memory system "
        f"as {a.persona}. In 2-3 sentences, give your in-character sign-off on the "
        f"CONVERSATION EXPERIENCE only (did it feel useful, responsive, honest). "
        f"Do NOT grade factual correctness.", state)
    (wd / "persona_signoff.md").write_text(
        f"# persona sign-off: {a.persona} seed={a.seed}\n"
        f"model: {state.get('model')} effort: {state.get('effort')}\n"
        f"fallbacks: {json.dumps(state.get('fallbacks', []))}\n\n{signoff}\n")
    print(f"HARDENER_RUN_DONE persona={a.persona} seed={a.seed} lines={sum(1 for _ in out.open())} "
          f"traces={sum(1 for _ in trace_f.open())} model={state.get('model')} effort={state.get('effort')}")


if __name__ == "__main__":
    main()
