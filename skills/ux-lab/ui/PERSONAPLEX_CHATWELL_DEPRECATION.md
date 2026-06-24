# PersonaPlexChatWell production deprecation

`PersonaPlexChatWell.tsx` is gallery/reference only.

Production PersonaPlex chat must render through:

```text
SharedChatShell → PersonaPlexAdapter → ComplianceChatWell → ThinkingTrace → MessageFooter
```

Rules:

- Do not mount `PersonaPlexChatWell` from production routes.
- Do not reintroduce a parallel PersonaPlex grid or dedicated chat CSS path.
- Use lucide icons through SharedChatShell and ThinkingTrace.
- Keep NVIS token values in adapter metadata only; do not display raw values in MessageFooter.
