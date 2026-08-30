# obvious-next-step-guard

Global Pi extension that prevents a final answer from becoming the stopping point when the answer names unfinished, unblocked work or reports an unblocked failure.

## What it enforces

On assistant `message_end`, the extension:

1. extracts the assistant text;
2. runs `obvious-next-step-check.mjs`;
3. detects labeled unfinished-work sections such as `Not done:`, `Remaining:`, or `Next step:`;
4. treats an unblocked failure report such as `failed 14/30`, `not acceptable`, or `exit code 1` as a required repair loop even when the agent failed to name the repair action;
5. includes the latest failed tool receipt in the continuation prompt when Pi captured one;
6. allows the answer when it names a real blocker, asks for required human authorization, says nothing remains, or only gives advisory/user-facing recommendations;
7. queues `CONTINUE_OBVIOUS_NEXT_STEP` with `pi.sendUserMessage(..., { deliverAs: "followUp" })` when the next action is unblocked;
8. caps automatic continuation with `OBVIOUS_NEXT_STEP_MAX_FOLLOWUPS`, default `3`, per originating user turn.

## Manual checker use

```bash
node ~/.pi/agent/extensions/obvious-next-step-guard/obvious-next-step-check.mjs < candidate.txt
```

Decision values:

- `pass`: Pi may stop.
- `follow_up`: Pi should queue a continuation turn.
- `error`: checker failure; the extension warns and does not block.

## Environment

```bash
OBVIOUS_NEXT_STEP_GUARD_ENABLED=0          # disable
OBVIOUS_NEXT_STEP_MAX_FOLLOWUPS=3         # default retry budget
```

## Proof boundary

This extension proves only that Pi refuses a narrow class of self-identified premature stops. It does not prove the named work succeeded. The follow-up must still execute deterministic gates and read back artifacts before claiming closure.

Reload Pi after the first install/edit:

```text
/reload
```

After this extension is loaded, agents can call the `reload_runtime` tool to queue `/reload-runtime` as a follow-up command instead of asking the human to reload.
