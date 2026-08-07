/**
 * MediaLockPanel, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { graphMediaSourceFromDocument, mediaLockFrameGroups, mediaLockFramesFromPacket, mediaLockGroupTimeRange, mediaLockStatusLabel } from '../lib/media'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { MediaLockFact } from './MediaLockFact'
import { StageEvidence } from './StageEvidence'

export function MediaLockPanel({ stage, projection }: { stage: DreamStage; projection?: StoryboardConsumerProjection }) {
  const packetUrl = projection?.packetUrl
  const [frames, setFrames] = useState<MediaLockFrame[]>([])
  const [packetStatus, setPacketStatus] = useState('loading accepted storyboard packet...')
  const frameGroups = mediaLockFrameGroups(frames)

  useEffect(() => {
    let cancelled = false
    async function loadPacket() {
      try {
        if (!packetUrl) throw new Error('storyboard packet missing from the active revision read model')
        const response = await fetch(packetUrl)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const packet = await response.json()
        const nextFrames = mediaLockFramesFromPacket(packet, projection)
        if (cancelled) return
        setFrames(nextFrames)
        setPacketStatus(nextFrames.length > 0
          ? `PASS_MEDIA_LOCK_SOURCE: ${nextFrames.length} accepted frames loaded from storyboard_packet.json`
          : 'BLOCKED_MEDIA_LOCK: storyboard_packet.json did not expose accepted frames')
      } catch (error) {
        if (cancelled) return
        setFrames([])
        setPacketStatus(`BLOCKED_MEDIA_LOCK_PACKET_LOAD: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    void loadPacket()
    return () => { cancelled = true }
  }, [packetUrl, projection?.revisionId])

  return (
    <section data-qid="dream:media-lock-panel" style={styles.mediaLockPanel}>
      <p style={styles.stageSummary}>{stage.summary}</p>
      {stage.failureOrGap && !isStagePassed(stage) && <div style={styles.gapBox}>{stage.failureOrGap}</div>}
      <div style={styles.mediaLockStatusBar}>
        <span>Accepted frame lock</span>
        <strong>{packetStatus}</strong>
      </div>
      {frames.length > 0 ? (
        <div style={styles.mediaLockGrid}>
          {frameGroups.map((group) => (
            <section key={group.panelId} style={styles.mediaLockFrameGroup}>
              <div style={styles.mediaLockGroupHeader}>
                <div style={styles.mediaLockGroupTitle}>
                  <strong>{group.panelId}</strong>
                  <span>{mediaLockGroupTimeRange(group.frames)} | {group.frames.length} locked frames</span>
                </div>
                <span style={styles.mediaLockLockedBadge}>LOCKED</span>
              </div>
              <div style={styles.mediaLockGroupFrames}>
                {group.frames.map((frame) => (
                  <article key={frame.id} style={styles.mediaLockFrame}>
                    <img src={frame.url} alt={`${frame.panelId} ${frame.role}`} style={styles.mediaLockThumb} />
                    <div style={styles.mediaLockFrameBody}>
                      <div style={styles.mediaLockFrameTitle}>
                        <strong>{frame.role.replace(/_/g, ' ')}</strong>
                      </div>
                      <div style={styles.mediaLockFacts}>
                        <MediaLockFact label="Status" value={mediaLockStatusLabel(frame.status)} title={frame.status} tone="pass" />
                        <MediaLockFact label="Identity" value={frame.identityStatus} tone="pass" />
                        <MediaLockFact label="Time" value={frame.timeLabel} />
                        <MediaLockFact label="SHA" value={frame.sha256} title={frame.sha256} hash />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div style={styles.gapBox}>Accepted storyboard frames are not available to the media-lock view yet.</div>
      )}
      <StageEvidence stage={{ ...stage, images: [] }} />
    </section>
  )
}
