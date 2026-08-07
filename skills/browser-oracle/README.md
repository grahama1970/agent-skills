# browser-oracle

> **Disciplines:** browser-automation · agentic-orchestration

Maps **directories → browser-oracle project names** (git) and **project names → tab id / URL** (machine-local `~/.pi`).

## Quick start

```bash
./run.sh bind oc-subagent-personas --tab-id 837352004 \
  --url 'https://chatgpt.com/c/…' --manual

./run.sh register --at ../oc-subagent --default oc-subagent-personas

./run.sh resolve --from ../oc-subagent/personas/mathematics --json
./run.sh doctor --from ../oc-subagent/personas/mathematics --json
```

Then `$ask webgpt … --webgpt-project oc-subagent-personas`.

## Walk-up

Registry discovery walks from `--from` toward `/`, same spirit as python-dotenv loading `.env` from parent directories. The nearest `.ask/browser-oracles.yaml` applies.

## Tests

```bash
./sanity.sh
uv run pytest -q
```
