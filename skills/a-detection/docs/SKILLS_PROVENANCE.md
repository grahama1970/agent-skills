# Skills provenance and conformance boundaries

The following files were read through the connected GitHub tool on 2026-09-17.
Git blob identifiers below identify observed source, not an executed compliance PASS.

| Source | Observed blob / scope |
|---|---|
| skills/setup-project/SKILL.md | f733edf13469d713038b0fc2a73dbf26adf735d9 |
| skills/setup-project/scripts/setup_project.py | c3b19dff93a0951cf8f0349a8e7df268e9ca6e8e |
| skills/setup-project/run.sh | 19512ca8ab4717ea6d8baf3ecbe054873de5095a |
| skills/agentic-evals/SKILL.md | 449d39ecf6895af7966fdb2864771e93c490a409 |
| skills/agentic-evals/src/runner.py | e3ca5bbd0164e9ec80f310e964166935f39576e9; relevant initial source inspected |
| skills/agentic-evals/run.sh | 37b8bb102a5b2a4bb0d3108af5aa02b7c2541821 |
| skills/best-practices-python/SKILL.md | ca1f95228aa71a83d9215ee76799ed417530d62a |
| skills/best-practices-skills/SKILL.md | contract read; the source preview did not provide a reliably retained blob ID |

Repository: https://github.com/grahama1970/agent-skills

## Applied requirements

The project has a src package, explicit dependencies, uv wrappers, Typer CLI,
Loguru error handling, httpx with finite timeouts, pathlib paths, timezone-aware
receipts, strict Pydantic boundaries, safe model serialization, no runtime asserts,
a thin `__init__.py`, a declarative container handoff, and bounded modules.

The skill wrapper declares folded YAML description, triggers, provides, composes
and complies. It delegates to the owning setup/evaluation skills. The browser-oracle
registry contains no personal tab IDs and is explicitly an unbound registry,
not proof of a completed independent browser review.

The setup config retains the source brief, machine-readable policy/requirements,
a draft immutable goal, and the required client contract gate. No fabricated
acceptance-contract, Battle, create-report or human approval artifacts are supplied.

## Not established

The native skills checkout was accessible for reading through GitHub, not mounted
as an executable local environment. Native adapters were attempted and report the
missing prerequisite. Native fixture validation, claim grading, coverage auditing,
regression-chain qualification and the full release chain are not claimed to have
run. This is a concrete integration handoff, not a full compliance certification.

Likewise Ruff/clean uv/Docker/real model weights were not available in the build
runtime. The retained local structural checks supplement, but do not impersonate,
the native scanners and do not establish every rule in either best-practices skill.
