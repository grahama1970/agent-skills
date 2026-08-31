# research-routing-gates

Deterministic Pi extension for Memory-first and research-routing enforcement.

It rejects agent answers that skip required machine evidence:

```text
substantive prompt
  -> $memory recall/answer/intent first, before code/file scanning
  -> $brave-search for narrow current/external research
  -> $dogpile for comprehensive multi-source research
  -> $triage-error or $tau when reporting BLOCKED/NEEDS_ATTENTION/generic failures
  -> fast non-browser $ask single-call for broad/generic/ambiguous error sanity before slow WebGPT or a full roundtable
  -> $ask webgpt for one bounded independent review question
  -> $ask roundtable for thrashing, milestones, high-stakes design, or strategic next-step ambiguity after fast triage is insufficient
  -> $ask compete for two or more concrete candidate approaches/implementations
```

Agent prose is never a gate. A gate is a tool call/result, command output, JSON receipt, or Tau/triage-error artifact.

## Runtime behavior

- Enabled by default. Disable with `/research-gates off` or `PI_RESEARCH_GATES_ENABLED=0`.
- Tracks `tool_call` and `tool_result` events for recognized command evidence and read/grep/find/ls scanning.
- Runs `research-gate-check.mjs` at assistant `message_end`.
- Replaces rejected answers with `REJECTED_BY_RESEARCH_ROUTING_GATE` and queues one retry.

## Recognized evidence

Memory:

```bash
skills/memory/run.sh recall --q "..." --brief
# or HTTP Memory daemon /recall, /answer, /intent evidence
```

Brave:

```bash
skills/brave-search/run.sh web "..." --count 5
skills/brave-search/run.sh context "..."
```

Dogpile:

```bash
skills/dogpile/run.sh search "..." --output-dir /tmp/pi-research-gate-dogpile
```

Failure triage:

```bash
skills/triage-error/run.sh classify --text "<exact error>"
skills/triage-error/run.sh triage --receipt <receipt>
```

Tau:

```bash
skills/tau/run.sh status
skills/tau/run.sh workflow-run ...
cd ~/workspace/experiments/tau && uv run tau dag-run /path/to/dag.json
```

Ask modes:

| Required route | Deterministic trigger | Evidence that satisfies it |
| --- | --- | --- |
| `ask_webgpt_required` | explicit `$ask webgpt`; one bounded artifact/question needs independent external review; no broad/generic error, milestone, thrash, or alternatives | `skills/ask/run.sh webgpt ...` or Tau single-call with `--handler webgpt` |
| `ask_fast_single_required` | broad/generic/ambiguous error sanity check; slow WebGPT or full panel would be premature | Ask/Tau single-call with a fast non-browser low-reasoning handler such as `--handler claude-fable-low` |
| `ask_roundtable_required` | explicit roundtable/panel; thrashing without concrete candidates; milestone/phase/release boundary; high-stakes design; strategic next-step ambiguity after fast triage is insufficient | Ask/Tau roundtable DAG with `--dag-template roundtable`/concurrent topology and receipt |
| `ask_compete_required` | explicit compete/bakeoff; winner selection; two or more candidate approaches/implementations; thrashing with named repair candidates | `skills/ask/run.sh compete ...` receipt |

Precedence: `ask_compete` > explicit `ask_roundtable` > broad-error `ask_fast_single` > `ask_roundtable` > `ask_webgpt` > none.

Do not use Ask as closure proof. Ask output is reviewer/advisor evidence; local deterministic proof still closes work.

## Checker

Manual use:

```bash
node ~/.pi/agent/extensions/research-routing-gates/research-gate-check.mjs < payload.json
```

Input schema:

```json
{
  "user_text": "question",
  "assistant_text": "answer",
  "enabled": true,
  "observations": [
    {"phase":"call","kind":"memory","toolName":"bash","command":"skills/memory/run.sh recall --q question --brief"},
    {"phase":"result","kind":"memory","toolName":"bash","command":"skills/memory/run.sh recall --q question --brief","ok":true}
  ]
}
```

Output schema: `pi_research_gate.check.v1`.

## Proof boundary

This extension proves route discipline only. It does not prove that Memory, Brave, Dogpile, Tau, or triage-error returned correct content; those skills own their own receipts and proof contracts.
