import React, { useCallback } from 'react'
import { AlertTriangle, ArrowRight, Database, FileText, Link2, Map, ShieldCheck, Terminal } from 'lucide-react'
import { useRegisterAction } from './_support/useRegisterAction'

type CapabilityCard = {
  id: string
  title: string
  description: string
  prompt: string
  qid: string
  action: string
  icon: React.ReactNode
}

const CAPABILITIES: CapabilityCard[] = [
  {
    id: 'supply-chain',
    title: 'Supply Chain Analysis',
    description: 'Map blast radii and identify vulnerable dependencies.',
    prompt: 'Analyze the blast radius of the most recent critical CVE against our active environments.',
    qid: 'shared-chat:empty:prompt:supply-chain',
    action: 'SHARED_CHAT_EMPTY_ANALYZE_SUPPLY_CHAIN',
    icon: <Link2 size={20} aria-hidden="true" />,
  },
  {
    id: 'sparta-map',
    title: 'SPARTA Coverage',
    description: 'Cross-reference logs with SPARTA threat matrices.',
    prompt: 'Map the dropped system logs to the SPARTA threat matrix to identify coverage gaps.',
    qid: 'shared-chat:empty:prompt:sparta-map',
    action: 'SHARED_CHAT_EMPTY_MAP_SPARTA_COVERAGE',
    icon: <Map size={20} aria-hidden="true" />,
  },
  {
    id: 'log-parse',
    title: 'Log Parsing',
    description: 'Extract IOCs and anomalies from raw text or JSON.',
    prompt: 'Extract all IP addresses and suspicious payloads from the attached configuration file.',
    qid: 'shared-chat:empty:prompt:log-parse',
    action: 'SHARED_CHAT_EMPTY_PARSE_LOGS',
    icon: <FileText size={20} aria-hidden="true" />,
  },
  {
    id: 'mitigation',
    title: 'Draft Mitigations',
    description: 'Generate remediation steps and firewall rules.',
    prompt: 'Draft an incident response mitigation plan based on the active threat.',
    qid: 'shared-chat:empty:prompt:draft-mitigations',
    action: 'SHARED_CHAT_EMPTY_DRAFT_MITIGATIONS',
    icon: <ShieldCheck size={20} aria-hidden="true" />,
  },
]

type EmbryEmptyStateProps = {
  onExecute: (prompt: string) => void
  voiceStatus?: 'off' | 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
  promptTemplates?: string[]
  onTemplateClick?: (template: string) => void
}

