# Battle Terminal Semantics For Local MVP

Decision date: 2026-08-01

## Decision

The local MVP supports only terminal states backed by Battle Judge and
scorekeeper receipts:

- `BLUE_SUCCESS`
- `RED_SUCCESS`
- `INSUFFICIENT_EVIDENCE`
- `BLOCKED`
- `UNAVAILABLE`

The local MVP does not support explicit `kill`, `promotion`, or `fastest_crash`
terminal semantics as operator-visible success states unless a future
implementation provides Judge-backed receipts for those states.

## Receipt Requirements

Supported terminal states must come from one of these receipt families:

- `battle.arena_tau_public_only_judge_receipt.v1`
- `battle.arena_tau_public_only_run_receipt.v1`
- `battle.tiered_live_qualification_gate.v1`
- `battle.same_run_arena_pixi_qualification.v1`

UI layers may render unsupported states only as unavailable or hidden. They must
not infer terminal success from animation labels, local preview flags, model
text, Tau provider claims, or spectator-only state.

The shared `battle_skill.terminal_semantics` boundary reads the underlying
`battle.arena_tau_public_only_judge_receipt.v1` bytes, binds their SHA-256,
and validates the verdict against typed pair-attempt observations. Wrapper
receipt families above must resolve to that Judge; their own success labels
are not authority. `current-status check` uses the selected campaign Judge.
`--terminal-candidate PATH` accepts a JSON candidate with `terminal_state`,
`source_schema`, `source_authority: judge`, `source_status`, `judge_receipt`,
and `judge_receipt_sha256`. Missing files, changed bytes, contradictory verdicts,
crash-only results, and unsupported states are rejected. Arena-to-Pixi
qualification and the public-only receipt adapter use the same boundary.

The command validates retained receipts; it does not run a new Docker replay.
Adversarial cases live in the retained `battle-terminal-semantics` eval, not
inside the production status command.

## Unsupported States

| State | Local MVP behavior | Required future proof |
|---|---|---|
| `kill` | Hidden or unavailable | Judge receipt proving a kill event and its boundary |
| `promotion` | Hidden or unavailable | Scorekeeper/Judge receipt proving promotion criteria |
| `fastest_crash` | Hidden or unavailable | Judge receipt proving crash timing and comparison method |

## Source Evidence

- `skills/battle/SKILL.md` assigns scoring authority to Judge/scorekeeper
  receipts and treats model/provider claims as advisory only.
- `skills/battle/CURRENT_STATUS.json` records same-run `BLUE_SUCCESS` proof and
  explicitly does not claim production deployment or adaptive-effect proof.
- The same-run qualification receipt
  `/tmp/battle-same-run-qualification-1143-pushed-20260801T124449Z/qualification-receipt.json`
  proves Judge-backed `BLUE_SUCCESS`; it does not prove kill, promotion, or
  fastest-crash semantics.
