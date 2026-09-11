"""Deterministic delivery-cover planner (the fast lane).

Every macro carries a "delivery cover": the instant, low-cost filler that plays
WHILE the slow high-reasoning answer generates. This maps (stage, intensity,
tags) -> an ordered cover plan in ~0ms with zero model reasoning, so the cover
lane can start speaking immediately (best-practices-chatterbox-agent two-lane
model; mirrors memory /intent fast:true). embry-voice-control runs the two
concurrent lanes and hands off (barge-in) when the answer is ready; this module
only maps the plan.

Escalation: only when tags mark the context ambiguous should the caller ask a
tiny model (glm-5.3-flash) to break a tie \u2014 the default path is deterministic.

Run `python3 cover_plan.py` for the self-check.
"""
from __future__ import annotations

# intensity 1-10 -> band; each band picks a thinking clip and a pause macro
_THINK = {"low": "think-mm-light", "mid": "think-hmm", "high": "think-hmm-long"}
_PAUSE = {"low": "beat", "mid": "considered", "high": "weight"}
# valid progress stages: memory pipeline + heavy Lane-B work activities
# (debugging=$debugger breakpoints, diagramming=$ops-excalidraw, searching=research)
_STAGES = {"intent", "recall", "clarify", "answer", "draft", "working_long",
           "debugging", "diagramming", "searching"}


def _band(intensity: int) -> str:
    if intensity <= 3:
        return "low"
    if intensity <= 7:
        return "mid"
    return "high"


def plan_cover(stage: str, intensity: int = 4, tags: list[str] | None = None) -> dict:
    """Map (stage, intensity, tags) -> ordered delivery cover. Deterministic.

    Returns a plan the cover lane plays immediately: a thinking sound, the
    stage's progress line, then a hold (pause, or a hum on an idle/long wait).
    """
    tags = tags or []
    if stage not in _STAGES:
        raise ValueError(f"unknown_stage:{stage}")
    band = _band(int(intensity))
    steps: list[dict] = [
        {"kind": "thinking", "clip": _THINK[band]},
        {"kind": "progress", "stage": stage},
    ]
    # hold: hum on an idle or long wait (mood-matched); otherwise a pause macro
    if "idle" in tags or stage == "working_long":
        mood = next((t.split(":", 1)[1] for t in tags if t.startswith("mood:")), "wistful")
        steps.append({"kind": "hum", "select_by": f"mood:{mood}"})
    else:
        steps.append({"kind": "pause", "macro": _PAUSE[band]})
    return {
        "schema": "chatterbox_speak.delivery_cover.v1",
        "stage": stage, "intensity": int(intensity), "band": band,
        "ambiguous": "ambiguous" in tags,  # caller may escalate to glm-5.3-flash tiebreak
        "steps": steps,
    }


def demo() -> None:
    p = plan_cover("recall", 5)
    assert p["band"] == "mid" and p["steps"][0]["clip"] == "think-hmm", p
    assert p["steps"][1] == {"kind": "progress", "stage": "recall"}
    assert p["steps"][2] == {"kind": "pause", "macro": "considered"}
    hi = plan_cover("answer", 9)
    assert hi["steps"][0]["clip"] == "think-hmm-long" and hi["steps"][2]["macro"] == "weight"
    idle = plan_cover("working_long", 2, tags=["idle", "mood:wistful"])
    assert idle["steps"][2] == {"kind": "hum", "select_by": "mood:wistful"}, idle
    dbg = plan_cover("debugging", 6)
    assert dbg["steps"][1] == {"kind": "progress", "stage": "debugging"}, dbg
    assert plan_cover("diagramming", 4)["steps"][1]["stage"] == "diagramming"
    assert plan_cover("intent", 4, tags=["ambiguous"])["ambiguous"] is True
    try:
        plan_cover("nope")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "unknown_stage:nope" in str(e)
    print("cover_plan.py self-check: PASS")


if __name__ == "__main__":
    demo()
