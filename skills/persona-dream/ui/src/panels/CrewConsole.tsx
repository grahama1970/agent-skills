/**
 * CrewConsole, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { chooseCrewPersona, compactCrewText, crewFitRationale, crewRoleCriteria, crewTauRepairNote, scoreCrewPersona } from '../lib/crew'
import {authorStyleGuide, groupResearchContext, loadCrewPersonaCandidates, personaText, personaThumbnailUrl, productionTechniquePackage, roleFitCandidates, rolePrompt} from '../lib/persona'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from '../lib/story'
import { nvis } from '../styles'
import { AlertTriangle, Aperture, BookOpen, Camera, CheckCircle2, ChevronDown, ClipboardCheck, Copy, Film, Gauge, Images, Lightbulb, Move3D, Package, PencilLine, RefreshCw, Sun, Table2, Users, Wand2 } from 'lucide-react'

export function CrewConsole({
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
  const storySetting = useMemo(() => inferStoryLocationAndEnvironment(ideaText || researchSeed || stage.summary || '', stage.artifacts), [ideaText, researchSeed, stage.summary, stage.artifacts])
  const [candidates, setCandidates] = useState<CrewPersonaOption[]>([])
  const [storyDraft, setStoryDraft] = useState('')
  const [creativity, setCreativity] = useState(0.4)
  const [producerId, setProducerId] = useState('')
  const [scriptwriterId, setScriptwriterId] = useState('')
  const [directorId, setDirectorId] = useState('')
  const [status, setStatus] = useState('Loading story contract and persona candidates...')
  const [copyStatus, setCopyStatus] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadCrewContext() {
      try {
        const [candidateItems, storyResponse] = await Promise.all([
          loadCrewPersonaCandidates(),
          fetch('/api/tau/dream/story-draft/latest').then(async (response) => response.ok ? response.json() : null).catch(() => null),
        ])
        if (cancelled) return
        setCandidates(candidateItems)
        const draft = typeof storyResponse?.draft === 'string' ? storyResponse.draft : ''
        setStoryDraft(draft)
        const producer = chooseCrewPersona('producer', candidateItems)
        const scriptwriter = producer ? chooseCrewPersona('scriptwriter', candidateItems, [producer.id]) : null
        const director = producer && scriptwriter ? chooseCrewPersona('director', candidateItems, [producer.id, scriptwriter.id]) : null
        setProducerId((current) => current || producer?.id || '')
        setScriptwriterId((current) => current || scriptwriter?.id || '')
        setDirectorId((current) => current || director?.id || '')
        setStatus(candidateItems.length > 0
          ? `Loaded ${candidateItems.length} persona candidates and ${draft ? 'latest story contract' : 'no latest story contract'}`
          : 'No persona candidates returned from memory')
      } catch (error) {
        if (!cancelled) setStatus(`Crew context failed: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    void loadCrewContext()
    return () => { cancelled = true }
  }, [])

  const personaById = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates])
  const producer = personaById.get(producerId) ?? null
  const scriptwriter = personaById.get(scriptwriterId) ?? null
  const director = personaById.get(directorId) ?? null
  const storyContract = useMemo(() => storyContractSummaryFromDraft(storyDraft), [storyDraft])
  const productionPackage = useMemo(() => productionTechniquePackage(storyContract, linkedAssets), [storyContract, linkedAssets])

  const crewPayload = useMemo(() => ({
    schema: 'dream.crew.prompt_payload.v1',
    metadata: {
      phase: '03',
      gate_state: stage.status,
      created_at: new Date().toISOString(),
      source_story_phase: '02',
    },
    controls: {
      creativity,
      sequence: ['producer', 'scriptwriter', 'director'],
      selection_policy: 'Select Producer first. Then select Scriptwriter using the story plus selected Producer. Then select Director using the story plus selected Producer and Scriptwriter.',
    },
    source_context: {
      core_idea: ideaText || researchSeed || stage.summary || '',
      story_text: storyContract.story,
      story_contract: storyContract.parsed,
      interaction_matrix: storyContract.interactionMatrix,
      location: storyContract.location || storySetting.location,
      environment: storyContract.environment || storySetting.environment,
      linked_assets: linkedAssets,
    },
    candidate_pool: candidates.map((candidate) => ({
      id: candidate.id,
      name: candidate.label,
      source: candidate.source,
      roles: candidate.roles,
      source_paths: candidate.sourcePaths,
      persona_context: candidate.description,
    })),
    current_manual_overrides: {
      producer: producer ? { id: producer.id, name: producer.label, persona_context: producer.description, thumbnail_path: producer.thumbnailPath, source_paths: producer.sourcePaths } : null,
      scriptwriter: scriptwriter ? { id: scriptwriter.id, name: scriptwriter.label, persona_context: scriptwriter.description, thumbnail_path: scriptwriter.thumbnailPath, source_paths: scriptwriter.sourcePaths } : null,
      director: director ? { id: director.id, name: director.label, persona_context: director.description, thumbnail_path: director.thumbnailPath, source_paths: director.sourcePaths } : null,
    },
    visible_selection_rationales: {
      producer: crewFitRationale('producer', producer, storyContract),
      scriptwriter: producer ? crewFitRationale('scriptwriter', scriptwriter, storyContract) : 'Waiting for Producer selection and rationale.',
      director: producer && scriptwriter ? crewFitRationale('director', director, storyContract) : 'Waiting for Producer and Scriptwriter selections and rationales.',
    },
    cinematic_technique_selector_handoff: {
      skill: 'cinematic-technique-selector',
      purpose: 'After crew roles are selected, choose the DoP/camera/lens/lighting/color Look Lock and Script DNA for downstream storyboard/provider prompts.',
      required_context: ['core_idea', 'story_text', 'interaction_matrix', 'location', 'environment', 'linked_assets', 'producer_selection', 'scriptwriter_selection', 'director_selection'],
      preliminary_look_lock: productionPackage,
      output_required: ['technique_selection.json', 'look_lock', 'script_dna', 'shot_bible', 'continuity_lock'],
    },
    prompts: {
      producer_prompt: rolePrompt('producer', 'the accepted Phase 02 Embry/Kai story contract'),
      scriptwriter_prompt: [
        rolePrompt('scriptwriter', 'the accepted Phase 02 Embry/Kai story contract'),
        producer ? `Selected Producer context: ${producer.label} — ${producer.description}` : 'Selected Producer context is missing and must be resolved first.',
      ].join('\n\n'),
      director_prompt: [
        rolePrompt('director', 'the accepted Phase 02 Embry/Kai story contract'),
        producer ? `Selected Producer context: ${producer.label} — ${producer.description}` : 'Selected Producer context is missing.',
        scriptwriter ? `Selected Scriptwriter context: ${scriptwriter.label} — ${scriptwriter.description}` : 'Selected Scriptwriter context is missing and must be resolved before Director.',
      ].join('\n\n'),
    },
    response_contract: {
      type: 'object',
      additionalProperties: false,
      required: ['producer_selection', 'scriptwriter_selection', 'director_selection', 'quality_checks'],
      properties: {
        producer_selection: { type: 'object', description: 'First selected crew role.' },
        scriptwriter_selection: { type: 'object', description: 'Second selected crew role, conditioned on producer_selection.' },
        director_selection: { type: 'object', description: 'Third selected crew role, conditioned on producer_selection and scriptwriter_selection.' },
        quality_checks: { type: 'object', description: 'Coverage and sequencing checks.' },
      },
    },
  }), [candidates, creativity, director, ideaText, linkedAssets, producer, productionPackage, researchSeed, scriptwriter, stage.status, stage.summary, storyContract, storySetting.environment, storySetting.location])

  useEffect(() => {
    const handleHeaderCopy = () => { void copyCrewPayload() }
    window.addEventListener('dream:copy-crew-payload', handleHeaderCopy)
    return () => window.removeEventListener('dream:copy-crew-payload', handleHeaderCopy)
  })

  const regenerateCrewDefaults = () => {
    const nextProducer = chooseCrewPersona('producer', candidates)
    const nextScriptwriter = nextProducer ? chooseCrewPersona('scriptwriter', candidates, [nextProducer.id]) : null
    const nextDirector = nextProducer && nextScriptwriter ? chooseCrewPersona('director', candidates, [nextProducer.id, nextScriptwriter.id]) : null
    setProducerId(nextProducer?.id || '')
    setScriptwriterId(nextScriptwriter?.id || '')
    setDirectorId(nextDirector?.id || '')
    setStatus(`Regenerated crew prompts: Producer → Scriptwriter → Director from ${candidates.length} candidates`)
  }

  const copyCrewPayload = async () => {
    await navigator.clipboard.writeText(JSON.stringify(crewPayload, null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }

  const roleCard = (role: CrewRole, selected: CrewPersonaOption | null, value: string, onChange: (value: string) => void, disabled = false) => {
    const avoid = role === 'producer'
      ? []
      : role === 'scriptwriter'
        ? [producer?.id].filter(Boolean) as string[]
        : [producer?.id, scriptwriter?.id].filter(Boolean) as string[]
    const options = roleFitCandidates(role, candidates, avoid)
    const thumbUrl = personaThumbnailUrl(selected)
    return (
      <section style={{ ...nvis.dataSpine, ...(disabled ? nvis.crewRoleCardDisabled : null) }}>
        <div style={nvis.spineIconSlot}>
          {thumbUrl ? (
            <img src={thumbUrl} alt={selected?.label ?? role} title={selected?.thumbnailConfidence ? `Thumbnail confidence: ${selected.thumbnailConfidence}` : selected?.label} style={nvis.crewPersonaThumb} />
          ) : (
            <span style={nvis.spineIconCircle}>
              {role === 'producer' ? <Package size={15} /> : role === 'scriptwriter' ? <PencilLine size={15} /> : <Film size={15} />}
            </span>
          )}
        </div>
        <div style={nvis.spineContent}>
          <div style={nvis.crewRoleHeader}>
            <span style={nvis.moduleLabel}>{role === 'scriptwriter' ? 'Scriptwriter' : role}</span>
            <span style={nvis.directorSelectWrap}>
              <select
                data-qid={`dream:crew:${role}`}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                style={nvis.directorSelect}
                title={`Choose ${role}`}
                disabled={disabled}
              >
                {(disabled || options.length === 0) && <option value="">{disabled ? 'Waiting on upstream role' : 'No role-fit candidates'}</option>}
                {options.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>{candidate.label}</option>
                ))}
              </select>
              <ChevronDown size={13} style={nvis.directorSelectIcon} />
            </span>
          </div>
          <p style={nvis.moduleBody}>{selected ? compactCrewText(selected.description, 420) : disabled ? 'This selection activates after the upstream role exists.' : 'No role-fit persona selected from memory.'}</p>
          <p style={nvis.crewRationale}>{crewPayload.visible_selection_rationales[role]}</p>
        </div>
      </section>
    )
  }

  const hasProducer = Boolean(producer)
  const hasScriptwriter = Boolean(scriptwriter)
  const storyPreview = compactCrewText(storyContract.story || 'No accepted story text loaded from Phase 02 yet.', 520)
  const matrixCount = storyContract.interactionMatrix.length
  const crewStep = hasProducer && hasScriptwriter ? 3 : hasProducer ? 2 : 1
  const gateMissing = stage.status.toUpperCase().includes('MISSING')

  return (
    <section data-qid="dream:crew:console" style={nvis.crewConsole}>
      <div style={nvis.crewTopBar}>
        <div>
          <div style={nvis.crewTopMeta}>
            <div style={nvis.directorLabel}><Users size={13} /> Sequential Crew Selection</div>
            <span style={nvis.crewStepPill}>Step {crewStep} of 3</span>
            <span style={{ ...nvis.crewGatePill, ...(gateMissing ? nvis.crewGatePillMissing : nvis.crewGatePillReady) }}>
              {gateMissing ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
              {stage.status}
            </span>
          </div>
          <p style={nvis.crewIntro}>Producer is selected first, then Scriptwriter, then Director. Each prompt receives the full idea, story, interaction matrix, location, environment, and linked assets.</p>
        </div>
        <div style={nvis.crewActions}>
          <label style={nvis.directorSliderGroup}>
            <span style={nvis.directorSliderHeader}>
              <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
              <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
            </span>
            <input
              data-qid="dream:crew:creativity"
              type="range"
              min="0.0"
              max="1.0"
              step="0.1"
              value={creativity}
              onChange={(event) => setCreativity(Number(event.target.value))}
              style={nvis.directorRange}
            />
          </label>
          <div style={nvis.crewButtonGroup}>
            <button type="button" data-qid="dream:crew:regenerate" onClick={regenerateCrewDefaults} style={nvis.directorGenerateBtn}><RefreshCw size={13} /> Regenerate Crew</button>
            <button type="button" data-qid="dream:crew:copy-payload" onClick={() => { void copyCrewPayload() }} style={nvis.directorDebugBtn}>{copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}{copyStatus || 'Copy Payload'}</button>
          </div>
        </div>
      </div>
      <div style={nvis.contextSummaryBar}>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Lightbulb size={13} /> Idea</span>
          <p style={nvis.crewContextText}>{compactCrewText(ideaText || researchSeed || stage.summary || 'No core idea loaded.', 360)}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><BookOpen size={13} /> Story</span>
          <p style={nvis.crewContextText}>{storyPreview}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Table2 size={13} /> Interaction Matrix</span>
          <p style={nvis.crewContextText}>{matrixCount > 0 ? `${matrixCount} rows collapsed into the copied crew payload.` : 'No interaction matrix rows loaded yet.'}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Images size={13} /> Linked Assets</span>
          <div style={nvis.crewThumbStrip}>
            {linkedAssets.slice(0, 6).map((asset) => (
              <img key={asset.id} src={asset.url} alt={asset.title} title={asset.description || asset.title} style={nvis.crewThumb} />
            ))}
            {linkedAssets.length === 0 && <span style={nvis.crewContextText}>No image thumbnails loaded.</span>}
          </div>
        </section>
      </div>
      <div style={nvis.crewMainWorkspace}>
        <div style={nvis.crewSectionHeader}>Active Crew Selection</div>
        {roleCard('producer', producer, producerId, setProducerId)}
        {roleCard('scriptwriter', scriptwriter, scriptwriterId, setScriptwriterId, !hasProducer)}
        {roleCard('director', director, directorId, setDirectorId, !hasProducer || !hasScriptwriter)}
      </div>
      <div style={nvis.directorStatusRow}>
        <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
        <span style={nvis.directorStatus}>{status}</span>
      </div>
      <section style={nvis.crewProductionSection} data-qid="dream:crew:production-technique">
        <span style={nvis.crewRoleLabel}><Wand2 size={13} /> Camera, Lighting, and Look Lock</span>
        <div style={nvis.crewMainWorkspace}>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Camera size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Camera</span><div style={nvis.moduleTitle}>Water-Safe Capture Package</div><p style={nvis.moduleBody}>{productionPackage.camera_package}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Aperture size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Lens</span><div style={nvis.moduleTitle}>Waterline Realism</div><p style={nvis.moduleBody}>{productionPackage.lens_package}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Sun size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Lighting</span><div style={nvis.moduleTitle}>Natural Daylight Surf Window</div><p style={nvis.moduleBody}>{productionPackage.lighting_strategy}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Move3D size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Movement</span><div style={nvis.moduleTitle}>Swell-Timed Camera Logic</div><p style={nvis.moduleBody}>{productionPackage.movement_rules}</p></div></section>
        </div>
      </section>
    </section>
  )
}
