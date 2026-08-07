/**
 * StoryMatrix, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { contactSheetDecisionForStoryRow } from '../lib/contact'
import { coverageNoteForScriptRow, distinctAssetDescription, hasLiveDescriptionReceipt, scriptContractFromDraft, scriptCoverageStatusForRow, scriptCoverageStatusTitle, scriptEntityRows, scriptGlossaryFromContract, scriptStringFromContract, splitScriptIntoRows, storyAssetDescriptionFromMemoryDocument, storyAssetDescriptionFromResult } from '../lib/script'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from '../lib/story'
import { memoryByKeysDocuments } from '../lib/graph'
import { nvis } from '../styles'
import { AssetProvenanceStrip } from './AssetProvenanceStrip'
import { DirectorConsole } from './DirectorConsole'
import { CheckCircle2, ChevronRight, CircleDot, CloudSun, MapPin, Table2 } from 'lucide-react'

export function StoryMatrix({
  stage,
  researchSeed,
  ideaText,
  linkedAssets = [],
}: {
  stage: DreamStage
  researchSeed?: string
  ideaText?: string
  linkedAssets?: LinkedStoryAsset[]
}) {
  const [assetDescriptions, setAssetDescriptions] = useState<Record<string, string>>({})
  const storySetting = useMemo(() => {
    const seed = ideaText || researchSeed || stage.summary || ''
    return inferStoryLocationAndEnvironment(seed, stage.artifacts)
  }, [researchSeed, ideaText, stage.summary, stage.artifacts])

  useEffect(() => {
    let cancelled = false
    const memoryKeys = Array.from(new Set(linkedAssets.map((asset) => asset.memoryKey || asset.id).filter((key) => Boolean(key) && !String(key).startsWith('asset-'))))
    if (memoryKeys.length === 0) {
      setAssetDescriptions({})
      return () => { cancelled = true }
    }
    async function loadAssetDescriptions() {
      try {
        const docs = await memoryByKeysDocuments('persona_memory', memoryKeys)
        if (cancelled) return
        const next: Record<string, string> = {}
        docs.forEach((doc) => {
          const key = String(doc._key ?? '')
          const description = storyAssetDescriptionFromMemoryDocument(doc)
          if (key && description) next[key] = description
        })
        setAssetDescriptions(next)
      } catch {
        if (!cancelled) setAssetDescriptions({})
      }
    }
    void loadAssetDescriptions()
    return () => { cancelled = true }
  }, [linkedAssets])

  const enrichedLinkedAssets = useMemo(() => linkedAssets.map((asset) => {
    const key = asset.memoryKey || asset.id
    return {
      ...asset,
      description: assetDescriptions[key] || asset.description || '',
    }
  }), [linkedAssets, assetDescriptions])

  const entityRows = useMemo<StoryMatrixRow[]>(() => {
    const fromArtifacts = stage.artifacts.filter((a) =>
      a.label.toLowerCase().includes('entity') || a.label.toLowerCase().includes('character') || a.label.toLowerCase().includes('object')
    )
    if (fromArtifacts.length > 0) {
      return fromArtifacts.map((a, i) => ({
        id: `${i}`,
        name: a.label.replace(/\.[^.]+$/, ''),
        objects: a.kind || 'described',
        environment: storySetting.environment,
        dynamics: a.kind || 'present',
        note: `${a.label.replace(/\.[^.]+$/, '')} must be staged against ${storySetting.environment}.`,
        isComplete: isStagePassed(stage),
      }))
    }
    const seed = ideaText || researchSeed || stage.summary || ''
    const extracted: Array<{ name: string; objects: string; dynamics: string; note: string }> = []
    const lower = seed.toLowerCase()
    if (lower.includes('embry')) extracted.push({
      name: 'Embry',
      objects: 'navy rashguard, phone, family obligations, borrowed/older shortboard',
      dynamics: 'Heat and humidity make her physically exposed: sweat, glare, and tired paddling turn autonomy into a bodily choice, not just an idea.',
      note: 'Script/panels should show sweat, squinting, salt on skin, careful hand placement, and fatigue in her paddle cadence before dialogue explains anything.',
    })
    if (lower.includes('kai')) extracted.push({
      name: 'Kai',
      objects: 'black rashguard, phone call, surf ritual, familiar shortboard',
      dynamics: 'Reads the swell while managing heat, glare, and patience; his competence shows in conserving effort instead of forcing the moment.',
      note: 'Stage Kai as physically adapted to the heat: calm breathing, economical paddling, shaded glances at the reef line, and small gestures that guide Embry without lecturing.',
    })
    if (lower.includes('surf') || lower.includes('board') || lower.includes('wave')) {
      extracted.push({
        name: 'Embry surfboard',
        objects: 'White shortboard, performance shape, visibly waxed deck, likely older/borrowed, rail pressure matters over shallow reef.',
        dynamics: 'Humidity and sun soften wax and make footing less certain; the board forces Embry to commit cleanly despite tired arms and slick contact points.',
        note: 'Panel details should include wax smears, sun glare on the deck, hands gripping rails, and foot placement uncertainty as the board reacts to chop and reef proximity.',
      })
      extracted.push({
        name: 'Kai surfboard',
        objects: 'White shortboard with darker underside/rail marks, well-used and waxed, familiar enough for quick reef-line decisions.',
        dynamics: 'A waxed, familiar board lets Kai compensate for heat, chop, and glare; restraint is visible when he waits rather than wasting energy.',
        note: 'Use the board as proof of familiarity: worn rail marks, confident trim angle, efficient turns, and quick corrections under humid, high-glare conditions.',
      })
    }
    if (lower.includes('swell') || lower.includes('wave') || lower.includes('surf')) {
      extracted.push({ name: 'June Swell', objects: 'sets, tide window, wave face', dynamics: 'Creates the timing pressure that makes hesitation and trust visible.', note: 'Panels need repeating set rhythm: quiet water, approaching lump, glare on the face, then a fast decision point.' })
    }
    if (lower.includes('reef') || lower.includes('rock') || lower.includes('lava')) {
      extracted.push({ name: 'Lava Reef', objects: 'sharp rock, shallow line, safe channel', dynamics: 'Turns the environment into a hard boundary rather than background scenery.', note: 'Show the reef as a physical rule: dark shapes below clear water, shallow consequences, and characters adjusting line and timing around it.' })
    }
    if (lower.includes('kona') || lower.includes('coast') || lower.includes('kahalu')) {
      extracted.push({ name: 'Kona Coast', objects: 'bay, local etiquette, reef break', dynamics: 'Holds the scene inside a public place where local rules shape private choices.', note: 'Script beats should include public beach pressure, waiting turns, reading locals, and the contrast between private escape and shared water.' })
    }
    if (extracted.length === 0 && seed) {
      seed.split(/[.!?]+/).forEach((s, i) => {
        const trimmed = s.trim()
        if (trimmed && i < 4) {
          extracted.push({ name: `Beat ${i + 1}`, objects: trimmed.slice(0, 48), dynamics: 'described in context', note: `Translate this beat into physical panel behavior under ${storySetting.environment}.` })
        }
      })
    }
    return extracted.map((e, i) => ({
      ...e,
      environment: storySetting.environment,
      id: `seed-${i}`,
      isComplete: Boolean(e.objects && e.dynamics && e.note && storySetting.environment !== 'MISSING'),
    }))
  }, [storySetting.environment, researchSeed, ideaText, stage])

  const memoryAnchorForEntity = (name: string, id: string) => {
    const lower = name.toLowerCase()
    if (lower.includes('embry')) return 'embry_age19_23_b01_memory_012'
    if (lower.includes('kai')) return 'embry_age15_19_b03_memory_016'
    if (lower.includes('reef') || lower.includes('kona') || lower.includes('swell')) return 'environment_surf_context'
    return id
  }

  return (
    <div style={nvis.matrixCard} data-qid="story-matrix">
      <DirectorConsole
        rows={entityRows}
        location={storySetting.location}
        environment={storySetting.environment}
        gateState={stage.status}
        coreIdea={ideaText || researchSeed || stage.summary || ''}
        linkedAssets={enrichedLinkedAssets}
      />
      <div style={nvis.matrixMetaGrid}>
        <div style={nvis.matrixMetaItem}>
          <span style={nvis.matrixMetaLabel}><MapPin size={12} /> Location</span>
          <span style={nvis.matrixMetaValue}>{storySetting.location}</span>
        </div>
        <div style={nvis.matrixMetaItem}>
          <span style={nvis.matrixMetaLabel}><CloudSun size={12} /> Environment</span>
          <span style={nvis.matrixMetaValue}>{storySetting.environment}</span>
        </div>
      </div>
      <h3 style={nvis.matrixSectionTitle}><Table2 size={12} /> Interaction Matrix</h3>
      <table style={nvis.matrixTable}>
        <thead>
          <tr style={nvis.matrixHeaderRow}>
            <th style={nvis.matrixTh}>Entity</th>
            <th style={nvis.matrixTh}>Objects</th>
            <th style={nvis.matrixTh}>Environment</th>
            <th style={nvis.matrixTh}>Dynamics</th>
            <th style={nvis.matrixTh}>Story Note</th>
            <th style={nvis.matrixTh}>Contact Sheet</th>
            <th style={nvis.matrixTh}>Status</th>
          </tr>
        </thead>
        <tbody>
          {entityRows.length === 0 && (
            <tr><td colSpan={7} style={{ ...nvis.matrixTd, textAlign: 'center', color: '#ff4444' }}>No entities extracted. Story matrix is empty.</td></tr>
          )}
          {entityRows.map((e) => {
            const contactSheet = contactSheetDecisionForStoryRow(e)
            return (
              <tr key={e.id} style={nvis.matrixRow}>
                <td style={nvis.matrixTd}>
                  <span
                    className="entity-link"
                    data-memory-id={memoryAnchorForEntity(e.name, e.id)}
                    aria-label={`${e.name} is grounded by ${memoryAnchorForEntity(e.name, e.id)}`}
                  >
                    {e.name}
                  </span>
                </td>
                <td style={{ ...nvis.matrixTd, color: e.objects ? '#e2e8f0' : '#ff4444' }}>{e.objects || 'MISSING'}</td>
                <td style={{ ...nvis.matrixTd, color: e.environment !== 'MISSING' ? '#e2e8f0' : '#ff4444' }}>{e.environment}</td>
                <td style={{ ...nvis.matrixTd, color: e.dynamics ? '#e2e8f0' : '#ff4444' }}>{e.dynamics || 'MISSING'}</td>
                <td style={{ ...nvis.matrixTd, color: e.note ? '#cbd5e1' : '#ff4444' }}>{e.note || 'MISSING'}</td>
                <td style={nvis.matrixTd}>
                  <span
                    title={contactSheet.rationale}
                    style={contactSheet.required ? nvis.matrixReadyPill : nvis.matrixMutedPill}
                  >
                    {contactSheet.required ? <CheckCircle2 size={12} /> : <CircleDot size={12} />}
                    {contactSheet.required ? 'Yes' : 'No'} · {contactSheet.kind.replace('_', ' ')}
                  </span>
                </td>
                <td style={nvis.matrixTd}>
                  {e.isComplete
                    ? <span style={nvis.matrixReadyPill}><CheckCircle2 size={12} /> Ready</span>
                    : (
                      <button
                        type="button"
                        data-qid={`dream:story:link-residue:${e.id}`}
                        title={`Choose a recalled source for ${e.name}`}
                        onClick={() => { window.location.hash = 'idea' }}
                        style={nvis.matrixPendingPill}
                      >
                        <span style={nvis.pathTraceHop}>PATH_01</span>
                        <ChevronRight size={9} />
                        <span>Source Needed</span>
                        <ChevronRight size={9} />
                        <span style={nvis.pathTraceTarget}>Target</span>
                      </button>
                    )
                  }
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <AssetProvenanceStrip assets={enrichedLinkedAssets} />
    </div>
  )
}
