/**
 * StoryboardConsole, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { acceptedStoryboardFrame, panelHasAcceptedStoryboardFrames, storyboardPanelPromptText, storyboardRecord, storyboardShotCode, storyboardStringList, storyboardTargetPanelIds } from '../lib/storyboard'
import { nvis } from '../styles'
import { StoryboardPanel } from './StoryboardPanel'
import { AlertTriangle, CheckCircle2, Image } from 'lucide-react'

export function StoryboardConsole({
  stage,
  projection,
  revisionQualified,
}: {
  stage: DreamStage
  projection?: StoryboardConsumerProjection
  revisionQualified: boolean
}) {
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const packetUrl = projection?.packetUrl

  useEffect(() => {
    let cancelled = false
    async function loadPacket() {
      try {
        setLoadError(null)
        if (!packetUrl) throw new Error('storyboard consumer projection missing from the active revision read model')
        const packetResponse = await fetch(packetUrl)
        if (!packetResponse.ok) throw new Error(`storyboard packet HTTP ${packetResponse.status}`)
        const payload = await packetResponse.json()
        if (!cancelled) {
          setPacket(payload)
        }
      } catch (error) {
        if (!cancelled) {
          setPacket(null)
          setLoadError(error instanceof Error ? error.message : String(error))
        }
      }
    }
    void loadPacket()
    return () => { cancelled = true }
  }, [packetUrl])

  const panels = Array.isArray(packet?.panels) ? packet.panels as Array<Record<string, unknown>> : []
  const targetPanelIds = storyboardTargetPanelIds(packet)
  const reviewPanels = targetPanelIds.length > 0
    ? panels.filter((panel) => targetPanelIds.includes(String(panel.panel_id ?? panel.id ?? '')))
    : panels
  const blockers = Array.isArray(packet?.missing_reference_blockers) ? packet.missing_reference_blockers as Array<Record<string, unknown>> : []
  const reviewBlockers = Array.isArray(packet?.review_blockers)
      ? packet.review_blockers.map(String).filter(Boolean)
      : []
  const candidates = Array.isArray(packet?.generated_candidate_panels) ? packet.generated_candidate_panels as Array<Record<string, unknown>> : []
  const panelsHaveAcceptedFrames = reviewPanels.length > 0 && reviewPanels.every(panelHasAcceptedStoryboardFrames)
  const reviewAccepted = Boolean(packet?.accepted) && String(packet?.review_status ?? packet?.status ?? '').includes('PASS')
  const packetStatus = String(packet?.review_status ?? packet?.status ?? (loadError ? 'MISSING_STORYBOARD_PACKET' : 'LOADING_STORYBOARD_PACKET'))
  const status = revisionQualified ? packetStatus : 'BLOCKED_REVISION_NOT_QUALIFIED'
  const isBlocked = !revisionQualified || /BLOCKED|MISSING|REJECTED|ERROR/i.test(status) || !panelsHaveAcceptedFrames || !reviewAccepted
  const targetLabel = targetPanelIds.length > 0 ? targetPanelIds.join(', ') : null
  const panelCountLabel = targetPanelIds.length > 0
    ? `${reviewPanels.length}/${panels.length || reviewPanels.length} target`
    : String(panels.length || '0')

  return (
    <section data-qid="dream:storyboard:console" style={nvis.storyboardConsole}>
      <style>{`
        details[data-storyboard-accordion] > summary::-webkit-details-marker {
          display: none;
        }
        details[data-storyboard-accordion] > summary::marker {
          content: "";
          font-size: 0;
        }
        summary[data-storyboard-accordion-header]:hover {
          background: rgba(255, 255, 255, 0.08) !important;
          color: #e5e7eb !important;
        }
        details[data-storyboard-accordion][open] [data-storyboard-accordion-chevron] {
          transform: rotate(180deg);
        }
      `}</style>
      <div style={nvis.storyboardHeader}>
        <div>
          <div style={nvis.storyboardEyebrow}>Animatic Storyboard</div>
          <h3 style={nvis.storyboardTitle}>
            {targetLabel ? `Targeted proof for ${targetLabel}` : 'Four timed panels for a 10-second video scene'}
          </h3>
        </div>
        <div style={nvis.storyboardMetaRow}>
          <span style={isBlocked ? nvis.storyboardStatusBlocked : nvis.storyboardStatusPass}>
            {isBlocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {status.replace(/_/g, ' ')}
          </span>
          <span style={nvis.storyboardMetaPill}>{panelCountLabel} panels</span>
          <span style={nvis.storyboardMetaPill}>{String(packet?.duration_seconds ?? '10')}s</span>
        </div>
      </div>

      {(loadError || isBlocked) && (
        <div style={nvis.storyboardBlockerBox}>
          <strong>Storyboard gate is not satisfied.</strong>
          <span>
            {loadError
              ? `Storyboard packet could not be loaded: ${loadError}.`
              : !revisionQualified
                ? 'The active revision is available for read-only inspection but has not passed revision qualification.'
              : reviewBlockers.length
                ? `Panel reviewer rejected this storyboard: ${reviewBlockers[0]}`
              : targetLabel
                ? `Targeted panel proof for ${targetLabel} requires reviewer-accepted start and end frames before it can pass.`
                : 'A single generated image is not a storyboard. Phase 07 requires multiple timed panels with text, references, coverage seed IDs, and reviewer acceptance.'}
          </span>
        </div>
      )}

      {reviewBlockers.length > 0 && (
        <div style={nvis.storyboardBlockerList}>
          <div style={nvis.storyboardBlockerTitle}>Panel reviewer blockers</div>
          {reviewBlockers.slice(0, 8).map((blocker, index) => (
            <div key={`${blocker}-${index}`} style={nvis.storyboardBlockerItem}>
              <div style={nvis.storyboardBlockerErrorText}>{blocker}</div>
              <div style={nvis.storyboardBlockerVerdict}>
                <span style={nvis.storyboardBlockerVerdictLabel}>Reviewer verdict</span>
                <span style={nvis.storyboardBlockerVerdictStatus}>{status}</span>
              </div>
            </div>
          ))}
          {reviewBlockers.length > 8 && (
            <div style={nvis.storyboardBlockerMore}>
              +{reviewBlockers.length - 8} additional reviewer blocker{reviewBlockers.length - 8 === 1 ? '' : 's'} in storyboard_review_verdict.json
            </div>
          )}
        </div>
      )}

      {blockers.length > 0 && (
        <div style={nvis.storyboardBlockerList}>
          <div style={nvis.storyboardBlockerTitle}>Reference blockers before image generation</div>
          {blockers.map((blocker, index) => (
            <div key={`${String(blocker.entity)}-${index}`} style={nvis.storyboardBlockerItem}>
              <span>{String(blocker.entity ?? 'Unknown entity')}</span>
              <small>{String(blocker.reason ?? 'Reference is missing')}</small>
            </div>
          ))}
        </div>
      )}

      {panels.length > 0 && (
        <div style={nvis.storyboardPanelGrid}>
          {panels.map((panel) => (
            <StoryboardPanel
              key={String(panel.panel_id ?? panel.shot)}
              panel={panel}
              projection={projection?.panels.find((candidate) => candidate.panelId === String(panel.panel_id ?? ''))}
            />
          ))}
        </div>
      )}

      {candidates.length > 0 && (
        <div style={nvis.storyboardCandidateStrip}>
          <div style={nvis.storyboardBlockerTitle}>Rejected generated candidate</div>
          {candidates.map((candidate) => {
            return (
              <div key={String(candidate.panel_id ?? candidate.path)} style={nvis.storyboardCandidateRow}>
                <div style={nvis.storyboardReferenceFallback}><Image size={16} /></div>
                <div>
                  <div style={nvis.storyboardCandidateStatus}>{String(candidate.status ?? 'REJECTED')}</div>
                  <div style={nvis.storyboardCandidateReason}>{String(candidate.reason ?? '')}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
