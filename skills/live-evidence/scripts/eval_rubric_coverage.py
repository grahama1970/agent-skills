#!/usr/bin/env python3
"""Deterministic proof for evidence-bound rubric coverage (#1452).

Role fixture: six criteria; three answer cases (concrete architecture+scale
answer, plausible-but-vague answer, constraint-contradicting answer). Proves:

- exact evidence binding (unknown events rejected; cited text must state the
  required facts);
- coverage-state correctness for the three answers;
- no unsupported promotion (evidence-bearing state without refs rejected at
  the type layer; vague answer cannot cover scale/failure/testing);
- deterministic rubric digest;
- stale question revision and stale rubric digest rejected + journaled;
- suggestion cap of three; adversarial no-evidence suggestion rejected unless
  visibly unsupported;
- prohibited biometric/personality criteria fail rubric validation;
- rubric edit invalidates cached coverage;
- dismissal journaled without becoming coverage evidence;
- scoring_disabled pinned: no score field can exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from live_evidence.rubric import (
        CoverageState,
        CriterionCoverage,
        FollowUpSuggestion,
        RoleRubric,
        RubricCriterion,
        RubricEngine,
    )

    def criterion(cid: str, label: str, evidence: list[str]) -> RubricCriterion:
        return RubricCriterion(
            criterion_id=cid, label=label,
            job_relevance=f"{label} is required for the backend role",
            evidence_required=evidence,
        )

    rubric = RoleRubric(
        rubric_id="backend-senior-v1",
        role_name="Senior Backend Engineer",
        version=1,
        criteria=[
            criterion("architecture", "Architecture tradeoffs", ["queue", "sharding", "tradeoff", "latency"]),
            criterion("scale", "Production scale", ["requests per second", "rps", "million", "qps"]),
            criterion("failure", "Failure recovery", ["retry", "failover", "rollback", "outage"]),
            criterion("testing", "Testing practice", ["integration test", "load test", "test suite"]),
            criterion("debugging", "Debugging depth", ["profiler", "breakpoint", "trace", "core dump"]),
            criterion("ownership", "Ownership", ["on-call", "postmortem", "owned the service"]),
        ],
        question_bank=["Describe a system you scaled.", "Walk me through a production outage."],
    )
    engine = RubricEngine(rubric)
    digest = engine.rubric_digest

    check("rubric digest deterministic", digest == rubric.rubric_digest() == RoleRubric(
        **rubric.model_dump(exclude={"schema_id"})).rubric_digest(), digest[:16])

    # Prohibited dimensions rejected outright.
    for bad_label in ("Apparent confidence", "Eye contact quality", "Accent clarity"):
        try:
            criterion("bad", bad_label, ["x"])
            check(f"prohibited criterion rejected: {bad_label}", False, "accepted")
        except Exception as exc:
            check(f"prohibited criterion rejected: {bad_label}", "prohibited" in str(exc))

    # scoring cannot be enabled.
    try:
        RoleRubric(**{**rubric.model_dump(exclude={"schema_id"}), "scoring_disabled": False})
        check("scoring cannot be enabled on a rubric", False, "accepted")
    except Exception:
        check("scoring cannot be enabled on a rubric", True)

    question_id, revision = "q-scaling-story", 1

    # Answer case 1: concrete architecture + scale evidence.
    # Answer case 2: polished but vague (no scale/failure/testing facts).
    # Answer case 3: contradicts the stated latency constraint.
    events = [
        {"event_id": "ev-ans-concrete-1",
         "text": "We sharded postgres by tenant and moved writes to a queue, trading latency for durability"},
        {"event_id": "ev-ans-concrete-2",
         "text": "At peak we sustained 40 thousand requests per second across nine regions"},
        {"event_id": "ev-ans-vague-1",
         "text": "It was a very robust system, we followed best practices and everything ran smoothly at scale"},
        {"event_id": "ev-ans-contradict-1",
         "text": "Earlier I said our p99 latency budget was 100 milliseconds"},
        {"event_id": "ev-ans-contradict-2",
         "text": "The synchronous fanout meant every request waited about 900 milliseconds at p99"},
    ]

    def coverage(cid: str, state: CoverageState, event_ids: list[str], q: str = question_id,
                 rev: int = revision, dig: str = digest) -> CriterionCoverage:
        return CriterionCoverage(
            criterion_id=cid, state=state, evidence_event_ids=event_ids,
            question_id=q, question_revision=rev, rubric_digest=dig,
        )

    # Evidence-bearing state without references fails at the type layer.
    try:
        coverage("scale", CoverageState.COVERED, [])
        check("covered without evidence references rejected", False, "accepted")
    except Exception as exc:
        check("covered without evidence references rejected", "exact evidence" in str(exc))

    result = engine.apply_coverage(
        [
            coverage("architecture", CoverageState.COVERED, ["ev-ans-concrete-1"]),
            coverage("scale", CoverageState.COVERED, ["ev-ans-concrete-2"]),
            # Vague answer proposed as covering failure recovery: cited text
            # states none of the required facts -> must be rejected.
            coverage("failure", CoverageState.COVERED, ["ev-ans-vague-1"]),
            # Contradiction with exact spans is legitimate.
            coverage("architecture", CoverageState.CONTRADICTED,
                     ["ev-ans-contradict-1", "ev-ans-contradict-2"]),
            coverage("testing", CoverageState.UNTESTED, []),
        ],
        events,
        active_question_id=question_id,
        active_revision=revision,
    )
    accepted_states = {c.criterion_id: c.state for c in engine.coverage(question_id, revision)}
    check(
        "concrete answer covers architecture and scale with exact events",
        accepted_states.get("scale") is CoverageState.COVERED
        and accepted_states.get("architecture") is CoverageState.CONTRADICTED,
        f"states={ {k: v.value for k, v in accepted_states.items()} }",
    )
    check(
        "vague answer cannot mark failure recovery covered",
        any(r["criterion_id"] == "failure" and r["reason"] == "evidence_binding_failed"
            for r in result["rejected"])
        and "failure" not in accepted_states,
    )
    check(
        "untested state accepted without evidence and journal records rejections",
        accepted_states.get("testing") is CoverageState.UNTESTED
        and any(j["kind"] == "coverage_rejected" for j in engine.journal),
    )

    # Unknown transcript event rejected.
    unknown = engine.apply_coverage(
        [coverage("debugging", CoverageState.COVERED, ["ev-not-in-transcript"])],
        events, active_question_id=question_id, active_revision=revision,
    )
    check(
        "coverage citing unknown transcript event rejected",
        unknown["accepted"] == 0 and unknown["rejected"][0]["reason"] == "evidence_binding_failed",
    )

    # Stale revision and stale rubric digest rejected.
    stale = engine.apply_coverage(
        [coverage("debugging", CoverageState.COVERED, ["ev-ans-concrete-1"], rev=0)],
        events, active_question_id=question_id, active_revision=revision,
    )
    stale_digest = engine.apply_coverage(
        [coverage("debugging", CoverageState.COVERED, ["ev-ans-concrete-1"], dig="e" * 64)],
        events, active_question_id=question_id, active_revision=revision,
    )
    check(
        "stale question revision cannot update coverage",
        stale["accepted"] == 0 and stale["rejected"][0]["reason"] == "stale_question_revision",
    )
    check(
        "stale rubric digest cannot update coverage",
        stale_digest["accepted"] == 0 and stale_digest["rejected"][0]["reason"] == "stale_rubric_digest",
    )

    # Suggestions: adversarial no-evidence suggestion rejected unless unsupported.
    def suggestion(cid: str, event_ids: list[str], **kw) -> FollowUpSuggestion:
        return FollowUpSuggestion(
            question_text=f"Probe {cid}", criterion_id=cid,
            why_this_is_still_open="answer left this dimension unstated",
            supporting_answer_event_ids=event_ids,
            expected_evidence_type="concrete incident or measurement",
            question_id=question_id, question_revision=revision, rubric_digest=digest, **kw,
        )

    try:
        suggestion("failure", [])
        check("no-evidence suggestion rejected unless marked unsupported", False, "accepted")
    except Exception as exc:
        check("no-evidence suggestion rejected unless marked unsupported",
              "unsupported" in str(exc))
    flagged = suggestion("failure", [], unsupported=True)
    check("no-evidence suggestion allowed only with visible unsupported flag",
          flagged.unsupported is True)

    kept = engine.apply_suggestions(
        [
            suggestion("failure", ["ev-ans-vague-1"]),
            suggestion("testing", ["ev-ans-vague-1"]),
            suggestion("debugging", ["ev-ans-vague-1"]),
            suggestion("ownership", ["ev-ans-vague-1"]),
        ],
        active_question_id=question_id, active_revision=revision,
    )
    check("suggestions capped at three", len(kept) == 3, f"kept={len(kept)}")
    stale_suggestion = engine.apply_suggestions(
        [suggestion("failure", ["ev-ans-vague-1"])],
        active_question_id=question_id, active_revision=revision + 1,
    )
    check("stale-revision suggestion not applied to the new revision",
          stale_suggestion == [])

    # Dismissal journaled + attributable and never becomes coverage.
    before = {c.criterion_id: c.state for c in engine.coverage(question_id, revision)}
    engine.dismiss_suggestion(question_id, revision, "failure", actor="interviewer:graham")
    after = {c.criterion_id: c.state for c in engine.coverage(question_id, revision)}
    dismissals = [j for j in engine.journal if j["kind"] == "suggestion_dismissed"]
    check(
        "dismissal journaled with actor and does not change coverage",
        before == after and dismissals and dismissals[0]["actor"] == "interviewer:graham"
        and "failure" not in after,
    )

    # Rubric edit invalidates cached coverage.
    edited = rubric.model_copy(update={"version": 2})
    engine.replace_rubric(edited)
    check(
        "rubric edit invalidates cached coverage",
        engine.coverage(question_id, revision) == []
        and any(j["kind"] == "rubric_replaced" for j in engine.journal),
    )

    print()
    if FAILURES:
        print(f"rubric coverage: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("rubric coverage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
