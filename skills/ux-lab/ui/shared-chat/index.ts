// Sparta Explorer shared-chat family, vendored into ux-lab as the canonical
// agent-skills chat surface (#1247). Source of truth for chrome/behavior:
// sparta/explorer/src/components/shared-chat. Sparta-external hooks and cards
// live under ./_support so the family is self-contained.
export { ChatWell, default as ChatWellDefault } from './ChatWell'
export type { ChatWellProps } from './ChatWell'
export { ComplianceChatWell as ComplianceChatWellComponent, default as ComplianceChatWell } from './ComplianceChatWell'
export type { ComplianceChatWellProps, InputMode, StarterChip } from './ComplianceChatWell'
export { default as CompactChatInterface } from './CompactChatInterface'
export { default as CommandPalette } from './CommandPalette'
export type { GlobalCommandId } from './CommandPalette'
export { default as CodeBlockWithCopy } from './CodeBlockWithCopy'
export { default as ChatProcessingState } from './ChatProcessingState'
export { default as TerminalProcessingState } from './TerminalProcessingState'
export { MarkdownRenderer } from './MarkdownRenderer'
export { default as MessageFooter, MessageFooter as MessageFooterComponent } from './MessageFooter'
export type { MessageFooterProps } from './MessageFooter'
export { default as ThinkingTrace, ThinkingTrace as ThinkingTraceComponent } from './ThinkingTrace'
export type { ThinkingTraceProps, ThinkingTraceStep } from './ThinkingTrace'
export * from './thinkingTraceHelpers'
export * from './memory-turn'
export * from './evidenceCaseReceipt'
export { highlightEntities } from './highlightEntities'
export type {
  ActivityEvent,
  Agent,
  AgentSuggestion,
  Artifact,
  CascadeLayer,
  EntityRef,
  EntityType,
  EvidenceCaseData,
  EvidenceGate,
  ReasoningStep,
  RecallItem,
  RecallResult,
  Skill,
  ThreatMatrixSummary,
} from './types'
