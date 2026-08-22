# Persona Dream PD-CORRECTED-GOAL-V1 Next-Step Review Bundle

Date: 2026-08-22
Repository: grahama1970/agent-skills
Ticket: https://github.com/grahama1970/agent-skills/issues/1479

## Corrected Immutable Goal

Dreams plus Embry's journal/reflection about the dream should introduce bounded emotional conflict and Chatterbox delivery changes during dynamic Horus/Embry conversations, while the actual answer content, factual correctness, identity core, provenance, and synthetic-vs-literal boundary remain unchanged.

Operational causal chain:

1. memory residue is selected from real project memory;
2. the dream spine emits a provenance-bound synthetic dream packet;
3. Embry writes or receives a dream journal/reflection that names conflict, mood, and feelings from that dream;
4. that journal creates a bounded session mood/arc delta;
5. Horus and Embry talk audibly in a dynamic conversation about Embry's dream, mood, and feelings;
6. the answer body and protected facts remain invariant against the control;
7. only emotional framing and Chatterbox delivery channels change.

## Current Local State

Committed setup slice:

```text
b5a703e372f108f5bc7ec032bf77e906c9d06747
```

Remote read-back:

```text
git ls-remote origin refs/heads/main
b5a703e372f108f5bc7ec032bf77e906c9d06747 refs/heads/main
```

Changed and committed files:

- skills/persona-dream/GOAL.md
- skills/persona-dream/CURRENT_STATUS.json
- skills/persona-dream/run.sh
- skills/persona-dream/fixtures/agentic_eval.json
- skills/persona-dream/evals/fixtures/pd_corrected_goal_v1.json
- skills/persona-dream/scripts/validate_operational_goal.py
- skills/persona-dream/scripts/validate_corrected_goal_manifest.py
- skills/persona-dream/scripts/validate_answer_invariance.py
- skills/persona-dream/scripts/validate_emotion_lineage.py
- skills/persona-dream/scripts/validate_chatterbox_delivery.py
- skills/persona-dream/scripts/run_corrected_goal_pair.py
- skills/persona-dream/scripts/adjudicate_corrected_goal.py
- skills/persona-dream/local/proofs/pd-corrected-goal-v1/manifest.json
- skills/persona-dream/local/proofs/pd-corrected-goal-v1/corrected_goal_pair_runner_receipt.json
- skills/persona-dream/local/proofs/pd-corrected-goal-v1/corrected_goal_receipt.json

## Proof Already Run

```text
jq empty skills/persona-dream/CURRENT_STATUS.json skills/persona-dream/evals/fixtures/pd_corrected_goal_v1.json skills/persona-dream/fixtures/agentic_eval.json
```

Result: exit 0.

```text
python3 -m py_compile skills/persona-dream/scripts/run_corrected_goal_pair.py skills/persona-dream/scripts/validate_operational_goal.py skills/persona-dream/scripts/validate_corrected_goal_manifest.py skills/persona-dream/scripts/validate_answer_invariance.py skills/persona-dream/scripts/validate_emotion_lineage.py skills/persona-dream/scripts/validate_chatterbox_delivery.py skills/persona-dream/scripts/adjudicate_corrected_goal.py
```

Result: exit 0.

```text
skills/persona-dream/run.sh validate-operational-goal --goal skills/persona-dream/GOAL.md --status skills/persona-dream/CURRENT_STATUS.json --expected-proof-id PD-CORRECTED-GOAL-V1
```

Result: `PASS_OPERATIONAL_GOAL_PINNED`, `mocked:false`, `live:false`.

```text
skills/persona-dream/run.sh check-current-state-consistency --strict --json
```

Result: `PASS_CURRENT_STATE_CONSISTENT`, `mismatch_count:0`.

```text
skills/agentic-evals/run.sh run skills/persona-dream/fixtures/agentic_eval.json --case corrected-goal-manifest-validators --case corrected-goal-pair-blocks-without-live-artifacts --output TEMPORARY_REPORT_PATH
```

