// Typed surface of @agent-skills/ux-lab-ui (skills/ux-lab/ui) as consumed here.
// Runtime resolution is the Vite alias in vite.config.ts; this shim keeps our
// strict tsconfig from linting the shared package's sources with our flags.
// Keep in sync with skills/ux-lab/ui/shared-chat/ (the vendored Sparta
// Explorer chat family, #1247) — ComplianceChatWell.tsx and memory-turn/.
declare module '@ux-lab/ui/ChatWell' {
  import type { ComponentType } from 'react'

  export interface ChatMessage {
    id: string
    role: 'user' | 'assistant' | 'system' | 'agent' | 'error'
    content: string
    createdAt: string
    title?: string
    footer?: string
    skillUsed?: string
    evidenceCase?: boolean
    thinkingTrace?: { id: string; label: string; status: string }[]
    reasoningSteps?: { id: string; label: string; status: string }[]
  }

  export interface StarterChip {
    label: string
    prompt: string
    dataQid?: string
  }

  export interface ChatWellProps {
    messages?: ChatMessage[]
    isStreaming?: boolean
    streamingSteps?: { id: string; label: string; status: string }[]
    liveAssistantMessage?: ChatMessage
    onSend?: (text: string) => void | Promise<void>
    placeholder?: string
    disabled?: boolean
    composerDisabled?: boolean
    showComposer?: boolean
    emptyTitle?: string
    emptyDescription?: string
    starterChips?: StarterChip[]
    actionSlot?: React.ReactNode
    qid?: string
    surface?: string
    className?: string
    voiceEnabled?: boolean
    voiceStatus?: 'off' | 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
    voiceLabel?: string
    onVoiceToggle?: (enabled: boolean) => void
    chatTitle?: string
    projectLabel?: string
    hideHeader?: boolean
    agentStatus?: 'idle' | 'processing' | 'ready'
  }

  export const ChatWell: ComponentType<ChatWellProps>
}
