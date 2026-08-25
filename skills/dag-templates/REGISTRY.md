# DAG Template Registry

Use this table when a project agent needs to pick a DAG primitive by task shape.
Run `./run.sh find "<intent>"` for machine-readable matching and `./run.sh show
<id>` before materializing.

| id | task shape | use when | slots |
| --- | --- | --- | --- |
| `immutable-goal-mvp-loop` | Goal-locked implementation/debugging loop with reviewer and escalation gates | The agent must make bounded MVP progress, stop thrashing, and escalate through `$brave-search` and `$ask` when blocked | `dag_id`, `goal_id`, `goal_hash`, `immutable_goal`, `target_repo`, `target` |

## Directory Contract

Every registry row points at one directory under `templates/`. A valid primitive
directory contains:

- `README.md`
- `dag.tau.dag.json`
- `ask-prompt.md`
- `phart-dag-chart.txt`
- `agentic_eval.json`

The JSON registry is the source of truth for paths and slots. This Markdown
file is the fast scan surface for humans and project agents.
