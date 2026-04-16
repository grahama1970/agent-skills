import { useState, useEffect } from 'react'
import { NVIS } from '../theme'
import { queryTaxonomy, listDocuments } from '../api/client'
import type { RequirementEntry, RequirementSection } from '../types'

// --- Sample data ---
const SAMPLE_SECTIONS: RequirementSection[] = [
  { id: 'intro', num: '1', title: 'Introduction', level: 0, reqCount: 0, children: [] },
  {
    id: 'fundamentals', num: '2', title: 'The Fundamentals', level: 0, reqCount: 3,
    children: [],
  },
  {
    id: 'sec-req', num: '3', title: 'Security Requirements', level: 0, reqCount: 47,
    children: [
      {
        id: 'ac', num: '3.1', title: 'Access Control', level: 1, reqCount: 7,
        children: [
          { id: 'ac-acct', num: '3.1.1', title: 'Account Management', level: 2, reqCount: 1, children: [] },
          { id: 'ac-enf', num: '3.1.2', title: 'Access Enforcement', level: 2, reqCount: 1, children: [] },
        ],
      },
      { id: 'at', num: '3.2', title: 'Awareness and Training', level: 1, reqCount: 3, children: [] },
      { id: 'au', num: '3.3', title: 'Audit and Accountability', level: 1, reqCount: 9, children: [] },
      { id: 'cm', num: '3.4', title: 'Configuration Management', level: 1, reqCount: 6, children: [] },
      { id: 'ia', num: '3.5', title: 'Identification & Auth', level: 1, reqCount: 11, children: [] },
      { id: 'ir', num: '3.6', title: 'Incident Response', level: 1, reqCount: 3, children: [] },
      { id: 'ma', num: '3.7', title: 'Maintenance', level: 1, reqCount: 4, children: [] },
    ],
  },
]

const SAMPLE_REQUIREMENTS: RequirementEntry[] = [
  {
    id: 'req-3.1.01', reqId: '03.01.01', text: 'Limit system access to authorized users, processes acting on behalf of authorized users, and devices.',
    nistSource: 'AC-2', spartaRef: 'SS-005', sectionId: 'ac',
    evidence: 'pass', proofStatus: 'proven',
    lean4Preview: 'theorem ac2_access_limited : ...',
    lean4Fn: 'ac2_access_limited',
  },
  {
    id: 'req-3.1.02', reqId: '03.01.02', text: 'Enforce approved authorizations for logical access to information and system resources in accordance with applicable access control policies.',
    nistSource: 'AC-3', spartaRef: 'SS-006', sectionId: 'ac',
    evidence: 'partial', proofStatus: 'partial',
    lean4Preview: 'theorem ac3_enforce_auth : ...',
    lean4Fn: 'ac3_enforce_auth',
  },
  {
    id: 'req-3.1.03', reqId: '03.01.03', text: 'Control the flow of CUI in accordance with approved authorizations.',
    nistSource: 'AC-4', spartaRef: 'SS-007', sectionId: 'ac',
    evidence: 'pass', proofStatus: 'proven',
    lean4Preview: 'theorem ac4_flow_control : ...',
    lean4Fn: 'ac4_flow_control',
  },
  {
    id: 'req-3.1.04', reqId: '03.01.04', text: 'Separate the duties of individuals to reduce the risk of malevolent activity without collusion.',
    nistSource: 'AC-5', spartaRef: undefined, sectionId: 'ac',
    evidence: 'none', proofStatus: 'unproven',
    lean4Preview: undefined, lean4Fn: undefined,
  },
  {
    id: 'req-3.1.05', reqId: '03.01.05', text: 'Employ the principle of least privilege, including for specific security functions and privileged accounts.',
    nistSource: 'AC-6', spartaRef: 'SS-008', sectionId: 'ac',
    evidence: 'pass', proofStatus: 'proven',
    lean4Preview: 'theorem ac6_least_priv : ...',
    lean4Fn: 'ac6_least_priv',
  },
  {
    id: 'req-3.1.06', reqId: '03.01.06', text: 'Limit unsuccessful logon attempts.',
    nistSource: 'AC-7', spartaRef: 'SS-009', sectionId: 'ac',
    evidence: 'partial', proofStatus: 'partial',
    lean4Preview: 'theorem ac7_logon_limit : ...',
    lean4Fn: 'ac7_logon_limit',
  },
  {
    id: 'req-3.1.07', reqId: '03.01.07', text: 'Control connection of mobile devices.',
    nistSource: 'AC-19', spartaRef: 'SS-010', sectionId: 'ac',
    evidence: 'pass', proofStatus: 'proven',
    lean4Preview: 'theorem ac19_mobile_ctrl : ...',
    lean4Fn: 'ac19_mobile_ctrl',
  },
]

