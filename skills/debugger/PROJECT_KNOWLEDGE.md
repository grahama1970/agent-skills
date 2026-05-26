# Project Knowledge: debugger

**Last updated:** 2026-05-26 17:46 by agent
**Status:** Active development

## Current Understanding

- `$debugger` exists to stop project agents from patching from inference when
  live runtime state is available. The core contract is: state the uncertainty,
  set focused breakpoints, stop in the real path, inspect paused variables, then
  patch only what the observed state justifies.
- The README should explain the gap in current LLM debugging: agents often react
  to stdout, stderr, logs, and stack traces after the fact, but those outputs do
  not reliably show variable state, branch choice, mutation timing, or adapter
  payloads at the moment the bug first appears.
- The debugger workflow is language-neutral at the human/agent contract level:
  the important artifact is paused variable state at a breakpoint. Language only
  determines the adapter used to stop the runtime and read the frame.
- Current first-class adapters are Python, TypeScript/JavaScript/Node, and Rust.
- The two README-level jobs are:
  1. Make the project agent prove runtime state before patching.
  2. Make human collaboration easy when a paused state needs semantic or product
     judgment.
- The visual direction is a vintage, photorealistic industrial "DEBUGGER"
  machine, front-facing enough to read as a memorable single object, similar in
  spirit to the `$ask` skill banner.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-26 | Initialize project knowledge | Enable shared human/agent context |
| 2026-05-26 | Add a public README for `$debugger` | The skill needs a human-readable explanation of why debugger access matters, not only the operational SKILL.md contract |
| 2026-05-26 | Use the vintage DEBUGGER machine banner direction | It has more character than a modern software-debugging image and matches the `$ask` README's memorable object style |
| 2026-05-26 | Keep README prose focused on runtime state, breakpoints, and collaboration | The user wanted the README to explain when the agent should use `$debugger`, when to collaborate with the human, and how breakpoints work |
| 2026-05-26 | Treat `$review-docs` as the better future name than `$review-readme` | README review is broader than prose: it should include rendered docs, image/link checks, examples, SKILL.md contradiction checks, and model prose review |
| 2026-05-26 | Promote Rust to first-class debugger support | The common project stack is Python + TypeScript + Rust, and the debugger proof model should be language-neutral for the agent and human |
| 2026-05-26 | Apply Kimi README/SKILL clarity review and `$best-practices-skills` constraints | Examples now use `$SKILL_DIR`, bridge behavior is explained plainly, debugger-tool failure is explicit, and bridge internals moved into a reference doc |

## Open Questions

- [ ] Should a new `$review-docs` skill be created to formalize README/docs
      review, using `$ask`, rendered CDP proof, link/image checks, command
      checks, and SKILL.md contradiction analysis?
- [ ] Can the exact Gemini-provided DEBUGGER image be added from a source file,
      or should the current generated banner remain the committed asset?
- [ ] Should unused header candidates be kept as alternatives or removed before
      broadcast?

## Agent Takeover Notes

- Current active work: finalize README/project knowledge/plan-iterate evidence,
  verify the rendered README in a browser, run focused sanity checks, then use
  `$skills-broadcast` to commit and push the debugger skill.
- Evidence pointers:
  - README: `README.md`
  - Banner: `docs/assets/debugger-banner.png`
  - Plan phase: `.plan-iterate/phase-01-debugger-docs-and-assets/`
  - Kimi review with actual file contents:
    `/tmp/ask-debugger-docs/debugger-readme-oc-kimi-review-inline-files/`
  - Kimi session:
    `/home/graham/.pi/sessions/ask/20260526_ask-7f94cc6300c8.jsonl`
  - Earlier GPT-5.5 high-reasoning code review:
    `/home/graham/workspace/experiments/agent-skills/skills/ask/.ask_artifacts/deep-review/20260526T204708Z/review.json`
  - Project-state quick report:
    `/tmp/debugger-project-state-quick.json`
- Next action: update the plan-iterate phase ledger, render README preview via
  CDP, run sanity checks, clean generated/transient artifacts, then broadcast.
- Blockers/caveats:
  - The chat-attached Gemini image is not available as a local file path in this
    workspace; current committed candidate is a generated vintage DEBUGGER banner
    with readable label.
  - Kimi's first review attempt was intentionally not accepted because it lacked
    README/SKILL source text. The accepted review is the inline-file run above.
  - A `$review-docs` skill does not yet exist.
- Last verified command/artifact:
  - `$ask oc-kimi` inline-file README/SKILL review returned: "No Critical, High,
    or Medium issues found"; low/nit edits were applied to README proof and
    collaboration wording.
  - WebGPT later identified Medium bridge status ownership/auditability issues;
    bridge status writes now use a shared lock plus atomic replace, and protocol
    tests cover superseded writes, malformed request quarantine behavior,
    retry-after-pending-race behavior, and custom-output error routing.
  - Real runtime E2E sanity now exists for Python, TypeScript, and Rust:
    `sanity-e2e.sh`, `sanity-e2e-typescript.sh`, and `sanity-e2e-rust.sh`.
  - Kimi's follow-up README/SKILL review found no blocking conceptual issues
    but requested portability and clarity changes: replace local absolute
    command paths, clarify what the VS Code bridge actually does, add debugger
    failure handling, and reduce implementation detail in SKILL.md.
  - `$best-practices-skills` was checked after that review. The relevant local
    constraints are valid frontmatter, explicit triggers/provides/composes,
    concise SKILL.md with details in references, behavioral sanity checks with
    positive/negative controls, and no heavy transient artifacts committed.

## Key Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Operational contract for when and how project agents must use debugger proof |
| `README.md` | Human-facing overview of why the debugger skill exists and how to use it |
| `docs/assets/debugger-banner.png` | Vintage photorealistic README header image |
| `scripts/capture_breakpoints.py` | Python breakpoint/local/watch capture harness |
| `scripts/write_vscode_launch.py` | Writes Python/debugpy VS Code launch configurations |
| `scripts/write_vscode_typescript_launch.py` | Writes TypeScript/Node/extension-host VS Code launch configurations |
| `scripts/write_vscode_rust_launch.py` | Writes Rust CodeLLDB-compatible VS Code launch configurations |
| `scripts/node_inspector_breakpoint_proof.mjs` | Captures real TypeScript paused locals through Node inspector |
| `scripts/request_vscode_bridge.py` | Writes visible VS Code bridge requests |
| `vscode-bridge/` | Companion VS Code extension bridge for visible debug-session control and DAP proof |
| `references/vscode-bridge.md` | Bridge implementation notes, status ownership rules, and current limitations |
| `sanity.sh` | Python harness sanity checks |
| `sanity-typescript.sh` | TypeScript launch writer sanity checks |
| `sanity-rust.sh` | Rust launch writer sanity checks |
| `sanity-e2e-typescript.sh` | Real TypeScript breakpoint/local-state E2E proof |
| `sanity-e2e-rust.sh` | Real Rust breakpoint/local-state E2E proof through rust-gdb |
| `sanity-bridge.sh` | Bridge protocol and smoke checks |
| `sanity-e2e.sh` | End-to-end breakpoint proof checks |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
