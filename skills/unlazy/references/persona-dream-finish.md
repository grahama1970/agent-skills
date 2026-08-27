# Using unlazy To Finish persona-dream

Use one `unlazy` ledger for the active Persona Dream finish path. The ledger
should live outside generated outputs, for example:

```text
skills/persona-dream/local/unlazy/finish-persona-dream/GATES.md
```

The ledger is operational state, not proof by itself. Each gate must point to a
command or receipt readback that can fail.

## Recommended Gates

```markdown
# Gates: persona-dream finish

OWNS: skills/persona-dream/**

Scope: finish the active Persona Dream proof path without conflating audible
conversation, provider/Kling readiness, human perception, or immutable-goal
closure.

- [ ] PD1: authoritative status surfaces are read before action
  CHECK: jq -e '.current_phase=="P2_CORRECTED_GOAL_PAIR_PROOF" and .next_step.default|test("PD-CORRECTED-GOAL-V1")' skills/persona-dream/CURRENT_STATUS.json && echo PERSONA_DREAM_STATUS_READBACK_OK
  EXPECT: PERSONA_DREAM_STATUS_READBACK_OK
  EVIDENCE: pending

- [ ] PD2: full-cycle audible loop receipt is present but scope-limited
  CHECK: skills/agentic-evals/run.sh run skills/persona-dream/fixtures/agentic_eval.json --case status-scope-boundary-regression --output /tmp/persona-dream-status-scope-boundary.json
  EXPECT: "readiness": "READY"
  EVIDENCE: pending

- [ ] PD3: PD-CORRECTED-GOAL-V1 paired proof has a fresh receipt
  CHECK: skills/persona-dream/run.sh corrected-goal-pair --manifest skills/persona-dream/evals/fixtures/pd_corrected_goal_v1.json --out /tmp/persona-dream-corrected-goal-pair --require-live --forbid-mocked && echo CORRECTED_GOAL_PAIR_RECEIPT_OK
  EXPECT: CORRECTED_GOAL_PAIR_RECEIPT_OK
  EVIDENCE: pending

- [ ] PD4: human perception is not falsely closed
  CHECK: jq -e '.current_claims.human_perceived_emotion_and_identity.valid_human_responses=="0/20" and (.current_claims.human_perceived_emotion_and_identity.blocked_by|index("SIGNED_INTERPRETATION.json"))' skills/persona-dream/CURRENT_STATUS.json && echo HUMAN_PERCEPTION_BLOCK_BOUNDARY_OK
  EXPECT: HUMAN_PERCEPTION_BLOCK_BOUNDARY_OK
  EVIDENCE: pending

- [ ] PD5: relevant edits are retained on origin/main
  CHECK: git ls-remote origin refs/heads/main && echo REMOTE_MAIN_READBACK_OK
  EXPECT: REMOTE_MAIN_READBACK_OK
  EVIDENCE: pending
```

## How To Run

Parse without executing:

```bash
skills/unlazy/run.sh gate-check --status skills/persona-dream/local/unlazy/finish-persona-dream/GATES.md
```

Lint the ledger:

```bash
skills/unlazy/run.sh gate-lint skills/persona-dream/local/unlazy/finish-persona-dream/GATES.md
```

After inspecting every command, run with explicit approval:

```bash
skills/unlazy/run.sh gate-check --approve skills/persona-dream/local/unlazy/finish-persona-dream/GATES.md
```

Reverify before reporting:

```bash
skills/unlazy/run.sh gate-check --reverify skills/persona-dream/local/unlazy/finish-persona-dream/GATES.md
```

## Stop Rule

If any required gate is unmet, report `Immutable Goal: NOT_MET` and the next
gate. If the remaining gate requires human listener rows, signed interpretation,
paid-call authorization, credentials, or external provider state, report
`Immutable Goal: BLOCKED:<reason>` and name the exact gate.
