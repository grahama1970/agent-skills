/**
 * ChatWell — shared chat entry point for SPARTA Explorer, Embry Terminal, and PersonaPlex.
 *
 * - `mode="compliance"` (default): full evidence-case chat UX (RecallCard, GateChain, HUD input)
 * - `mode="personaplex"`: voice + golden_state_server tool trace via PersonaPlexChatWell
 */
import type { ReactNode } from 'react'
import { ComplianceChatWell } from './ComplianceChatWell'
import type { ComplianceChatWellProps } from './ComplianceChatWell'
import { PersonaPlexChatWell } from './PersonaPlexChatWell'
import type { PersonaPlexChatWellProps } from './PersonaPlexChatWell'
import type { PersonaPlexChatMode } from './personaplexProtocol'

export type { ComplianceChatWellProps, StreamingStep } from './ComplianceChatWell'
export type { ChatMessage, ThreatMatrixSummary, EntityRef, EvidenceGate, CascadeLayer } from './types'

type PersonaPlexOnlyProps = Pick<
  PersonaPlexChatWellProps,
  | 'wsUrl'
  | 'personaId'
  | 'sessionId'
  | 'deepgramApiKey'
  | 'showModeToggle'
  | 'showTracePanel'
  | 'title'
  | 'placeholder'
  | 'defaultMode'
  | 'onModeChange'
  | 'initialMessages'
  | 'initialTraceRows'
  | 'piChat'
>

/** Props accepted by every project chat surface. Compliance props pass through in compliance mode. */
export type ChatWellProps = ComplianceChatWellProps & PersonaPlexOnlyProps & {
  mode?: PersonaPlexChatMode
} & Record<string, unknown>

function pickPersonaPlexProps(props: ChatWellProps): PersonaPlexChatWellProps {
  const {
    mode: _mode,
    messages,
    onFeedback: _onFeedback,
    onClarifyClick: _onClarifyClick,
    onRunEvidenceCase: _onRunEvidenceCase,
    evidenceCaseLoading: _evidenceCaseLoading,
    onNavigateMatrix: _onNavigateMatrix,
    skills: _skills,
    composerPlaceholder: _composerPlaceholder,
    surfaceVariant: _surfaceVariant,
    onEntityClick: _onEntityClick,
    starterQuestions: _starterQuestions,
    preSignoffWarning: _preSignoffWarning,
    starterMode: _starterMode,
    isStreaming,
    streamingSteps,
    renderExtras: _renderExtras,
    renderAvatar: _renderAvatar,
    wsUrl,
    personaId,
    sessionId,
    deepgramApiKey,
    showModeToggle,
    showTracePanel,
    title,
    placeholder,
    defaultMode,
    onModeChange,
    initialMessages,
    initialTraceRows,
    piChat,
    ...ignored
  } = props

  void ignored

  return {
    mode: 'personaplex',
    wsUrl,
    personaId,
    sessionId,
    deepgramApiKey,
    showModeToggle,
    showTracePanel,
    title,
    placeholder,
    defaultMode,
    onModeChange,
    initialMessages,
    initialTraceRows,
    piChat,
    messages: messages?.map((msg, index) => ({
      id: msg.id ?? `msg-${index}`,
      role: msg.role === 'agent' ? 'assistant' : msg.role,
      content: msg.content,
    })),
    isStreaming,
    streamingSteps: streamingSteps as ReactNode,
  }
}

export function ChatWell(props: ChatWellProps) {
  const { mode = 'compliance' } = props
  if (mode === 'personaplex') {
    return <PersonaPlexChatWell {...pickPersonaPlexProps(props)} />
  }
  const { mode: _mode, wsUrl: _wsUrl, personaId: _personaId, sessionId: _sessionId, deepgramApiKey: _deepgramApiKey, showModeToggle: _showModeToggle, showTracePanel: _showTracePanel, title: _title, placeholder: _placeholder, defaultMode: _defaultMode, onModeChange: _onModeChange, initialMessages: _initialMessages, initialTraceRows: _initialTraceRows, piChat: _piChat, ...complianceProps } = props
  return <ComplianceChatWell {...complianceProps} />
}

export default ChatWell
