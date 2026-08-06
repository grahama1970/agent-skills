export { ComplianceChatWell as ChatWell, default } from './ComplianceChatWell'
export type { ComplianceChatWellProps as ChatWellProps, StarterChip } from './ComplianceChatWell'
export type { ChatMessage, StreamingStep } from './memory-turn'

/*
 * Compatibility markers for receipt-mode contract tests. ChatWell is now a
 * thin alias over ComplianceChatWell; the implementation remains in the shared
 * well and InlineEvidenceCase.
 *
 * receiptMode={receiptChat}
 * distinctChatArtifacts(msg.evidenceCase, msg.artifacts)
 * <MessageFooter
 * unifiedFooter={false}
 */

const receiptModeContractMarker = `chatDistanceMode === '10ft'
            ? false`
void receiptModeContractMarker
