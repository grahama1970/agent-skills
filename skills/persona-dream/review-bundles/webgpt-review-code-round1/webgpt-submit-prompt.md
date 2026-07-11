# WebGPT Code Review Request: Persona-Dream Panel Repair Gate

Please perform a strict `$review-code` review of the attached bundle.

The project agent is blocked from moving to panel regeneration or Kling
preflight repair until this review returns a passable verdict. The attachment
contains the full review bundle, source files, prior WebGPT blocker verdict, and
the failed inline `$ask webgpt-review` transport receipt.

## Decision

Can the new `agents/persona-dream-panel-repair-gate/AGENTS.md` contract plus the
updated `skills/persona-dream/SKILL.md` gate safely control the next phase:
repairing generated storyboard panels and the Kling preflight packet?

## Must Re-Check

- The subagent must be persona-agnostic, not hardcoded to Horus/Embry.
- A panel must fail if required characters, props, weather, environmental
  physics, persona-memory cues, or source-reference anchors are missing.
- The script writer/realism gate must run before regeneration and again after a
  generated image introduces or omits important visible elements.
- Pasted overlays must fail; the scene must be regenerated or blocked.
- Unreviewed panels must block Kling/provider packets.
- Voice clone candidates without provider `voice_id` must block voiced provider
  payloads.
- The provider lane must default to `mode: std` / 720p for this experiment.
- `external_task_id`, callback or polling plan, provider-accessible media URLs,
  costs, and hashes must be required before live provider execution.

## Output Format

Return JSON first:

```json
{
  "verdict": "satisfied|needs_changes|blocked|insufficient_evidence",
  "blocking_findings": [
    {
      "file": "path",
      "issue": "specific problem",
      "why_it_matters": "risk",
      "required_change": "exact repair"
    }
  ],
  "non_blocking_findings": [],
  "patch_suggestions": [],
  "tests_to_run": [],
  "do_not_do": [],
  "aggregation_ready": false,
  "missing_evidence": []
}
```

Use `satisfied` only if this is adequate for the next phase. If an executable
runner/schema/test is mandatory before using the subagent contract, return
`needs_changes` and explain the smallest required fix.
