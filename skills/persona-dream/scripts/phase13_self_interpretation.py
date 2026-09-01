#!/usr/bin/env python3
"""Phase 13 - Persona self-interpretation of a Watch observation packet.

Compares the intended dream (story/script/storyboard intent), the grounded
source memories (recalled through the $memory HTTP API), the actual Watch
observations, and persona state, then drafts tentative interpretations with
scillm gpt-5.5.

The interpretive DRAFTING is done by the LLM. The CITATION / GROUNDING
VALIDATION is deterministic code (this module): every accepted claim must cite
at least one Watch observation id AND at least one source-memory id, carry
confidence and uncertainty, and offer an alternative (renderer-defect)
explanation. When a claim cites a renderer continuity review whose verdict is a
defect (for example DRIFT), the honesty rule requires the renderer-defect
explanation be FAVORED - the code rejects claims that treat a renderer defect as
psychological truth.

Interpretation is a proposal, never a durable persona rewrite.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util as _ilu
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_BASE_URL = os.environ.get("MEMORY_BASE_URL", "http://127.0.0.1:8601")
SCILLM_MODEL = os.environ.get("PERSONA_DREAM_SCILLM_MODEL", "gpt-5.5")
CALLER_SKILL = "persona-dream"

# Text reasoning is routed through the sanctioned Tau node - persona-dream never
# calls scillm directly. Load the adapter by file path so this works whether
# phase13 is run as a script or imported via importlib (phase14 / loop runner).
_ADAPTER_PATH = Path(__file__).resolve().parent / "tau_text_reasoning_adapter.py"
_aspec = _ilu.spec_from_file_location("tau_text_reasoning_adapter", _ADAPTER_PATH)
assert _aspec and _aspec.loader
tau_adapter = _ilu.module_from_spec(_aspec)
_aspec.loader.exec_module(tau_adapter)

# Persona/relationship cognition contract loader (Defect 5): recall questions,
# subject/target, and persona ids come from ONE fixture contract - never
# hardcoded here.
_CONTRACT_PATH = Path(__file__).resolve().parent / "persona_dream_cognition_contract.py"
_cspec = _ilu.spec_from_file_location("persona_dream_cognition_contract", _CONTRACT_PATH)
assert _cspec and _cspec.loader
cognition_contract = _ilu.module_from_spec(_cspec)
_cspec.loader.exec_module(cognition_contract)

# Caller-defined JSON output contract handed to (and hash-recorded by) the Tau node.
INTERPRETATION_OUTPUT_CONTRACT = {
    "type": "object",
    "required": ["candidates"],
    "candidate_required": [
        "interpretation_id", "tom_state_type", "subject", "target", "statement",
        "observation_refs", "source_memory_refs", "confidence", "uncertainty",
        "emotional_intensity", "alternative_explanation", "favored_explanation",
    ],
}

# Defect verdicts on a renderer continuity review that make the renderer-defect
# explanation the FAVORED one under the honesty rule.
RENDERER_DEFECT_VERDICTS = {"DRIFT", "FAIL", "MISMATCH", "NO_MATCH"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def file_sha(path: Path) -> str:
    return f"sha256:{hashlib.sha256(Path(path).read_bytes()).hexdigest()}"


# --------------------------------------------------------------------------- #
# Deterministic observation index                                             #
# --------------------------------------------------------------------------- #
def build_observation_index(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive stable, citeable Watch observation ids from an observation packet."""
    index: list[dict[str, Any]] = []

    for frame in packet.get("frame_evidence", []) or []:
        idx = frame.get("index")
        obs_id = f"frame_{int(idx):04d}" if idx is not None else None
        if not obs_id:
            continue
        windows = []
        if frame.get("in_identity_window"):
            windows.append("identity")
        if frame.get("in_speaker_window"):
            windows.append("speaker")
        index.append({
            "observation_id": obs_id,
            "observation_type": "frame",
            "summary": (
                f"Frame {idx} at t={frame.get('timestamp_seconds')}s"
                + (f"; windows={','.join(windows)}" if windows else "")
                + (f"; entities={frame.get('observed_entities')}" if frame.get("observed_entities") else "; entities=unavailable")
            ),
            "renderer_review": False,
            "renderer_defect_verdict": None,
            "timestamp_seconds": frame.get("timestamp_seconds"),
        })

    for fact in packet.get("transcript_facts", []) or []:
        fid = fact.get("fact_id")
        if not fid:
            continue
        index.append({
            "observation_id": fid,
            "observation_type": "transcript_fact",
            "summary": f"Transcript {fact.get('time_range')}: {fact.get('statement')}",
            "renderer_review": False,
            "renderer_defect_verdict": None,
        })

    hooks = packet.get("step_hooks", {}) or {}
    cont = hooks.get("step_36_identity_temporal_continuity")
    if isinstance(cont, dict):
        review = cont.get("vision_review", {}) or {}
        verdict = review.get("verdict")
        index.append({
            "observation_id": "identity_temporal_continuity_review",
            "observation_type": "renderer_continuity_review",
            "summary": (
                f"Identity continuity review over window {cont.get('identity_window_seconds')} "
                f"(model={review.get('model')}, verdict={verdict}): "
                + str(review.get("raw_output_tail", "")).replace("\n", " ")[:400]
            ),
            "renderer_review": True,
            "renderer_defect_verdict": verdict,
        })

    speaker = hooks.get("step_38_visible_speaker_lipsync")
    if isinstance(speaker, dict):
        index.append({
            "observation_id": "visible_speaker_lipsync_window",
            "observation_type": "speaker_visibility",
            "summary": (
                f"Speaker {speaker.get('speaker')} flagged visible over "
                f"{speaker.get('spoken_interval_seconds')}s saying: "
                f"{speaker.get('transcript_line_at_interval')}"
            ),
            "renderer_review": False,
            "renderer_defect_verdict": None,
        })

    for i, gap in enumerate(packet.get("coverage_gaps", []) or []):
        index.append({
            "observation_id": f"coverage_gap_{i:02d}",
            "observation_type": "coverage_gap",
            "summary": str(gap),
            "renderer_review": False,
            "renderer_defect_verdict": None,
        })

    return index