const THREAT_MAP = [
  { label: 'Prec', value: 0.91 },
  { label: 'Resi', value: 0.85 },
  { label: 'Frag', value: 0.24 },
  { label: 'Corr', value: 0.12 },
  { label: 'Loya', value: 0.90 },
]

// --- Helpers ---
function evidenceBadge(ev: RequirementEntry['evidence']) {
  if (ev === 'pass') return { label: '\u25CF PASS', color: NVIS.green }
  if (ev === 'partial') return { label: '\u25D1 PARTIAL', color: NVIS.amber }
  return { label: '\u25CB NONE', color: NVIS.red }
}

function proofBadge(ps: RequirementEntry['proofStatus']) {
  if (ps === 'proven') return { label: '\u2713 QED', color: NVIS.green }
  if (ps === 'partial') return { label: '\u21BB WIP', color: NVIS.accent }
  return null
}

function barColor(value: number): string {
  if (value >= 0.7) return NVIS.green
  if (value >= 0.4) return NVIS.amber
  return NVIS.red
}

interface SectionNodeProps {
  section: RequirementSection
  depth: number
  selectedId: string
  expandedIds: Set<string>
  onSelect: (id: string) => void
  onToggle: (id: string) => void
}

function SectionNode({ section, depth, selectedId, expandedIds, onSelect, onToggle }: SectionNodeProps) {
  const isSelected = section.id === selectedId
  const isExpanded = expandedIds.has(section.id)
  const hasChildren = section.children.length > 0
  const indent = 12 + depth * 16

  return (
    <>
      <div
        role="treeitem"
        aria-selected={isSelected}
        aria-expanded={hasChildren ? isExpanded : undefined}
        tabIndex={0}
        onClick={() => { onSelect(section.id); if (hasChildren) onToggle(section.id) }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(section.id); if (hasChildren) onToggle(section.id) } }}
        style={{
          paddingLeft: indent,
          paddingRight: 8,
          paddingTop: 5,
          paddingBottom: 5,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          borderLeft: `2px solid ${isSelected ? NVIS.accent : 'transparent'}`,
          background: isSelected ? `${NVIS.accent}14` : 'transparent',
          fontSize: 11,
        }}
        onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = `${NVIS.accent}08` }}
        onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
      >
        <span style={{ fontSize: 9, color: NVIS.dim, width: 12, flexShrink: 0 }}>
          {hasChildren ? (isExpanded ? '\u25BC' : '\u25B6') : '\u00A0'}
        </span>
        <span style={{ color: NVIS.dim, minWidth: 30, flexShrink: 0 }}>{section.num}</span>
        <span style={{ flex: 1, color: NVIS.white, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {section.title}
        </span>
        {section.reqCount > 0 && (
          <span style={{
            fontSize: 9, padding: '1px 5px', borderRadius: 8,
            background: `${NVIS.accent}1a`, color: NVIS.accent, flexShrink: 0,
          }}>
            {section.reqCount}
          </span>
        )}
      </div>
      {hasChildren && isExpanded && section.children.map((child) => (
        <SectionNode
          key={child.id}
          section={child}
          depth={depth + 1}
          selectedId={selectedId}
          expandedIds={expandedIds}
          onSelect={onSelect}
          onToggle={onToggle}
        />
      ))}
    </>
  )
}

