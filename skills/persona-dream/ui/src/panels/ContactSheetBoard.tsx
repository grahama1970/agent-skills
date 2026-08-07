/**
 * ContactSheetBoard, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { assetExtension, dreamAssetUrl } from '../lib/asset'
import { nvis } from '../styles'
import { MediaModal } from './MediaModal'

export function ContactSheetBoard({ stage }: { stage: DreamStage }) {
  const [requirementSheets, setRequirementSheets] = useState<ContactSheetRequirementAsset[]>([])
  const [previewSheet, setPreviewSheet] = useState<ContactSheetDisplayAsset | null>(null)
  const requirementsArtifact = stage.artifacts.find((artifact) => artifact.label.endsWith('contact_sheet_requirements.json'))
  useEffect(() => {
    let cancelled = false
    async function loadRequirementSheets() {
      if (!requirementsArtifact) {
        setRequirementSheets([])
        return
      }
      try {
        const response = await fetch(`/api/projects/dream/asset?path=${encodeURIComponent(requirementsArtifact.path)}`)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const payload = await response.json()
        const rows = Array.isArray(payload.requirements) ? payload.requirements : []
        const next = new Map<string, ContactSheetRequirementAsset>()
        rows.forEach((row: Record<string, unknown>) => {
          const entity = String(row.entity || '')
          const entityType = String(row.entity_type || '')
          const assets = Array.isArray(row.existing_assets) ? row.existing_assets : []
          assets.forEach((asset) => {
            if (!asset || typeof asset !== 'object') return
            const item = asset as Record<string, unknown>
            const rawUrl = String(item.url || item.source || '')
            const url = dreamAssetUrl(rawUrl)
            const id = String(item.asset_id || item.memory_key || rawUrl)
            if (!url || !id) return
            next.set(id, {
              id,
              url,
              label: String(item.title || entity || id),
              entity,
              entityType,
            })
          })
        })
        if (!cancelled) setRequirementSheets(Array.from(next.values()))
      } catch (error) {
        console.warn('Failed to load contact sheet requirements', error)
        if (!cancelled) setRequirementSheets([])
      }
    }
    void loadRequirementSheets()
    return () => { cancelled = true }
  }, [requirementsArtifact?.path])

  const sheets: ContactSheetDisplayAsset[] = stage.images.length > 0
    ? stage.images.map((img) => ({ id: img.path, url: img.url, label: img.label }))
    : requirementSheets
  const hasRequirementArtifacts = stage.artifacts.length > 0

  return (
    <div data-qid="contact-sheet-grid" style={nvis.contactSheetGrid}>
      {sheets.length > 0 ? sheets.map((sheet) => (
        <div
          key={sheet.id}
          className="contact-sheet-card"
          role="button"
          tabIndex={0}
          aria-label={`Open contact sheet preview for ${sheet.label}`}
          data-qid="dream:contact-sheet:card"
          data-qs-action="open-contact-sheet-preview"
          style={nvis.contactSheetCard}
          onClick={() => setPreviewSheet(sheet)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              setPreviewSheet(sheet)
            }
          }}
        >
          <img src={sheet.url} alt={sheet.label} style={nvis.contactSheetThumb} />
          {sheet.entity && (
            <div style={nvis.contactSheetCaption}>
              <span>{sheet.entity}</span>
              <span>{sheet.entityType}</span>
            </div>
          )}
          <div className="contact-sheet-overlay" style={nvis.contactSheetOverlay}>
            <button
              type="button"
              data-qid="dream:contact-sheet:open-preview"
              data-qs-action="open-contact-sheet-preview"
              style={nvis.contactSheetAction}
              onClick={(event) => {
                event.stopPropagation()
                setPreviewSheet(sheet)
              }}
            >
              Open Preview
            </button>
          </div>
        </div>
      )) : (
        <div style={nvis.contactSheetEmpty}>
          <span style={{ color: hasRequirementArtifacts ? '#a7f3d0' : '#ff4444', marginBottom: 8, fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            {hasRequirementArtifacts ? 'CONTACT_SHEET_REQUIREMENTS_READY' : 'NO_CONTACT_SHEETS'}
          </span>
          {hasRequirementArtifacts && (
            <span style={{ color: '#94a3b8', fontSize: 12, textAlign: 'center', maxWidth: 420, lineHeight: 1.5 }}>
              Phase 04 has a saved requirements contract. Existing character sheets and missing prop/environment reference sheets are listed in the JSON artifacts below.
            </span>
          )}
          <button
            type="button"
            data-qs-action="generate-sheets"
            style={nvis.contactSheetTrigger}
          >
            Trigger Contact Sheet Agent
          </button>
        </div>
      )}
      {previewSheet && (
        <MediaModal url={previewSheet.url} mediaType="png" onClose={() => setPreviewSheet(null)} />
      )}
    </div>
  )
}