export default function EmbryEmptyState({
  onExecute,
  voiceStatus = 'off',
  promptTemplates = [],
  onTemplateClick,
}: EmbryEmptyStateProps): JSX.Element {
  useRegisterAction('shared-chat:empty:prompt:supply-chain', { app: 'sparta-explorer', action: 'SHARED_CHAT_EMPTY_ANALYZE_SUPPLY_CHAIN', label: 'Supply Chain Analysis', description: 'Run a supply-chain blast-radius starter prompt' })
  useRegisterAction('shared-chat:empty:prompt:sparta-map', { app: 'sparta-explorer', action: 'SHARED_CHAT_EMPTY_MAP_SPARTA_COVERAGE', label: 'SPARTA Coverage', description: 'Run a SPARTA coverage mapping starter prompt' })
  useRegisterAction('shared-chat:empty:prompt:log-parse', { app: 'sparta-explorer', action: 'SHARED_CHAT_EMPTY_PARSE_LOGS', label: 'Log Parsing', description: 'Run an IOC and anomaly extraction starter prompt' })
  useRegisterAction('shared-chat:empty:prompt:draft-mitigations', { app: 'sparta-explorer', action: 'SHARED_CHAT_EMPTY_DRAFT_MITIGATIONS', label: 'Draft Mitigations', description: 'Run a mitigation-drafting starter prompt' })
  useRegisterAction('shared-chat:empty:incident-investigate', { app: 'sparta-explorer', action: 'SHARED_CHAT_EMPTY_INVESTIGATE_INCIDENT', label: 'Investigate active incident', description: 'Run the active incident investigation starter prompt' })

  const executePrompt = useCallback((prompt: string) => {
    onExecute(prompt)
  }, [onExecute])

  return (
    <div
      data-qid="shared-chat:lean-in-empty"
      aria-label="Console empty state"
      style={{
        minHeight: '100%',
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 24px',
        fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        color: '#EDEDED',
      }}
    >
      <div style={{ width: '100%', maxWidth: 860, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32, textAlign: 'center' }}>
        <div style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
          <div
            aria-hidden="true"
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              display: 'grid',
              placeItems: 'center',
              background: 'rgba(0, 112, 243, 0.10)',
              color: '#3b82f6',
              border: '1px solid rgba(0, 112, 243, 0.22)',
            }}
          >
            <Terminal size={24} />
          </div>
          <div style={{ color: '#f8fafc', fontSize: 24, fontWeight: 700, letterSpacing: 0 }}>
            Sparta Console
          </div>
          <p style={{ margin: 0, color: '#94a3b8', fontSize: 14, lineHeight: 1.6, maxWidth: 560 }}>
            The console is ready. Select a core capability below to initiate an automated workflow, or enter a custom command to begin.
          </p>
        </div>

        {voiceStatus === 'error' && (
          <div
            data-qid="shared-chat:empty:incident"
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              padding: 14,
              border: '1px solid rgba(248, 81, 73, 0.45)',
              borderRadius: 8,
              background: 'rgba(248, 81, 73, 0.08)',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', gap: 10, minWidth: 0 }}>
              <AlertTriangle size={16} color="#ff7b72" aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ color: '#ff7b72', fontSize: 12, fontWeight: 700 }}>Active incident detected</div>
                <div style={{ color: '#cbd5e1', fontSize: 12, lineHeight: 1.45 }}>Console voice telemetry is degraded.</div>
              </div>
            </div>
            <button
              type="button"
              data-qid="shared-chat:empty:incident-investigate"
              data-qs-action="SHARED_CHAT_EMPTY_INVESTIGATE_INCIDENT"
              title="Investigate active incident"
              onClick={() => executePrompt('Investigate the active Console voice telemetry incident.')}
              style={{
                minHeight: 36,
                border: 0,
                borderRadius: 8,
                background: '#f85149',
                color: '#fff',
                padding: '0 12px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Investigate
            </button>
          </div>
        )}

        <div
          data-qid="shared-chat:empty:capabilities"
          style={{
            width: '100%',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: 16,
          }}
        >
          {CAPABILITIES.map((capability) => (
            <button
              key={capability.id}
              type="button"
              data-qid={capability.qid}
              data-qs-action={capability.action}
              title={capability.prompt}
              onClick={() => executePrompt(capability.prompt)}
              onMouseEnter={(event) => {
                event.currentTarget.style.background = '#1e293b'
                event.currentTarget.style.borderColor = '#64748b'
                const affordance = event.currentTarget.querySelector<HTMLElement>('[data-capability-affordance="true"]')
                if (affordance) affordance.style.opacity = '1'
                const icon = event.currentTarget.querySelector<HTMLElement>('[data-capability-icon="true"]')
                if (icon) {
                  icon.style.background = 'rgba(0, 112, 243, 0.10)'
                  icon.style.color = '#60a5fa'
                }
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.background = 'rgba(30, 41, 59, 0.40)'
                event.currentTarget.style.borderColor = 'rgba(51, 65, 85, 0.55)'
                const affordance = event.currentTarget.querySelector<HTMLElement>('[data-capability-affordance="true"]')
                if (affordance) affordance.style.opacity = '0'
                const icon = event.currentTarget.querySelector<HTMLElement>('[data-capability-icon="true"]')
                if (icon) {
                  icon.style.background = '#0A0A0A'
                  icon.style.color = '#94a3b8'
                }
              }}
              style={{
                width: '100%',
                minHeight: 178,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: 0,
                padding: 20,
                border: '1px solid rgba(51, 65, 85, 0.55)',
                borderRadius: 12,
                background: 'rgba(30, 41, 59, 0.40)',
                color: '#EDEDED',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'background-color 0.2s, border-color 0.2s',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, minWidth: 0 }}>
                <span
                  data-capability-icon="true"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 10,
                    display: 'grid',
                    placeItems: 'center',
                    background: '#0A0A0A',
                    color: '#94a3b8',
                    transition: 'background-color 0.2s, color 0.2s',
                    flexShrink: 0,
                  }}
                >
                  {capability.icon}
                </span>
                <span style={{ color: '#EDEDED', fontSize: 14, fontWeight: 650, minWidth: 0 }}>{capability.title}</span>
              </span>
              <span style={{ color: '#94a3b8', fontSize: 13, lineHeight: 1.55, flex: 1 }}>
                {capability.description}
              </span>
              <span
                data-capability-affordance="true"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  marginTop: 16,
                  color: '#3b82f6',
                  fontSize: 12,
                  fontWeight: 650,
                  opacity: 0,
                  transition: 'opacity 0.2s',
                }}
              >
                <span>Execute command</span>
                <ArrowRight size={14} aria-hidden="true" />
              </span>
            </button>
          ))}
        </div>

        {promptTemplates.length > 0 && (
          <div style={{ width: '100%', maxWidth: 560, textAlign: 'left' }}>
            <div style={{
              fontSize: 11,
              fontWeight: 700,
              color: '#64748b',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              marginBottom: 8,
            }}>
              Prompt Templates
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {promptTemplates.map((template, index) => (
                <button
                  key={`${template}-${index}`}
                  type="button"
                  data-qid={`shared-chat:prompt-template:${index}`}
                  data-qs-action="SHARED_CHAT_APPLY_TEMPLATE"
                  title={`Use prompt template: ${template}`}
                  onClick={() => onTemplateClick?.(template)}
                  style={{
                    width: '100%',
                    minHeight: 40,
                    borderRadius: 8,
                    border: '1px solid rgba(51, 65, 85, 0.55)',
                    background: 'rgba(15, 23, 42, 0.56)',
                    color: '#cbd5e1',
                    padding: '8px 12px',
                    fontSize: 12,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  {template}
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#64748b', fontSize: 11 }}>
          <Database size={13} aria-hidden="true" />
          <span>Evidence gating active. Check important telemetry.</span>
        </div>
      </div>
    </div>
  )
}