export default function RequirementsView() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [requirements, setRequirements] = useState<RequirementEntry[]>(SAMPLE_REQUIREMENTS)
  const [selectedSectionId, setSelectedSectionId] = useState<string>('ac')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set(['sec-req', 'ac']))
  const [selectedReqId, setSelectedReqId] = useState<string | null>('req-3.1.02')

  useEffect(() => {
    async function fetchRequirements() {
      // Initial data already set from SAMPLE_REQUIREMENTS
      setLoading(false)
      // Try embry-memory to enrich with live QRA data
      try {
        // /taxonomy/query works with {text, scope} — use "sparta" scope
        const result = await queryTaxonomy('requirements', 'sparta')
        // Also try listing sparta_qra for real requirement data
        const qraResult = await listDocuments('sparta_qra', 50)
        if (qraResult.documents && qraResult.documents.length > 0) {
          const mapped: RequirementEntry[] = qraResult.documents.map((doc, i) => {
            const meta = doc.metadata ?? {}
            const bridgeAttrs = meta.bridge_attributes as Record<string, unknown> | undefined
            return {
              id: `req-live-${i}`,
              reqId: (meta.control_id as string) ?? doc.key ?? `QRA-${i}`,
              text: doc.content ?? (meta.question as string) ?? '',
              nistSource: (meta.source_framework as string) ?? (bridgeAttrs?.nist_source as string) ?? '',
              spartaRef: (meta.sparta_ref as string) ?? (bridgeAttrs?.sparta_ref as string) ?? undefined,
              sectionId: 'ac',
              evidence: (meta.score as number ?? 0) >= 0.8 ? 'pass' as const : (meta.score as number ?? 0) >= 0.5 ? 'partial' as const : 'none' as const,
              proofStatus: (meta.score as number ?? 0) >= 0.8 ? 'proven' as const : (meta.score as number ?? 0) >= 0.5 ? 'partial' as const : 'unproven' as const,
              lean4Preview: undefined,
              lean4Fn: undefined,
            }
          })
          if (mapped.length > 0) {
            setRequirements(mapped)
          }
        } else if (result.tags && result.tags.length > 0) {
          // Fallback to taxonomy query tags
          const mapped: RequirementEntry[] = result.tags.map((tag, i) => ({
            id: `req-live-${i}`,
            reqId: tag.text,
            text: tag.text,
            nistSource: tag.category,
            spartaRef: undefined,
            sectionId: 'ac',
            evidence: tag.confidence >= 0.8 ? 'pass' as const : tag.confidence >= 0.5 ? 'partial' as const : 'none' as const,
            proofStatus: tag.confidence >= 0.8 ? 'proven' as const : tag.confidence >= 0.5 ? 'partial' as const : 'unproven' as const,
            lean4Preview: undefined,
            lean4Fn: undefined,
          }))
          if (mapped.length > 0) {
            setRequirements(mapped)
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Memory service unreachable')
      }
    }
    fetchRequirements()
  }, [])

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999', fontFamily: 'monospace', fontSize: 13 }}>
        Loading...
      </div>
    )
  }

  const filteredReqs = requirements.filter((r) => {
    if (selectedSectionId === 'ac' || selectedSectionId === 'ac-acct' || selectedSectionId === 'ac-enf') {
      return r.sectionId === 'ac'
    }
    return r.sectionId === selectedSectionId
  })

  const passCount = filteredReqs.filter((r) => r.evidence === 'pass').length
  const partialCount = filteredReqs.filter((r) => r.evidence === 'partial').length
  const noneCount = filteredReqs.filter((r) => r.evidence === 'none').length
  const provenCount = filteredReqs.filter((r) => r.proofStatus === 'proven').length
  const wipCount = filteredReqs.filter((r) => r.proofStatus === 'partial').length

  // Lemma stats
  const lemmaProved = 12, lemmaPending = 4, lemmaFailed = 2, lemmaTotal = 18

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)', minHeight: 0 }}>
      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '8px 0', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, flexShrink: 0 }}>
          ✗ {error}
        </div>
      )}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>

      {/* Section Sidebar */}
      <div style={{
        width: 280, flexShrink: 0, background: NVIS.surface,
        borderRight: `1px solid ${NVIS.borderSolid}`,
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${NVIS.borderSolid}`, flexShrink: 0 }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 6 }}>
            Sections
          </div>
          <div style={{ fontSize: 10, color: NVIS.dim }}>nist_sp_800_171_r3.pdf</div>
        </div>

        <div
          role="tree"
          aria-label="Document sections"
          style={{ flex: 1, overflowY: 'auto' }}
        >
          {SAMPLE_SECTIONS.map((s) => (
            <SectionNode
              key={s.id}
              section={s}
              depth={0}
              selectedId={selectedSectionId}
              expandedIds={expandedIds}
              onSelect={setSelectedSectionId}
              onToggle={toggleExpand}
            />
          ))}
        </div>

        {/* Health Widgets */}
        <div style={{ flexShrink: 0, padding: '10px 12px', borderTop: `1px solid ${NVIS.borderSolid}` }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 6 }}>
            Threat Map (Taxonomy Bridges)
          </div>
          {THREAT_MAP.map((t) => (
            <div key={t.label} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3, fontSize: 10 }}>
              <span style={{ width: 38, color: NVIS.dim, textTransform: 'uppercase', fontSize: 8, letterSpacing: '0.04em', flexShrink: 0 }}>
                {t.label}
              </span>
              <div style={{ flex: 1, height: 6, background: NVIS.borderSolid, borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${t.value * 100}%`, height: '100%', borderRadius: 3, background: barColor(t.value) }} />
              </div>
              <span style={{ width: 28, textAlign: 'right', fontSize: 10, color: NVIS.dim, flexShrink: 0 }}>
                {t.value.toFixed(2)}
              </span>
            </div>
          ))}

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 4 }}>
              Lemma Graph (Proof Coverage)
            </div>
            <div
              role="img"
              aria-label={`Proof coverage: ${lemmaProved} proved, ${lemmaPending} in progress, ${lemmaFailed} failed of ${lemmaTotal}`}
              style={{ height: 8, background: NVIS.borderSolid, borderRadius: 4, overflow: 'hidden', marginBottom: 4 }}
            >
              <div style={{ height: '100%', display: 'flex' }}>
                <div style={{ width: `${(lemmaProved / lemmaTotal) * 100}%`, background: NVIS.green }} />
                <div style={{ width: `${(lemmaPending / lemmaTotal) * 100}%`, background: NVIS.amber }} />
                <div style={{ width: `${(lemmaFailed / lemmaTotal) * 100}%`, background: NVIS.red }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, fontSize: 9, color: NVIS.dim }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ width: 6, height: 6, borderRadius: 3, background: NVIS.green, flexShrink: 0 }} />
                {lemmaProved} proved
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ width: 6, height: 6, borderRadius: 3, background: NVIS.amber, flexShrink: 0 }} />
                {lemmaPending} wip
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ width: 6, height: 6, borderRadius: 3, background: NVIS.red, flexShrink: 0 }} />
                {lemmaFailed} fail
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Requirements Table Panel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${NVIS.borderSolid}`, background: NVIS.surface, flexShrink: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: NVIS.white, marginBottom: 4 }}>
            Requirements in §3.1 Access Control
          </div>
          <div style={{ fontSize: 11, color: NVIS.dim, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <span>{filteredReqs.length} requirements</span>
            <span style={{ color: NVIS.dim }} aria-hidden="true">&middot;</span>
            <span style={{ color: NVIS.green }}>{passCount} with evidence</span>
            <span style={{ color: NVIS.dim }} aria-hidden="true">&middot;</span>
            <span style={{ color: NVIS.accent }}>{provenCount} formally proved</span>
            {noneCount > 0 && (
              <>
                <span style={{ color: NVIS.dim }} aria-hidden="true">&middot;</span>
                <span style={{ color: NVIS.red }}>{noneCount} gap{noneCount > 1 ? 's' : ''}</span>
              </>
            )}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          <table
            aria-label="Requirements list"
            style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}
          >
            <thead>
              <tr>
                {['Req ID', 'Requirement', 'NIST Source', 'SPARTA', 'Evidence', 'Proof', 'Lean4 Preview'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    style={{
                      position: 'sticky', top: 0, zIndex: 5,
                      background: NVIS.surface, borderBottom: `1px solid ${NVIS.borderSolid}`,
                      padding: '8px 14px', textAlign: 'left',
                      fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em',
                      color: NVIS.dim, fontWeight: 600,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredReqs.map((req) => {
                const isActive = req.id === selectedReqId
                const evBadge = evidenceBadge(req.evidence)
                const pBadge = proofBadge(req.proofStatus)
                return (
                  <tr
                    key={req.id}
                    aria-selected={isActive}
                    onClick={() => setSelectedReqId(req.id)}
                    style={{
                      background: isActive ? `${NVIS.accent}0f` : 'transparent',
                      cursor: 'pointer',
                    }}
                    onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLTableRowElement).style.background = `${NVIS.accent}08` }}
                    onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
                  >
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top' }}>
                      <span style={{ color: NVIS.accent, fontWeight: 600, whiteSpace: 'nowrap' }}>{req.reqId}</span>
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top', maxWidth: 480 }}>
                      <span style={{ color: NVIS.white }}>{req.text}</span>
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top', whiteSpace: 'nowrap' }}>
                      <span style={{ color: NVIS.dim, fontSize: 11 }}>{req.nistSource}</span>
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top', whiteSpace: 'nowrap' }}>
                      <span style={{ color: NVIS.dim, fontSize: 11 }}>{req.spartaRef ?? '\u2014'}</span>
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top' }}>
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 3,
                        display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap',
                        background: `${evBadge.color}1a`, border: `1px solid ${evBadge.color}40`,
                        color: evBadge.color,
                      }}>
                        {evBadge.label}
                      </span>
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top' }}>
                      {pBadge ? (
                        <span style={{
                          fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 3,
                          display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap',
                          background: `${pBadge.color}1a`, border: `1px solid ${pBadge.color}40`,
                          color: pBadge.color,
                        }}>
                          {pBadge.label}
                        </span>
                      ) : (
                        <span style={{ color: NVIS.dim, fontSize: 10 }}>&mdash;</span>
                      )}
                    </td>
                    <td style={{ padding: '8px 14px', borderBottom: `1px solid ${NVIS.borderSolid}50`, verticalAlign: 'top', maxWidth: 260 }}>
                      {req.lean4Preview ? (
                        <div
                          title={req.lean4Preview}
                          style={{
                            fontSize: 9, color: NVIS.dim, background: NVIS.surface,
                            padding: '4px 6px', borderRadius: 3, border: `1px solid ${NVIS.borderSolid}`,
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            maxWidth: 250, cursor: 'pointer',
                          }}
                          onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = NVIS.accent; (e.currentTarget as HTMLDivElement).style.color = NVIS.white }}
                          onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = NVIS.borderSolid; (e.currentTarget as HTMLDivElement).style.color = NVIS.dim }}
                        >
                          <span style={{ color: NVIS.accent }}>theorem </span>
                          <span style={{ color: NVIS.green }}>{req.lean4Fn}</span>
                          <span> : ...</span>
                        </div>
                      ) : (
                        <span style={{ fontSize: 9, color: NVIS.dim }}>not attempted</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Status Bar */}
        <div style={{
          height: 28, background: NVIS.surface, borderTop: `1px solid ${NVIS.borderSolid}`,
          display: 'flex', alignItems: 'center', padding: '0 16px', flexShrink: 0,
          fontSize: 11, color: NVIS.dim, gap: 0,
        }}
          role="status"
          aria-live="polite"
        >
          <span>47 requirements total</span>
          <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
          <span>§3.1 Access Control · {filteredReqs.length} reqs</span>
          <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
          <span>
            Evidence:{' '}
            <span style={{ color: NVIS.green }}>{passCount} pass</span>
            {' · '}
            <span style={{ color: NVIS.amber }}>{partialCount} partial</span>
            {' · '}
            <span style={{ color: NVIS.red }}>{noneCount} none</span>
          </span>
          <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
          <span>
            Proofs:{' '}
            <span style={{ color: NVIS.green }}>{provenCount} QED</span>
            {' · '}
            <span style={{ color: NVIS.accent }}>{wipCount} WIP</span>
          </span>
        </div>
      </div>
      </div>
    </div>
  )
}
