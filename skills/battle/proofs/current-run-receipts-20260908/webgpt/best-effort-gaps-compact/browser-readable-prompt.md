Answer the request below directly and completely. Do not add roundtable or report scaffolding.
Handler: webgpt

Request:
You are WebGPT collaborating on the Battle skill closure review. My prior prompt was too narrow. Please do a best-effort adversarial audit, not just a binary verdict.

Review the attached bundle and answer with these exact sections:

1. VERDICT: MET, NEEDS_CHANGES, or NEEDS_HUMAN.
2. NEXT_STEPS: minimal ordered actions, or NONE if no action remains.
3. GAPS: any missing proof, stale proof, or unproven claim. Include NONE if no gaps.
4. HALLUCINATIONS_OR_OVERCLAIMS: claims in the supplied context that are not supported by the attached receipts/screenshot. Include NONE if none.
5. UX_SCREENSHOT_READBACK: what the attached Surf screenshot visibly proves and what it does not prove.
6. REPO_FILE_PATHS: list the repo-relative Battle files that matter and whether they should be committed/pushed.
7. CLARIFYING_QUESTIONS: ask only questions that block the next local action; otherwise NONE.

Immutable Battle goal: authorized Red/Blue security competition backend with Tau-owned provider subagents, Dogpile and memory research ingress, Docker-only target/exploit/patch execution, independent Judge replay, objective scorekeeping, adaptive lineage spawn/evaluate/select/promote loop, durable proof receipts, and arena-first sports/monster-boss commentary reports from receipts. Expanded goal: Pydantic-validated JSON receipts for arena, Red activity, Blue activity, and sports play-by-play commentary; commentary is schema-modeled event-log data citing arena/team receipt paths and exact Red/Blue activity indices; Markdown reports are downstream only. Pixi spectator replay must visibly bind to the exact backend adaptive-lineage receipt set but is supplementary, not backend readiness authority.

Current local facts supplied in attachments:
- current-status-check.json: current Battle status checker result.
- open-battle-issues.jsonl: open Battle issues after audit window.
- proof-summary.json: sanitized closure proof summary.
- battle-replay-live-ux.png: Surf screenshot of the live spectator UX.
- battle-diff-name-status.txt and battle-local-fixture.diff: repo-relative Battle working-tree file info.

If you recommend code changes, provide exact repo-relative path and minimal patch. If you recommend committing, say exactly which repo-relative paths to stage.


Local evidence attachments available to the browser model:
- ATTACHMENT_1: battle-webgpt-best-effort-compact.zip
Use the attached files as source material; do not rely on local filesystem paths.
