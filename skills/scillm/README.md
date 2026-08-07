# scillm

> **Disciplines:** model-ops

![Scillm card](../../docs/assets/project-cards/scillm.webp)

Scillm is the model and agent execution surface behind my agent work. It gives
project agents one path for any-model calls, image/VLM work, batch calls,
tool-call proposals, agent DAGs, and delegated coding workers without
scattering provider glue through every skill.

The full public project lives at
[github.com/grahama1970/scillm](https://github.com/grahama1970/scillm). This
skill is the agent-skills operator guide: start here when a skill needs to call
Scillm correctly.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start with |
|---|---|
| One model answer, JSON extraction, critique, or VLM description | `scillm <model> "prompt"` |
| A generated image artifact | `run.sh generate-image --prompt-file ... --out ...` |
| Many independent model calls | `scillm <model> prompts.jsonl` |
| A bounded worker that can inspect files or patch code | `scillm agent "task"` |
| A specific OpenCode model as a worker | `scillm agent opencode/<model> "task"` |
| Tool-call proposals for a caller-owned loop | `scillm --json --tools tools.json <model> "prompt"` |

Scillm also backs DAG-shaped workflows used by the harness: exec nodes,
OpenCode serve, transport streams, standing agents, receipts, retries, and
amendment.

Use those advanced surfaces only when the simple chat, image, batch, or delegate
paths are not enough.

## The Mental Model

```text
Project skill
  -> asks Scillm for the right surface
  -> Scillm routes to a provider, model, or worker
  -> caller validates the artifact, receipt, diff, or response
```

Scillm is deliberately more than a proxy wrapper. It normalizes provider
selection, OAuth-backed models, Chutes batches, OpenCode Go chat models,
OpenCode serve delegates, prompt gates, tool-call proposals, multimodal file
payloads, and proof receipts.

## Start Here

Run the project-agent doctor before relying on Scillm in a workflow:

```bash
cd /path/to/scillm
./scripts/doctor_project_agent_scillm_calls.sh
```

For day-to-day calls, prefer the CLI:

```bash
scillm "what is 2 + 2"
scillm openai/gpt-5.5 high "write a focused test plan"
scillm opencode/deepseek-v4-flash "summarize this failure"
scillm agent "inspect this repo and explain the failing test"
scillm --tools tools.json openai/gpt-5.5 "Use a tool if needed."
```

If the CLI is not on `PATH`, use the project source command and report the
resolution problem:

```bash
cd /path/to/scillm
PYTHONPATH=src uv run python -m scillm.cli tools check tools.json
```

## Common Mistakes

| Mistake | Better move |
|---|---|
| Hand-building provider headers in a skill | Route through Scillm |
| Asking chat to create an image file | Use the image surface |
| Using chat to patch a repo | Use a delegated agent |
| Treating a delegate response as truth | Verify artifacts, diffs, and receipts locally |
| Passing tools to `scillm agent` | Use `--tools` only for non-agent model calls |
| Stretching one chat call into a DAG runner | Use the harness or advanced transport path |

## Proof Discipline

Every Scillm-backed report should state:

```text
mocked: yes|no
live: yes|no
surface: chat|image|batch|delegate|advanced
model/agent: <name>
artifact paths: <receipts, images, diffs, logs, or response files>
unverified: <what was not checked>
```

Receipts and delegate messages are claims until the caller checks the returned
artifact or behavior.

## References

Load these only when the task needs that surface:

| File | Contents |
|---|---|
| [`references/models-and-routing.md`](references/models-and-routing.md) | Model aliases, routing, Chutes, and OpenCode Go notes |
| [`references/chat-calls.md`](references/chat-calls.md) | Single calls, JSON, VLM, and message formats |
| [`references/batch-calls.md`](references/batch-calls.md) | Parallel batch, server pools, and completion ordering |
| [`references/opencode-serve.md`](references/opencode-serve.md) | Bounded OpenCode worker runs |
| [`references/opencode-transport.md`](references/opencode-transport.md) | Transport streaming and DAG collaboration details |
| [`references/exec-workers.md`](references/exec-workers.md) | Maintainer-oriented `scillm exec` profiles |
| [`references/standing-agents.md`](references/standing-agents.md) | Multi-turn agent handoff workflow |
| [`references/files-multimodal.md`](references/files-multimodal.md) | Image, PDF, and ZIP payload shapes |
| [`references/ops-endpoints.md`](references/ops-endpoints.md) | Health, auth, providers, and capabilities |

The operational contract for project agents is [`SKILL.md`](SKILL.md).
