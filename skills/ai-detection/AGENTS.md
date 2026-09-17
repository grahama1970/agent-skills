# Agent contract

Read README, docs/PROJECT_KNOWLEDGE.md, immutable_goal.json, and the specs before
changing code. The immutable goal is a draft; do not invent an owner signature.

Keep author attribution, competence assessment, and policy decisions separate.
Never claim native skill execution from a locally authored lookalike report.
Do not edit a test/oracle to hide a product defect. Record intentional test-contract
repairs, then freeze and replay the unchanged suite. Native agentic-evals owns its
own execution/mutation provenance; project verification is not a substitute.

Use uv + Typer + Loguru + httpx + Pydantic. No dynamic code execution, pickle,
secret logging, direct ArangoDB, remote model upload, or automatic penalties.
Maintain strict JSON representation and Unicode guards. Every module stays below
800 lines; use functions except state containers and validated record types.

At handoff use these fixed fields: Status, Summary, Verified, Needs-Human, Next,
Blockers, Artifacts. Missing real-world evidence is NOT_ESTABLISHED, not a PASS.