Result: `READY`, `case_count:2`, `trial_count:6`, `PASS:2`, `FAIL:0`, `BLOCKED:0`. The generated report was written under temporary storage. This is deterministic fixture/fault-injection evidence only; it is not live Persona Dream proof.

```text
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 731 test file(s); no mock+proof claim violations`.

## Current Fail-Closed Receipt

Path:

```text
skills/persona-dream/local/proofs/pd-corrected-goal-v1/corrected_goal_receipt.json
```

Status:

```text
BLOCKED_CORRECTED_GOAL_PAIRED_PROOF
mocked: false
live: false
```

Missing live artifacts named by the receipt:

- `control/conversation.jsonl`
- `treatment/conversation.jsonl`
- `answer_invariance.json`
- `emotional_carryover.json`
- `chatterbox_delivery.json`

## Live Service State

Chatterbox was initially stopped. It was started with:

```text
docker start chatterbox-fork-agent-server
```

Health read-back from `http://127.0.0.1:8018/health` returned:

```text
ok: true
mocked: false
live: true
engine: chatterbox_turbo
device: cuda
model_loaded: true
```

Relevant Chatterbox constraints observed from the health payload:

- `[sigh]` is an accepted native tag.
- `pace` is applied.
- `tone` is request-only on default turbo unless `emotion_realization=audible`.
- intensity is the useful affect channel; valence is perceptually inert in the current path.
- explicit intensity/valence/base-emotion routing can conflict with non-literal inline tags, so the proof must be precise about which delivery channel is being tested.

UX/API state has not yet been proven in this continuation. Existing dynamic conversation scripts expect `PD_UX_BASE_URL` default `http://127.0.0.1:8790` and Chatterbox on `http://127.0.0.1:8018`.

## Existing Persona Dream Runtime Paths

Existing useful files:

- `skills/persona-dream/scripts/eval_audible_conversation.py` drives a journal-bearing run through `scripts/dynamic_conversation.py` for two Horus/Embry turn pairs and blocks if Chatterbox or the UX server is unreachable.
- `skills/persona-dream/scripts/dynamic_conversation.py` drafts Horus through Tau, speaks Horus through Chatterbox, then calls `speak_reply.generate_and_speak` for Embry.
- `skills/persona-dream/scripts/speak_reply.py` builds Embry's prompt from `journal.md`, `journal_entry.json` or `persona_journal.json`, and conversation history, then speaks through Chatterbox.
- `skills/persona-dream/scripts/append_conversation.py` refuses Horus or Embry turns without tone and rendered audio and sha256-binds them into `conversation.jsonl`.

## Ticket And Watchdog State

Ticket #1479 was created, leased, and commented with the setup-slice proof. It remains open.

Lease:

```text
lease_id: 20260822T154339Z-agent-skill-maintainer-1479
maintainer-active label present
```

Release attempt failed because `$ticket` worktree retention audit found unrelated dirty secondary worktrees:

```text
ERROR: worktree retention audit failed; commit, remove, or explicitly retain flagged secondary worktrees before releasing/closing the ticket
```

Project watchdog status:

- `skills/project-watchdog/run.sh status` reported `agent-skills` active.
- Installed cron line is currently scoped to `--project tau`, so automatic cron dispatch for `agent-skills` was not proven.
- `skills/project-watchdog/run.sh tick --project agent-skills --max-tickets 1` returned `SKIPPED` with stop_reason `tick_already_running`.

## Open Question For Reviewers

Given this context, what are the next deterministic steps to finish #1479 and the corrected immutable goal without drifting?

Please answer with:

1. the smallest live proof slice that should run next;
2. the exact artifacts that slice must produce;
3. whether to reuse `eval_audible_conversation.py`, write a paired adapter around existing scripts, or first run a narrower service proof;
4. how to handle Chatterbox delivery gates given the native-tag versus affect-backend tradeoff;
5. how `$ticket` and `$project-watchdog` should track creation, diagnosis, proof comments, release, and closure;
6. any action that should be explicitly deferred to avoid scope drift.

Do not mark the immutable goal complete unless the live paired control/treatment artifacts and final receipt exist.
