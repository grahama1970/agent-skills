---
name: loop
description: >
  Run one bounded executable harness for a scoped artifact: explorer -> coder ->
  checks -> code-reviewer -> repair until PASS, BLOCKED, or max attempts.
metadata:
  short-description: Executable one-artifact loop harness
provides:
  - bounded-artifact-loop
  - executable-repair-harness
  - loop-receipts
composes:
  - code-review-runner
  - review-code
  - task-monitor
  - best-practices-python
complies:
  - best-practices-skills
  - best-practices-python
disciplines:
  - agentic-orchestration
---

# Loop Skill

Use `$loop` when the user wants one scoped artifact completed with an explicit inspect, code, review, repair cycle.

Do not manually simulate the loop in chat. The skill invokes the executable harness, and the harness writes the truth artifact:

```text
.loop/runs/<run_id>/final-receipt.json
```

## Boundary

`$loop` is a single DAG node worker, not a project DAG engine.

Outer project agents own dependencies, scheduling, multi-artifact plans, retries across nodes, branch/worktree policy, and promotion decisions. `$loop` owns one bounded artifact transaction:

```text
explorer once -> coder attempt -> deterministic checks -> code-reviewer -> repair or stop
```

If the task spans multiple independent artifacts, keep that graph outside `$loop` and call `$loop` separately for each artifact-sized node.

## Threat Model

Phase 0 agents are unreliable, not hostile same-user malware.

They may timeout, fail, emit malformed JSON, edit wrong files, create out-of-scope files, or accidentally interfere with artifacts. Phase 0 does not claim protection against deliberate filesystem race attacks, shell startup tampering, Git hook tampering, container escape, or full same-user compromise. Use isolated disposable git worktrees for real project-agent runs.

## Command

Run from the repository root:

```bash
python skills/loop/scripts/loop.py \
  --objective-file <objective-file> \
  --agent-config <agents.toml> \
  --allow '<glob>' \
  --check '<command>' \
  --max-attempts 3 \
  --check-timeout 300 \
  --print-json
```

You may use `--objective '<text>'` instead of `--objective-file`.

Required inputs:

- `--objective` or `--objective-file`
- `--agent-config`
- at least one `--allow`
- `--max-attempts`, default `3`
- `--check-timeout`, default `300` seconds per deterministic check

For a valid PASS, provide at least one `--check`. A reviewer PASS without deterministic checks must not be treated as success.

## Agent Config

Agents are shell commands that read a JSON prompt on stdin and write JSON to stdout.

Fixture config:

```toml
[explorer]
cmd = ["{python}", "{skill_dir}/tests/fixtures/explorer_agent.py"]
writes = false
timeout_seconds = 60

[coder]
cmd = ["{python}", "{skill_dir}/tests/fixtures/coder_agent.py"]
writes = true
timeout_seconds = 60

[code-reviewer]
cmd = ["{python}", "{skill_dir}/tests/fixtures/code_reviewer_agent.py"]
writes = false
timeout_seconds = 60
```

Role rules:

- `explorer` must be read-only.
- `coder` may edit files.
- `code-reviewer` must be read-only.
- The harness enforces reviewer read-only behavior by comparing the repository diff before and after review.
- The harness does not pass `.loop` artifact paths such as `LOOP_RUN_DIR`, `LOOP_CHECKS_JSON`, or `diff_path` to agents. Reviewer input receives `diff_text` and check summaries inline.

## Stop Rules

The harness writes `final-receipt.json` and exits after one of these terminal states:

- `PASS`: all checks returned `0`, code-reviewer returned `PASS`, reviewer did not edit files, changed files stayed within `--allow`, and attempts used did not exceed max attempts.
- `NEEDS_CHANGES`: max attempts were used without a valid PASS.
- `BLOCKED`: an agent failed or timed out, reviewer blocked, reviewer edited files, reviewer output was invalid, checks timed out, or changed files exceeded allowed scope.

Allowed `stop_reason` values for `loop.final_receipt.v1`:

```text
CODE_REVIEWER_PASS
CODE_REVIEWER_BLOCKED
MAX_ATTEMPTS
DISALLOWED_FILE_CHANGE
REVIEWER_EDITED_FILES
CHECK_FAILED
INVALID_REVIEWER_OUTPUT
AGENT_FAILED
TIMEOUT
```

`DISALLOWED_FILE_CHANGE` dominates other terminal reasons when final changed files are outside allowed globs.

## Receipt Contract

Every normal harness run writes:

```text
.loop/runs/<run_id>/
  request.json
  objective.md
  explorer/
    explorer-prompt.md
    explorer-stdout.txt
    explorer-stderr.txt
    explorer-result.json
  attempts/
    01/
      coder-prompt.md
      coder-stdout.txt
      coder-stderr.txt
      coder-result.json
      changed-files.txt
      checks.json
      checks/
        01.stdout
        01.stderr
      diff.patch
      code-reviewer-prompt.md
      code-reviewer-stdout.txt
      code-reviewer-stderr.txt
      code-reviewer-result.json
  final-receipt.json
```