def renderer_defect_observation_ids(observation_index: list[dict[str, Any]]) -> set[str]:
    """Observation ids that are renderer reviews with a defect verdict (honesty rule)."""
    out: set[str] = set()
    for obs in observation_index:
        if obs.get("renderer_review") and str(obs.get("renderer_defect_verdict") or "").upper() in RENDERER_DEFECT_VERDICTS:
            out.add(obs["observation_id"])
    return out


# --------------------------------------------------------------------------- #
# Deterministic citation / grounding validation                               #
# --------------------------------------------------------------------------- #
def validate_candidate(
    candidate: dict[str, Any],
    observation_ids: set[str],
    source_ids: set[str],
    defect_observation_ids: set[str],
    allowed_targets: set[str] | None = None,
) -> list[str]:
    """Return a list of rejection reasons. Empty list == admissible."""
    reasons: list[str] = []

    for field in ("interpretation_id", "tom_state_type", "subject", "target", "statement"):
        if not str(candidate.get(field) or "").strip():
            reasons.append(f"MISSING_FIELD:{field}")

    target = str(candidate.get("target") or "").strip()
    if allowed_targets is not None and target and target not in allowed_targets:
        reasons.append(f"TARGET_OUTSIDE_CONTRACT:{target}")

    obs_refs = candidate.get("observation_refs")
    if not isinstance(obs_refs, list) or not obs_refs:
        reasons.append("NO_OBSERVATION_CITATION")
    else:
        unknown = [r for r in obs_refs if r not in observation_ids]
        if unknown:
            reasons.append(f"UNKNOWN_OBSERVATION_REFS:{','.join(map(str, unknown))}")

    src_refs = candidate.get("source_memory_refs")
    if not isinstance(src_refs, list) or not src_refs:
        reasons.append("NO_SOURCE_MEMORY_CITATION")
    else:
        unknown = [r for r in src_refs if r not in source_ids]
        if unknown:
            reasons.append(f"UNKNOWN_SOURCE_MEMORY_REFS:{','.join(map(str, unknown))}")

    if not str(candidate.get("alternative_explanation") or "").strip():
        reasons.append("MISSING_ALTERNATIVE_EXPLANATION")

    conf = candidate.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        reasons.append("CONFIDENCE_OUT_OF_RANGE")

    intensity = candidate.get("emotional_intensity")
    if intensity is not None and (not isinstance(intensity, (int, float)) or not (0.0 <= float(intensity) <= 1.0)):
        reasons.append("EMOTIONAL_INTENSITY_OUT_OF_RANGE")

    # Honesty rule: a claim that cites a renderer defect review must FAVOR the
    # renderer-defect explanation. Psychological meaning cannot silently override
    # a proven renderer failure.
    cited_defects = [r for r in (obs_refs or []) if r in defect_observation_ids]
    if cited_defects and candidate.get("favored_explanation") != "renderer_defect":
        reasons.append("RENDERER_DEFECT_NOT_FAVORED_DESPITE_REVIEW")

    return reasons


