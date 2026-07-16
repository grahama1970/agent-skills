import React from 'react'
import { Clock3, Mic, Route, Shield, Sparkles } from 'lucide-react'
import type { ChatMessage, TurnBranch, UnknownRecord } from './memory-turn'
import { branchFromMessage, footerBranchLabel } from './thinkingTraceHelpers'

export interface MessageFooterProps {
  message: ChatMessage
  className?: string
}

export function MessageFooter({ message, className }: MessageFooterProps): JSX.Element | null {
  if (message.role !== 'assistant') return null

  const metadata = (message.metadata ?? {}) as UnknownRecord
  const branch = (branchFromMessage(message) ?? metadata.branch) as TurnBranch | undefined
  const tags = footerTags(message, metadata, branch)

  return (
    <footer
      className={className}
      data-qid="shared-chat:message-footer"
      data-branch={branch ?? 'assistant'}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 8,
        marginTop: 10,
        color: '#8995a8',
        fontSize: 11,
        lineHeight: 1.3,
      }}
    >
      <FooterIcon branch={branch} />
      {tags.map((tag) => (
        <span key={tag} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {tag}
        </span>
      ))}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <Clock3 size={12} strokeWidth={1.6} aria-hidden="true" />
        {formatTime(message.createdAt)}
      </span>
    </footer>
  )
}

function FooterIcon({ branch }: { branch?: TurnBranch }): JSX.Element {
  if (branch === 'personaplex') return <Mic size={13} strokeWidth={1.6} aria-hidden="true" />
  if (branch === 'watch') return <Sparkles size={13} strokeWidth={1.6} aria-hidden="true" />
  if (branch === 'evidence-case' || branch === 'compliance' || branch === 'aql') return <Shield size={13} strokeWidth={1.6} aria-hidden="true" />
  return <Route size={13} strokeWidth={1.6} aria-hidden="true" />
}

function footerTags(message: ChatMessage, metadata: UnknownRecord, branch?: TurnBranch): string[] {
  const tags: string[] = []
  const branchLabel = footerBranchLabel(branch)
  if (branchLabel) tags.push(branchLabel)
  if (message.skillUsed) tags.push(message.skillUsed)

  const answerModel = stringValue(metadata.answerModel ?? metadata.answer_model)
  if (answerModel) tags.push(`model ${answerModel}`)

  const reportPath = stringValue(metadata.reportPath ?? metadata.report_path)
  if (reportPath) tags.push(shortPath(reportPath))

  const personaId = stringValue(metadata.personaId ?? metadata.persona_id)
  if (personaId) tags.push(`persona ${personaId}`)

  const nvisTokens = metadata.nvisTokens ?? metadata.nvis_tokens
  if (nvisTokens && typeof nvisTokens === 'object') tags.push('NVIS tokens attached')

  const citations = metadata.citations
  if (Array.isArray(citations)) tags.push(`${citations.length} citations`)

  if (!tags.length) tags.push('assistant')
  return dedupe(tags)
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function shortPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : path
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function dedupe(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))]
}

export default MessageFooter
