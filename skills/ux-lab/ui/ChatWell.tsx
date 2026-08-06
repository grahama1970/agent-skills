// Canonical chat well — the Sparta Explorer shared-chat family (vendored under
// ./shared-chat, #1247). The legacy subset remains in ./ComplianceChatWell.tsx
// for SharedChatShell/PersonaPlex consumers; new consumers use this alias.
export { ComplianceChatWell as ChatWell, default } from './shared-chat/ComplianceChatWell'
export type { ComplianceChatWellProps as ChatWellProps, InputMode, StarterChip } from './shared-chat/ComplianceChatWell'
export type { ChatMessage, StreamingStep } from './shared-chat/memory-turn'
