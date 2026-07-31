# Battle Next MVP Competition Packet

Objective:
Choose the next smallest executable MVP-level proof rung that moves Battle from the current bounded local frontend/backend receipts toward a production-scope working front end and back end.

Immutable goal or acceptance bar:
Deliver production-scope Battle frontend and backend behavior with deterministic local receipts, beyond the prior local MVP proof.

Target repo/path:
/home/graham/workspace/experiments/agent-skills-main-clean on branch main. Battle lives under skills/battle. Do not propose work on any non-main branch or copied /tmp source tree.

Shared context:
The current committed evidence file is skills/battle/local/production-scope-v16-evidence-20260729.json. It reports status PARTIAL_PASS, mocked=false.

Frontend receipts:
- skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-v16/summary.json
- skills/battle/local/working-frontend-backend-20260729/pr8-integrated-main-after-v16/01-live-sse-adapter.png
- skills/battle/local/working-frontend-backend-20260729/test-interactions-live-after-patch/captures-live-route-v16-refresh/results.json

Frontend currently proved:
- Battle spectator renders the live local HTTP SSE adapter with EventSource transport, mocked=false, and seq 36/36.
- test-interactions exercises 38 live QID interactions with 0 failures and 0 warnings.

Backend receipts:
- skills/battle/local/production-scope-v16-memory-chain-postfilter-20260729/memory-chain-qualification.json
- skills/battle/local/production-scope-v16-live-topology-zipadapter-20260729/live-topology-qualification.json

Backend currently proved:
- Battle writes and exactly recalls one team-scoped measured RelayForge record through the production Memory API.
- A live Tau/SciLLM provider cites and uses the exact Memory record to change a Blue strategy artifact.
- One immutable nine-service RelayForge topology runs healthy for a live bounded Red/Blue campaign.
- Live Tau/SciLLM provider artifacts are converted into typed Battle-selected public actions and bound to private Judge measurements.

Current live topology receipt status:
- status=PASS
- mocked=false
- live=true
- closed_blocker=live-topology-not-qualified
- remaining_blockers=[]
- judge_verdict=CONTESTED
- production_readiness_proven=false
- claims.does_not_prove: Memory improved the Judge outcome; RelayForge or Battle is production ready; six-trial qualification, factorial effects, or cross-target generalization.

Remaining not proven in the project evidence:
- Production deployment.
- WebSocket transport.
- Unbounded swarm execution.
- Memory-improved Judge outcome.
- Battle or RelayForge production readiness.
- Six-trial qualification.
- Factorial effects.
- Cross-target generalization.

Constraints:
- Use only the main branch of agent-skills.
- Do not use scillm directly from the project agent; ask may route through Tau-owned transports.
- Do not use mocks or synthetic provider responses as final proof.
- Do not replace deterministic local receipts with reviewer prose.
- Keep the next rung MVP-level: one narrow command/artifact path that can be implemented and locally checked by the project agent.
- Prefer repairing or extending existing Battle scripts over new architecture.
- Avoid dashboard/status theater; frontend proof needs rendered screenshot or test-interactions receipts.
- If the proposed next rung needs a human decision, say exactly what decision is missing.

Question for isolated candidates:
What is the next MVP-level implementation challenge most likely to unblock the immutable goal, and what exact local patch and proof command should the project agent run first?

Expected candidate output:
APPROACH: concise strategy.
NEXT_MVP: one sentence naming the smallest proof rung.
WHY_THIS_FIRST: evidence-based reason this rung is the bottleneck.
CHANGES: exact files/functions/scripts likely to change.
PROOF_COMMANDS: exact commands and expected receipt paths.
ACCEPTANCE: deterministic pass criteria, including mocked/live boundary.
RISKS: likely failure signatures and how to fail closed.
BLOCKERS: only missing credential, authority, human decision, or external state.
VERIFIED_FEATURE: use only for a locally checkable candidate recommendation.

Forbidden claims:
Do not claim the immutable goal is complete. Do not claim Battle or RelayForge production readiness from the current bounded receipts. Do not propose broad new architecture unless no existing script can express the next proof rung.
