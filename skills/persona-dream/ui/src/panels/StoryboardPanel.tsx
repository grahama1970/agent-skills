/**
 * StoryboardPanel, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { assetExtension, dreamAssetUrl } from '../lib/asset'
import {copyZipBlobToClipboard, crc32, downloadBlob, fnv1a32, writeUint16, writeUint32} from '../lib/binary'
import { acceptedStoryboardFrame, panelHasAcceptedStoryboardFrames, storyboardPanelPromptText, storyboardRecord, storyboardShotCode, storyboardStringList, storyboardTargetPanelIds } from '../lib/storyboard'
import {copyPanelBundleToDesktopClipboard, createStoredZip, fetchZipAsset, sanitizeZipName} from '../lib/zip'
import { nvis } from '../styles'
import { StoryboardPromptBlock } from './StoryboardPromptBlock'
import { StoryboardSupportBlock } from './StoryboardSupportBlock'
import { Camera, ChevronDown, ClipboardCheck, Copy, Image } from 'lucide-react'

export function StoryboardPanel({
  panel,
  projection,
}: {
  panel: Record<string, unknown>
  projection?: StoryboardPanelProjection
}) {
  const [copyStatus, setCopyStatus] = useState('')
  const range = panel.time_range && typeof panel.time_range === 'object' ? panel.time_range as Record<string, unknown> : {}
  const references = Array.isArray(panel.references) ? panel.references as Array<Record<string, unknown>> : []
  const seeds = Array.isArray(panel.coverage_seed_ids) ? panel.coverage_seed_ids.map(String) : []
  const entities = Array.isArray(panel.required_entities) ? panel.required_entities.map(String) : []
  const startFrame = storyboardRecord(panel.start_frame)
  const endFrame = storyboardRecord(panel.end_frame)
  const cameraPlan = storyboardRecord(panel.camera)
  const lightingPlan = storyboardRecord(panel.lighting)
  const productionNotes = storyboardRecord(panel.production_notes)
  const generationPrompt = storyboardRecord(panel.generation_prompt)
  const actingBeats = storyboardStringList(panel.acting_beats)
  const primaryFrame = acceptedStoryboardFrame(startFrame) || acceptedStoryboardFrame(endFrame)
  const primaryReferenceUrl = projection?.startFrame.url ?? projection?.endFrame.url ?? ''
  const timeLabel = `${String(range.start_s ?? '?')}-${String(range.end_s ?? '?')}`
  const shotText = String(panel.shot ?? 'Missing shot direction')
  const shotCode = storyboardShotCode(shotText)
  const copyPanelPayload = async () => {
    setCopyStatus('Building')
    const payload = {
      schema: 'persona_dream.storyboard_panel_prompt_payload.v1',
      panel_id: panel.panel_id ?? null,
      time_range: range,
      shot: panel.shot ?? null,
      action: panel.action ?? null,
      dialogue: panel.dialogue ?? null,
      required_entities: entities,
      coverage_seed_ids: seeds,
      references,
      start_frame: startFrame,
      end_frame: endFrame,
      camera: cameraPlan,
      lighting: lightingPlan,
      acting_beats: actingBeats,
      production_notes: productionNotes,
      generation_prompt: generationPrompt,
      accepted_frame: primaryFrame || null,
    }
    const panelId = sanitizeZipName(String(panel.panel_id ?? 'storyboard-panel'))
    const jsonPayload = JSON.stringify(payload, null, 2)
    const textPayload = storyboardPanelPromptText(payload)
    const checklistPayload = JSON.stringify(storyboardReviewerChecklist, null, 2)
    const manifestPayload = JSON.stringify({
      schema: 'persona_dream.storyboard_panel_clipboard_bundle.v1',
      panel_id: panel.panel_id ?? null,
      created_at: new Date().toISOString(),
      includes: [
        'panel_prompt_payload.json',
        'panel_prompt_payload.txt',
        'panel_reviewer_checklist.json',
        'accepted_frame/* when available',
        'references/* when available',
      ],
    }, null, 2)
    const filename = `${panelId}-prompt-payload.zip`
    const serverEntries: Array<Record<string, string>> = [
      { name: 'panel_prompt_payload.json', text: jsonPayload },
      { name: 'panel_prompt_payload.txt', text: textPayload },
      { name: 'panel_reviewer_checklist.json', text: checklistPayload },
      { name: 'manifest.json', text: manifestPayload },
    ]
    if (primaryFrame) {
      const raw = String(primaryFrame.path || primaryFrame.image_path || '')
      const extension = assetExtension(raw)
      serverEntries.push({ name: `accepted_frame/${panelId}-accepted-frame.${extension}`, path: raw })
    }
    references.forEach((reference, index) => {
      const raw = String(reference.path || reference.url || '')
      if (!raw || raw.startsWith('http')) return
      const label = sanitizeZipName(String(reference.id ?? reference.title ?? `reference-${index + 1}`))
      const extension = assetExtension(raw)
      serverEntries.push({ name: `references/${String(index + 1).padStart(2, '0')}-${label}.${extension}`, path: raw })
    })

    try {
      const serverCopied = await copyPanelBundleToDesktopClipboard(filename, serverEntries)
      if (serverCopied) {
        setCopyStatus('Copied zip')
        window.setTimeout(() => setCopyStatus(''), 1600)
        return
      }
    } catch {
      // Fall through to browser-only zip/download fallback when the local API is unavailable.
    }

    const entries: ZipFileEntry[] = [
      {
        name: 'panel_prompt_payload.json',
        data: textEncoder.encode(jsonPayload),
      },
      {
        name: 'panel_prompt_payload.txt',
        data: textEncoder.encode(textPayload),
      },
      {
        name: 'panel_reviewer_checklist.json',
        data: textEncoder.encode(checklistPayload),
      },
      {
        name: 'manifest.json',
        data: textEncoder.encode(manifestPayload),
      },
    ]

    const imageEntries = await Promise.all([
      primaryFrame ? fetchZipAsset(
        String(primaryFrame.path || primaryFrame.image_path || ''),
        `accepted_frame/${panelId}-accepted-frame`,
      ) : Promise.resolve(null),
      ...references.map((reference, index) => {
        const raw = String(reference.path || reference.url || '')
        const label = sanitizeZipName(String(reference.id ?? reference.title ?? `reference-${index + 1}`))
        return fetchZipAsset(raw, `references/${String(index + 1).padStart(2, '0')}-${label}`)
      }),
    ])
    entries.push(...imageEntries.filter(Boolean) as ZipFileEntry[])

    const zip = createStoredZip(entries)
    const copied = await copyZipBlobToClipboard(zip)
    if (!copied) downloadBlob(zip, filename)
    setCopyStatus(copied ? 'Copied zip' : 'Downloaded')
    window.setTimeout(() => setCopyStatus(''), 1600)
  }

  return (
    <article data-qid="dream:storyboard:panel" style={nvis.storyboardPanelCard}>
      <div style={nvis.storyboardFrame}>
        {primaryReferenceUrl ? (
          <img
            src={primaryReferenceUrl}
            alt={String(panel.panel_id ?? 'accepted storyboard frame')}
            style={nvis.storyboardFrameImage}
          />
        ) : (
          <div style={nvis.storyboardFrameMissing}>
            <span style={nvis.storyboardFrameGuideLabel}>{String(panel.panel_id ?? 'panel')} · {shotCode}</span>
            <span style={nvis.storyboardFrameGuideLine}>Storyboard frame pending</span>
            <small>Start and end frame specs below</small>
          </div>
        )}
        <div style={nvis.storyboardFrameShade} />
        <div style={nvis.storyboardFrameTop}>
          <span style={nvis.storyboardPanelId}>{String(panel.panel_id ?? 'panel')} · {timeLabel}</span>
          <div style={nvis.storyboardPanelFrameActions}>
            <button
              type="button"
              data-qid={`dream:storyboard:copy-panel:${String(panel.panel_id ?? 'panel')}`}
              title="Copy full panel prompt payload"
              aria-label="Copy full panel prompt payload"
              onClick={() => { void copyPanelPayload() }}
              style={nvis.storyboardCopyButton}
            >
              {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
            </button>
          </div>
        </div>
        <div style={nvis.storyboardFrameBottom}>
          <span style={nvis.storyboardShotCode}><Camera size={12} /> {shotCode}</span>
          <span style={nvis.storyboardFrameCaption}>{shotText}</span>
        </div>
      </div>

      <div style={nvis.storyboardPanelBody}>
        <p style={nvis.storyboardAction}>{String(panel.action ?? 'Missing action text')}</p>
        {panel.dialogue ? <p style={nvis.storyboardDialogue}>{String(panel.dialogue)}</p> : null}
        <details data-storyboard-accordion style={nvis.storyboardAccordion}>
          <summary data-storyboard-accordion-header style={nvis.storyboardAccordionHeader}>
            <span>View Generation Specs</span>
            <ChevronDown data-storyboard-accordion-chevron size={14} style={nvis.storyboardAccordionChevron} />
          </summary>
          <div style={nvis.storyboardAccordionContent}>
            <StoryboardPromptBlock prompt={generationPrompt} />
            <div style={nvis.storyboardSupportGrid}>
              <StoryboardSupportBlock
                title="Start Frame"
                body={String(startFrame.description ?? 'Missing start-frame description')}
                items={storyboardStringList(startFrame.visual_requirements)}
              />
              <StoryboardSupportBlock
                title="End Frame"
                body={String(endFrame.description ?? 'Missing end-frame description')}
                items={storyboardStringList(endFrame.visual_requirements)}
              />
              <StoryboardSupportBlock
                title="Camera / Lighting"
                body={`${String(cameraPlan.movement ?? 'Missing camera movement')} ${String(cameraPlan.composition ?? '')}`.trim()}
                items={[
                  String(cameraPlan.camera_equipment ?? 'camera equipment missing'),
                  String(lightingPlan.time_of_day ?? 'time of day missing'),
                  String(lightingPlan.quality ?? 'lighting quality missing'),
                ]}
              />
              <StoryboardSupportBlock
                title="Acting Beats"
                body={actingBeats.length ? actingBeats.join(' ') : 'Missing acting beats'}
                items={[
                  `Producer: ${String(productionNotes.producer ?? 'missing')}`,
                  `Director: ${String(productionNotes.director ?? 'missing')}`,
                  `Scriptwriter: ${String(productionNotes.scriptwriter ?? 'missing')}`,
                ]}
              />
            </div>
          </div>
        </details>
        <div style={nvis.storyboardTrackRow}>
          {seeds.length > 0 && (
            <div style={nvis.storyboardTagGroup}>
              <span style={nvis.storyboardTagLabel}>Seeds</span>
              <div style={nvis.storyboardSeedRow}>
                {seeds.map((seed) => <span key={seed} style={nvis.storyboardSeed}>{seed}</span>)}
              </div>
            </div>
          )}
          {entities.length > 0 && (
            <div style={nvis.storyboardTagGroup}>
              <span style={nvis.storyboardTagLabel}>Entities</span>
              <div style={nvis.storyboardEntityRow}>
                {entities.map((entity) => <span key={entity} style={nvis.storyboardEntity}>{entity}</span>)}
              </div>
            </div>
          )}
        </div>
        {references.length > 0 && (
          <div style={nvis.storyboardReferenceRail}>
            {references.map((reference) => {
              const raw = String(reference.path || reference.url || '')
              const url = dreamAssetUrl(raw)
              const imageEligible = Boolean(url) && String(reference.role ?? '') !== 'rejected_candidate_reference'
              return (
                <div key={String(reference.id ?? reference.title ?? raw)} style={nvis.storyboardReferenceCard}>
                  {imageEligible ? (
                    <img src={url} alt={String(reference.title ?? reference.id ?? 'reference')} style={nvis.storyboardReferenceThumb} />
                  ) : (
                    <div style={nvis.storyboardReferenceFallback}><Image size={16} /></div>
                  )}
                  <div style={nvis.storyboardReferenceText}>
                    <span>{String(reference.title ?? reference.id ?? 'Reference')}</span>
                    <small>{String(reference.role ?? reference.memory_key ?? 'reference')}</small>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </article>
  )
}
