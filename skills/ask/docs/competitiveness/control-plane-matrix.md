# /ask Control Plane Competitiveness Matrix

Created: 2026-05-30

This matrix is the source-derived baseline for making `/ask` compelling against
LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, and custom orchestration control
planes. Claims are intentionally bounded to current local source and tests.

| Capability | /ask status | Current evidence | Competitive implication | Improvement path |
| --- | --- | --- | --- | --- |
| Natural language front door | Present | `SKILL.md` human chat examples; `src/ask/ask.py` CLI inference; `tests/test_human_chat_examples.py` | Stronger human-facing entrypoint than graph-first frameworks when the operator wants low ceremony. | Keep route decisions explicit so natural inference is inspectable. |
| Memory-first context | Present | `src/ask/ask.py` calls memory recall before synthesis; `skills_exec.py`; runtime events | Differentiates from agent frameworks that leave retrieval wiring to app code. | Expose memory policy in route decisions and verifier citations. |
| Browser oracle lanes | Partial | `webgpt_runtime.py`, `cursor_browser_runtime.py`, browser alias tests, WebGPT/Cursor Browser docs | Differentiates by using authenticated user browser sessions with artifacts. | Add lane health probes and live evidence bundles per backend. |
| Typed adapter boundary | Partial | Separate runtime modules exist for WebGPT, Cursor Browser, Kimi, Perplexity, scillm | Better modularity than monolithic agent scripts, but response contracts are not yet uniform. | Normalize adapter request/response and failure taxonomy. |
| Route decision trace | Partial | CLI request artifacts capture normalized options; route decision artifact added by this plan slice | Competes with framework tracing by explaining why a lane was chosen. | Persist alternatives, unavailable reasons, and evidence policy for every run. |
| Run artifacts | Present | `AskRunState` writes request/status/events; `tests/test_run_state_protocol.py` | Strong audit trail compared with ad hoc agent transcripts. | Add artifact manifest and per-adapter invocation events. |
| Verifier gates | Partial | Deep-review verifier rules, argue verifier tests, runtime fail-closed states | Stronger than “agent said so” review loops when gates are deterministic. | Share verifier vocabulary across oracle/review/browser outputs. |
| Parallel and protocol review | Present | Parallel review, argue, roundtable, CAE gap review modes in `SKILL.md` and tests | Comparable to multi-agent frameworks for review breadth while retaining `/ask` artifacts. | Make reviewer selection and moderator synthesis traceable in status/events. |
| Worker execution | Not in scope | `/ask` delegates to `/orchestrate`, `/code-runner`, `/scillm`, or subagent adapters | Avoids becoming an unfocused framework clone. | Keep `/ask` as selector/composer/verifier, not implementation runner. |
| Live readiness reporting | Partial | `doctor`, `config doctor`, `sanity-e2e.sh --plan-only` | Competitive only if it fails closed on unknown browser/service state. | Add lane-level `available`, `needs_attention`, `unavailable`, `blocked`. |
| Competitor positioning docs | Missing | This file and plan `06_ASK_CONTROL_PLANE_COMPETITIVENESS_TASKS.yaml` start the baseline | Needed so users understand why `/ask` exists alongside frameworks. | Update `README.md` and `SKILL.md` after route/adapter evidence lands. |

## Current Slice Acceptance

- Every new competitive claim above names source files or marks the capability
  partial, missing, or out of scope.
- Route decisions are expected to appear in runtime request/status artifacts as
  `ask.route_decision.v1`.
- This matrix is not release evidence. Release evidence belongs in
  `docs/competitiveness/release-evidence.md` after deterministic tests and live
  lane proof bundles exist.