def validate_interpretations(
    candidates: list[dict[str, Any]],
    observation_index: list[dict[str, Any]],
    source_ids: set[str],
    allowed_targets: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observation_ids = {o["observation_id"] for o in observation_index}
    defect_ids = renderer_defect_observation_ids(observation_index)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for cand in candidates:
        reasons = validate_candidate(cand, observation_ids, source_ids, defect_ids, allowed_targets)
        if reasons:
            rejected.append({"interpretation_id": cand.get("interpretation_id", "?"), "reasons": reasons})
        else:
            stamped = dict(cand)
            stamped["synthetic_origin"] = True
            stamped["literal_historical_event"] = False
            stamped.setdefault("cites_renderer_review", any(r in defect_ids for r in cand.get("observation_refs", [])))
            accepted.append(stamped)
    return accepted, rejected


# --------------------------------------------------------------------------- #
# Source-memory recall through the $memory HTTP API                           #
# --------------------------------------------------------------------------- #
def _http_post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def recall_source_memories(
    questions: list[str],
    residue_source_ids: list[str],
    persona_id: str,
    base_url: str = MEMORY_BASE_URL,
) -> list[dict[str, Any]]:
    """Question-shaped recall of grounded source memories; returns recall receipts."""
    receipts: list[dict[str, Any]] = []
    residue_set = set(residue_source_ids)
    for question in questions:
        collections = ["persona_memory"]
        tags = [f"persona:{persona_id}"]
        try:
            data = _http_post(
                f"{base_url.rstrip('/')}/recall",
                {"q": question, "collections": collections, "tags": tags, "k": 8},
                {},
                15.0,
            )
            keys = [str(i.get("_key")) for i in data.get("items", []) if i.get("_key")]
            confirmed = sorted(residue_set.intersection(keys))
            receipts.append({
                "question": question,
                "collections": collections,
                "tags": tags,
                "found": bool(data.get("found")),
                "confidence": data.get("confidence"),
                "returned_keys": keys,
                "residue_source_ids_confirmed": confirmed,
            })
        except Exception as exc:  # noqa: BLE001 - record the failure, do not fabricate recall
            receipts.append({
                "question": question,
                "collections": collections,
                "tags": tags,
                "found": False,
                "confidence": None,
                "returned_keys": [],
                "residue_source_ids_confirmed": [],
                "error": str(exc),
            })
    return receipts


# --------------------------------------------------------------------------- #
# scillm gpt-5.5 interpretive drafting                                        #
# --------------------------------------------------------------------------- #
def build_prompt(
    intended_dream: dict[str, Any],
    observation_index: list[dict[str, Any]],
    source_bindings: list[dict[str, Any]],
    persona_id: str,
    example_target: str,
) -> str:
    obs_lines = "\n".join(f"  - {o['observation_id']} [{o['observation_type']}]: {o['summary']}" for o in observation_index)
    src_lines = "\n".join(f"  - {b['source_id']}: {b.get('text','')[:400]}" for b in source_bindings)
    defect_ids = sorted(renderer_defect_observation_ids(observation_index))
    return f"""You are the self-interpretation stage of persona-dream for persona "{persona_id}".
You compare an INTENDED dream against what was ACTUALLY rendered (Watch observations)
and the grounded SOURCE MEMORIES, then propose TENTATIVE interpretations.

HARD RULES (a downstream deterministic gate will REJECT any claim that breaks them):
1. Every claim must cite at least one observation_id from the OBSERVATIONS list
   AND at least one source_id from the SOURCE MEMORIES list. Never invent ids.
2. Every claim must carry a confidence in [0,1], an uncertainty note, and an
   emotional_intensity in [0,1].
3. Every claim must include an alternative_explanation that is the simpler,
   non-psychological reading (for example a renderer or context defect).
4. HONESTY RULE: for any claim that cites a renderer continuity review with a
   defect verdict (these observation ids: {defect_ids or 'none'}), you MUST set
   favored_explanation="renderer_defect" and give BOTH a psychological reading
   (as the statement) AND the renderer-defect reading (as alternative_explanation).
   A generated symbol is not automatically psychological truth.

INTENDED DREAM:
{json.dumps(intended_dream, indent=2)[:1600]}

OBSERVATIONS (cite these observation_ids):
{obs_lines}

SOURCE MEMORIES (cite these source_ids):
{src_lines}

Return ONLY a JSON object of the form:
{{"candidates": [
  {{
    "interpretation_id": "interpretation-001",
    "tom_state_type": "trust|belief|fear|desire|uncertainty|stance|relationship_state",
    "subject": "{persona_id}",
    "target": "{example_target}",
    "statement": "<tentative psychological interpretation>",
    "observation_refs": ["<observation_id>", ...],
    "source_memory_refs": ["<source_id>", ...],
    "confidence": 0.4,
    "uncertainty": "<what is unresolved>",
    "emotional_intensity": 0.5,
    "alternative_explanation": "<simpler renderer/context reading>",
    "cites_renderer_review": true,
    "favored_explanation": "renderer_defect|psychological|undetermined"
  }}
]}}
Produce 2 to 4 candidates. At least one MUST address the identity continuity
review (renderer defect) if one is present. No prose outside the JSON object."""


def draft_interpretations(prompt: str, timeout: float = 240.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Draft interpretations through the sanctioned Tau text-reasoning node.

    No direct scillm call: only Tau may reach scillm. Returns the drafted
    candidates (the LLM only proposes; the deterministic gate below decides
    admissibility) and the Tau receipt (prompt hash, api_key_source, raw output).
    """
    parsed, receipt = tau_adapter.dispatch_text_reasoning(
        prompt,
        role="persona-self-interpretation",
        output_contract=INTERPRETATION_OUTPUT_CONTRACT,
        caller_skill=CALLER_SKILL,
        model=SCILLM_MODEL,
        timeout_s=timeout,
    )
    candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    return candidates, receipt


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
def load_intended_dream(story_contract: Path | None, script_contract: Path | None) -> dict[str, Any]:
    intended: dict[str, Any] = {}
    if story_contract and Path(story_contract).exists():
        story = read_json(story_contract)
        intended["story"] = story.get("story")
        intended["target_duration_s"] = story.get("target_duration_s")
    if script_contract and Path(script_contract).exists():
        script = read_json(script_contract)
        intended["action_blocks"] = script.get("action_blocks")
        intended["dialogue_blocks"] = script.get("dialogue_blocks")
    return intended


def load_source_bindings(residue: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    bindings: list[dict[str, Any]] = []
    blockers: list[str] = []
    items = residue.get("items")
    if residue.get("schema") != "persona_dream.residue_links.v1" or not isinstance(items, list) or not items:
        return [], ["BLOCKED_RESIDUE_PACKET_INVALID"]
    for i, item in enumerate(items):
        source_id = str(item.get("source_id") or "").strip()
        text = str(item.get("text") or item.get("retrieval_text") or "").strip()
        persona_id = str(item.get("persona_id") or "").strip()
        if not source_id or not text or not persona_id:
            blockers.append(f"BLOCKED_RESIDUE_ITEM_INCOMPLETE:{i}")
            continue
        bindings.append({
            "source_id": source_id,
            "persona_id": persona_id,
            "collection": item.get("collection"),
            "text": text,
            "memory_text_sha256": canonical_sha(text),
        })
    if not bindings:
        blockers.append("BLOCKED_SOURCE_MEMORY_BINDING_MISSING")
    return bindings, blockers


def run_phase13(
    observation_path: Path,
    residue_path: Path,
    story_contract: Path | None,
    script_contract: Path | None,
    dream_id: str,
    revision_id: str,
    run_id: str,
    persona_id: str,
    live: bool = True,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if contract is None:
        contract = cognition_contract.load_contract()
    example_target = contract["default_target"]

    packet = read_json(observation_path)
    residue = read_json(residue_path)
    observation_index = build_observation_index(packet)
    source_bindings, blockers = load_source_bindings(residue)
    source_ids = {b["source_id"] for b in source_bindings}

    recall_receipts: list[dict[str, Any]] = []
    if live and source_bindings:
        questions = cognition_contract.recall_questions(contract)
        recall_receipts = recall_source_memories(questions, sorted(source_ids), persona_id)
        confirmed = set()
        for r in recall_receipts:
            confirmed.update(r.get("residue_source_ids_confirmed", []))
        for b in source_bindings:
            b["recall_confirmed"] = b["source_id"] in confirmed

    intended_dream = load_intended_dream(story_contract, script_contract)

    candidates: list[dict[str, Any]] = []
    llm_meta: dict[str, Any] = {
        "model": SCILLM_MODEL,
        "provider": "scillm",
        "route": "tau:persona-dream-text-reasoning",
        "direct_scillm_call": False,
        "caller_skill": CALLER_SKILL,
    }
    if live and source_bindings and observation_index:
        prompt = build_prompt(intended_dream, observation_index, source_bindings, persona_id, example_target)
        candidates, tau_receipt = draft_interpretations(prompt)
        llm_meta["candidate_count"] = len(candidates)
        llm_meta["tau_routing"] = tau_adapter.receipt_provenance(tau_receipt)

    accepted, rejected = validate_interpretations(
        candidates,
        observation_index,
        source_ids,
        allowed_targets={str(example_target), "unknown_person"},
    )

    defect_ids = renderer_defect_observation_ids(observation_index)
    drift_dual = any(
        any(r in defect_ids for r in c.get("observation_refs", []))
        and c.get("favored_explanation") == "renderer_defect"
        and str(c.get("alternative_explanation") or "").strip()
        for c in accepted
    )

    if blockers or not observation_index or not source_bindings:
        status = "BLOCKED_SELF_INTERPRETATION"
    elif not accepted:
        status = "BLOCKED_SELF_INTERPRETATION"
    elif rejected:
        status = "PASS_SELF_INTERPRETATION_WITH_REJECTIONS"
    else:
        status = "PASS_SELF_INTERPRETATION"

    # Strip the raw memory text out of persisted bindings (keep the hash).
    persisted_bindings = [
        {k: v for k, v in b.items() if k != "text"} for b in source_bindings
    ]

    return {
        "schema": "persona_dream.dream_self_interpretation.v1",
        "status": status,
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "persona_id": persona_id,
        "observation_packet_path": str(observation_path),
        "observation_packet_sha256": file_sha(observation_path),
        "intended_dream": intended_dream,
        "observation_index": observation_index,
        "source_memory_bindings": persisted_bindings,
        "recall_receipts": recall_receipts,
        "llm": llm_meta,
        "candidates": candidates,
        "accepted_interpretations": accepted,
        "rejected_interpretations": rejected,
        "honesty_rule": {
            "identity_drift_dual_explanation_present": drift_dual,
            "renderer_defect_favored_on_drift": drift_dual,
        },
        "blockers": blockers,
        "mocked": False,
        "live": bool(live),
        "provider_live": bool(live and candidates),
        "generated_at": utc_now(),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observation", type=Path, required=True)
    p.add_argument("--residue-links", type=Path, required=True)
    p.add_argument("--story-contract", type=Path, default=None)
    p.add_argument("--script-contract", type=Path, default=None)
    p.add_argument("--dream-id", required=True)
    p.add_argument("--revision-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--persona-id", default=None,
                   help="Persona id. Defaults to the cognition contract's persona_id.")
    p.add_argument("--contract", type=Path, default=None,
                   help="Persona/relationship cognition contract path (defaults to the fixture lane).")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--no-live", action="store_true", help="Skip recall + LLM (deterministic contract only)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    contract = cognition_contract.load_contract(args.contract)
    persona_id = args.persona_id or contract["persona_id"]
    result = run_phase13(
        args.observation, args.residue_links, args.story_contract, args.script_contract,
        args.dream_id, args.revision_id, args.run_id, persona_id, live=not args.no_live,
        contract=contract,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    if args.json:
        print(json.dumps({"status": result["status"], "accepted": len(result["accepted_interpretations"]),
                          "rejected": len(result["rejected_interpretations"]), "output": str(args.output)}, indent=2))
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
