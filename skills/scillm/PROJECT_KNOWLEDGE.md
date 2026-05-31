# Project Knowledge: scillm

**Last updated:** 2026-05-30 21:19 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-05-25: scillm is the direct model-provider/proxy layer and may expose Codex App Server style agent handoff/turn APIs, but it is not itself the user-facing collaborator UX. For Nico-style visible collaborators, scillm/App Server is sufficient only if ask can retrieve and print the actual collaborator response text in the project-agent terminal and persist response artifacts/events. A state such as running/delivered without Nico discourse is not enough.
- 2026-05-30 debugger proof found warm-check was still parsing legacy model_name: text while live proxy config uses model_name: chutes-deepseek. warm_check.py now accepts current chutes-deepseek and legacy text profiles. Live ./skills/scillm/run.sh warm-check --json returns model deepseek-ai/DeepSeek-V3.2-TEE with switch_needed=false; /ask oc-kimi live smoke reached scillm backend and model_served opencode-go/kimi-k2.6.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-25 | Initialize project knowledge | Enable shared human/agent context |
| 2026-05-25 | Codex App Server may replace tmux only when it returns observable collaborator discourse | The human clarified that a separate tmux terminal is optional; reliability means the project agent can show Nico's response in the current terminal. Therefore scillm/Codex App Server should be preferred over PTY/tmux if it provides actual response text and artifact-backed turn state; otherwise ask must fail closed or use an explicit fallback, not hidden send-keys. |
| 2026-05-30 | warm-check default text model follows chutes-deepseek profile | The scillm public contract shifted away from generic text for production-shaped routing; warm-check must inspect the configured chutes-deepseek provider-family profile while retaining legacy text compatibility. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Agent Takeover Notes

- Current active work: none recorded yet
- Evidence pointers: none recorded yet
- Next action: identify current task and evidence before claiming readiness
- Blockers/caveats: none recorded yet
- Last verified command/artifact: none recorded yet
- Current active work: clarify and verify scillm/Codex App Server support for ask visible subagents. Evidence pointers: skills/scillm/SKILL.md streaming/thinking monitoring contract; scillm health endpoint http://localhost:4001/health returned 200 during this session; ask visible-subagent code posts to /v1/scillm/agents/{worker}/handoffs, /leases, /turn, and /steer. Next action: inspect/probe those agent endpoints for response text fields and event/log artifacts before declaring the App Server path reliable for Nico. Blockers/caveats: do not confuse transport liveness with collaborator discourse; running/heartbeat state is not a Nico answer. Last verified command/artifact: curl/httpx health probe returned /health 200 and /v1/scillm/health 200; /v1/scillm/agents/nico/handoffs OPTIONS returned 405, so endpoint behavior still needs direct POST proof.

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