Project agents must consume `final-receipt.json`, not subagent prose or stdout summaries.

Validate the receipt:

```bash
python skills/loop/scripts/validate_loop_receipt.py \
  .loop/runs/<run_id>/final-receipt.json \
  --print-summary
```

Validate changed-file scope when needed:

```bash
python skills/loop/scripts/check_changed_files.py \
  --include 'src/**' \
  --include 'tests/**'
```

## Project-Agent DAG Node

For Scillm/project-agent DAG integration, prefer the node runner instead of
calling `loop.py` directly. The node runner is the stable adapter between an
outer DAG node JSON and the inner loop harness:

```bash
python skills/loop/scripts/scillm_loop_node.py \
  --node .loop/nodes/<node_id>.json \
  --repo <disposable-worktree> \
  --print-json
```

Put node specs under `.loop/nodes/` or another ignored artifact directory. Do
not write `node.json` at repository root: `loop.py --require-clean` should fail
when non-artifact files make the worktree dirty.

### From Messy Human Prompt

`$loop` is not the prompt compiler or the whole project DAG. If the human gives
messy orchestration intent such as:

```text
use coder subagent write function
have code-reviewer subagent review the code
$loop N times until code-reviewer subagent passes the code
launch concurrent reviewer subagents, one security, one best-practices code
send back to project agent
```

the project agent or Scillm DAG compiler should:

1. Use `$interview` only if it cannot infer required scope, checks, target files, attempt budget, or reviewer lanes.
2. Compile exactly one write-capable repair node into `.loop/nodes/<node_id>.json`.
3. Run `skills/loop/scripts/scillm_loop_node.py` for that repair node, usually in a disposable worktree.
4. Validate the emitted node result and `final-receipt.json`.
5. Launch concurrent read-only outer DAG reviewer nodes for security and relevant `best-practices-*` code skills.
6. Aggregate loop receipt plus reviewer findings back to the project agent.

`$loop` must not launch the post-loop security or best-practices reviewers
itself. Those are outer DAG nodes. `$loop` returns the bounded repair truth
artifact that those later nodes consume.

Input:

```json
{
  "node_type": "loop",
  "node_id": "implement_parse_duration",
  "objective": "Implement parse_duration so parse_duration(\"1h 30m\") returns 5400.",
  "allowed_globs": ["sample-target/src/time/**", "sample-target/tests/**"],
  "required_changed_globs": ["sample-target/src/time/parse_duration.py"],
  "checks": ["python3 -m unittest discover -s sample-target/tests"],
  "max_attempts": 3,
  "check_timeout": 300,
  "agent_config": "skills/loop/examples/agents.scillm.toml",
  "worktree": {"mode": "existing"}
}
```

Output:

```json
{
  "schema": "loop.scillm_node_result.v1",
  "node_id": "implement_parse_duration",
  "status": "PASS|NEEDS_CHANGES|BLOCKED",
  "loop_final_verdict": "PASS|NEEDS_CHANGES|BLOCKED",
  "loop_run_id": "<run_id>",
  "final_receipt": ".loop/runs/<run_id>/final-receipt.json",
  "stop_reason": "<stop_reason>",
  "changed_files": [],
  "receipt_valid": true,
  "required_changed_globs_satisfied": true,
  "missing_required_changed_globs": []
}
```

Mapping:

- `PASS` means the outer DAG node may be marked complete after receipt validation and any `required_changed_globs` are satisfied.
- `NEEDS_CHANGES` means the outer DAG may retry the whole node if its own retry budget allows.
- `BLOCKED` means human input, upstream correction, missing dependency, or infrastructure repair is required.

`required_changed_globs` is optional but recommended when a DAG node must touch
a specific target file. `allowed_globs` only defines the maximum permitted edit
scope; it does not prove the intended file changed.

Scillm should use this shape for write-capable repair nodes:

```text
Scillm DAG node -> scillm_loop_node.py -> loop.py -> Scillm explorer/coder/reviewer workers -> final-receipt.json -> node result JSON
```

Read-only DAG nodes can call Scillm exec/OpenCode directly. Write-capable
repair nodes should call `scillm_loop_node.py` in a disposable worktree.

## Operating Rules

- Run real project-agent tasks in disposable git worktrees.
- Do not auto-merge, auto-push, auto-close issues, or install cron from this skill.
- Do not infer success from process return code alone; validate and inspect the receipt.
- Nonzero exit without a receipt is an infrastructure or preflight failure, not a subagent terminal result.

## Deferred

These are outside Phase 0:

- cron
- GitHub issue closure
- PR babysitting
- memory
- replay/events
- production unattended operation
- native Codex subagent proof
- malicious same-user sandboxing
