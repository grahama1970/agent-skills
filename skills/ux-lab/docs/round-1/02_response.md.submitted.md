# Clarify, Then Create Self-Contained ux-lab Skill

Attached creation bundle contains GOAL.md with the full scope.

The shared chat UI components (SharedChatShell, ComplianceChatWell, ThinkingTrace, MemoryTurnAdapter) currently live in pi-mono/ux-lab. They need to be extracted into agent-skills/skills/ux-lab/ so they're versioned alongside the skills ecosystem.

Key constraint: the source files are already committed to pi-mono at commit b98746993. This is an extraction + import relocation, not a rewrite.

Deliver one zip with MANIFEST.json, finished files, MIGRATION.md, PATCH_PLAN.md, prompt_improvements.md.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260624T184700Z:255f6afa>>>

Do not print anything after that marker.
