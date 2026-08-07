/**
 * ScriptConsole, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { crc32, downloadBlob, fnv1a32, writeUint16, writeUint32 } from '../lib/binary'
import { chooseCrewPersona, compactCrewText, crewFitRationale, crewRoleCriteria, crewTauRepairNote, scoreCrewPersona } from '../lib/crew'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from '../lib/story'
import { stableJson } from '../lib/text'
import { nvis } from '../styles'
import { ScriptAssetTile } from './ScriptAssetTile'
import { ScriptTable } from './ScriptTable'
import { BookOpen, CheckCircle2, Clapperboard, ClipboardCheck, Copy, FileText, Gauge, Images, Lightbulb, Play, Sparkles, Table2 } from 'lucide-react'

export function ScriptConsole({
  stage,
  allStages,
  researchSeed,
  ideaText,
  linkedAssets,
}: {
  stage: DreamStage
  allStages: DreamStage[]
  researchSeed?: string
  ideaText?: string
  linkedAssets: LinkedStoryAsset[]
}) {
  const storyStage = allStages.find((s) => s.id === '02')
  const crewStage = allStages.find((s) => s.id === '03')
  const contactStage = allStages.find((s) => s.id === '04')
  const voicesStage = allStages.find((s) => s.id === '05')
  const [creativity, setCreativity] = useState(0.5)
  const [sceneCount, setSceneCount] = useState(1)
  const [targetPages, setTargetPages] = useState(1)
  const [durationSeconds, setDurationSeconds] = useState(10)
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState('')
  const [storyDraftSource, setStoryDraftSource] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    let cancelled = false
    try {
      setDraft(localStorage.getItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY) || '')
      setStatus(localStorage.getItem(DREAM_SCRIPT_STATUS_STORAGE_KEY) || '')
      const cachedStory = localStorage.getItem(DREAM_STORY_DRAFT_STORAGE_KEY) || ''
      if (cachedStory) setStoryDraftSource(cachedStory)
    } catch {
      // Local storage is only a cache for the visible draft.
    }
    fetch('/api/tau/dream/story-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data || typeof data.draft !== 'string' || data.draft.trim().length === 0) return
        setStoryDraftSource(data.draft)
        try {
          localStorage.setItem(DREAM_STORY_DRAFT_STORAGE_KEY, data.draft)
        } catch {
          // The fetched Tau artifact remains in React state.
        }
      })
      .catch(() => {
        // Missing latest-story endpoint keeps the script pane fail-closed.
      })
    fetch('/api/tau/dream/script-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data) return
        const nextDraft = data.script_contract && typeof data.script_contract === 'object'
          ? JSON.stringify(data.script_contract, null, 2)
          : typeof data.draft === 'string'
            ? data.draft
            : ''
        if (nextDraft.trim().length === 0) return
        setDraft(nextDraft)
        const nextStatus = typeof data.status === 'string' ? `Tau script loop ${data.status}` : 'Tau script loaded'
        setStatus(nextStatus)
        try {
          localStorage.setItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY, nextDraft)
          localStorage.setItem(DREAM_SCRIPT_STATUS_STORAGE_KEY, nextStatus)
        } catch {
          // The fetched Tau artifact remains in React state.
        }
      })
      .catch(() => {
        // Missing latest-script endpoint leaves the pane ready for manual generation.
      })
    return () => { cancelled = true }
  }, [])

  const updateDraft = (nextDraft: string) => {
    setDraft(nextDraft)
    try {
      if (nextDraft) localStorage.setItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY, nextDraft)
      else localStorage.removeItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY)
    } catch {
      // Keep React state authoritative when local storage is unavailable.
    }
  }

  const updateStatus = (nextStatus: string) => {
    setStatus(nextStatus)
    try {
      if (nextStatus) localStorage.setItem(DREAM_SCRIPT_STATUS_STORAGE_KEY, nextStatus)
      else localStorage.removeItem(DREAM_SCRIPT_STATUS_STORAGE_KEY)
    } catch {
      // Visible status remains in React state.
    }
  }

  const storyDraft = storyDraftSource
  const storyContract = storyContractSummaryFromDraft(storyDraft)
  const storySetting = inferStoryLocationAndEnvironment(ideaText || researchSeed || storyStage?.summary || stage.summary || '', stage.artifacts)

  const buildScriptPayload = () => {
    const sourceContext = {
      core_idea: ideaText || researchSeed || stage.summary || '',
      story_text: storyContract.story || storyStage?.summary || '',
      story_contract: storyDraft ? parseStoryDraftJson(storyDraft) : null,
      interaction_matrix: storyContract.interactionMatrix,
      location: storySetting.location,
      environment: storySetting.environment,
      linked_assets: linkedAssets.map((asset) => ({
        id: asset.id,
        title: asset.title,
        url: asset.url,
        description: asset.description || '',
        source: asset.source || asset.memoryKey || asset.id,
        media_type: asset.mediaType || '',
      })),
      contact_sheets: {
        artifacts: stageArtifactSummary(contactStage),
        images: stageImageSummary(contactStage),
      },
      voices: {
        artifacts: stageArtifactSummary(voicesStage),
        images: stageImageSummary(voicesStage),
      },
      crew: {
        artifacts: stageArtifactSummary(crewStage),
        images: stageImageSummary(crewStage),
      },
    }
    const responseContract = {
      type: 'object',
      additionalProperties: false,
      required: [
        'script',
        'scene_count',
        'target_pages',
        'dialogue_blocks',
        'action_blocks',
        'environment_continuity',
        'voice_direction',
        'asset_usage',
        'interaction_matrix_coverage',
        'quality_checks',
      ],
      properties: {
        script: {
          type: 'string',
          description: 'Screenplay-formatted script text for the requested scene/page count.',
        },
        scene_count: { type: 'number' },
        target_pages: { type: 'number' },
        dialogue_blocks: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['character', 'line', 'tone', 'source_context'],
            properties: {
              character: { type: 'string' },
              line: { type: 'string' },
              tone: { type: 'string' },
              source_context: { type: 'string' },
            },
          },
        },
        action_blocks: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['beat', 'physical_action', 'environment_driver'],
            properties: {
              beat: { type: 'string' },
              physical_action: { type: 'string' },
              environment_driver: { type: 'string' },
            },
          },
        },
        environment_continuity: {
          type: 'array',
          items: { type: 'string' },
        },
        voice_direction: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['character', 'delivery', 'pause_or_tone_note'],
            properties: {
              character: { type: 'string' },
              delivery: { type: 'string' },
              pause_or_tone_note: { type: 'string' },
            },
          },
        },
        asset_usage: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['asset_id', 'used_for', 'script_continuity_note'],
            properties: {
              asset_id: { type: 'string' },
              used_for: { type: 'string' },
              script_continuity_note: { type: 'string' },
            },
          },
        },
        interaction_matrix_coverage: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['source_seed_id', 'covered_in_script', 'script_function', 'script_evidence', 'environmental_realism_evidence', 'missing_script_details'],
            properties: {
              source_seed_id: { type: 'string' },
              covered_in_script: { type: 'boolean', const: true },
              script_function: { type: 'string' },
              script_evidence: { type: 'string', description: 'Exact script line, beat, or sentence proving this row is described.' },
              environmental_realism_evidence: { type: 'string', description: 'Concrete visible evidence for how heat, humidity, water, reef, light, fatigue, or etiquette affects the entity/object.' },
              missing_script_details: {
                type: 'array',
                maxItems: 0,
                items: { type: 'string' },
                description: 'Must be empty. Any item means script-reviewer must return NEEDS_CHANGES and route back to script-writer.',
              },
            },
          },
        },
        quality_checks: {
          type: 'object',
          additionalProperties: false,
          required: [
            'uses_phase02_story',
            'covers_interaction_matrix',
            'uses_contact_sheet_context',
            'uses_voice_context',
            'does_not_invent_unprovided_assets',
          ],
          properties: {
            uses_phase02_story: { type: 'boolean' },
            covers_interaction_matrix: { type: 'boolean' },
            uses_contact_sheet_context: { type: 'boolean' },
            uses_voice_context: { type: 'boolean' },
            does_not_invent_unprovided_assets: { type: 'boolean' },
          },
        },
      },
    }
    const prompt = [
      'Create the Phase 06 screenplay script for persona-dream.',
      '',
      'Use the accepted prior pane artifacts as the only source of truth.',
      'The script must be generated by the Tau DAG in tau_orchestration. Do not run this as a one-shot prompt.',
      'Tau must dispatch script-writer first, then script-reviewer. The reviewer may either PASS or route back to script-writer while attempts remain. If attempts are exhausted, return BLOCKED_MAX_RETRIES with the failed source_seed_id rows.',
      '',
      'Do not create a new story. Adapt the Phase 02 story contract into screenplay form.',
      'Every character, object, and environmental pressure used by the story must remain explainable through the interaction matrix.',
      'Reviewer gate: every source_context.interaction_matrix row must have one matching interaction_matrix_coverage row with covered_in_script=true, non-empty script_evidence, non-empty environmental_realism_evidence, and missing_script_details=[].',
      'If any interaction_matrix_coverage row has covered_in_script=false, missing_script_details length > 0, or vague evidence, script-reviewer must return NEEDS_CHANGES and Tau must route back to script-writer while attempts remain.',
      'Reject PASS if Embry, Kai, either surfboard, June Swell, Lava Reef, Kona Coast, heat, humidity, glare, saltwater, softened wax, fatigue, or local etiquette are only mentioned but not visibly described in the script.',
      'Reject PASS if the script includes timestamp notation in the screenplay body. Duration belongs in metadata/table rows, not in screenplay text.',
      'Reject PASS if $extract-entities coverage cannot map highlighted character/object/environment mentions back to source_context.interaction_matrix.',
      'Use voice context for delivery notes, but do not invent unavailable voices.',
      'Use contact sheets and linked assets as continuity references, not as extra plot.',
      '',
      '<source_context>',
      JSON.stringify(sourceContext, null, 2),
      '</source_context>',
      '',
      '<response_contract>',
      JSON.stringify(responseContract, null, 2),
      '</response_contract>',
      '',
      'Return one raw JSON object only. No markdown. No comments. No keys outside the response contract.',
    ].join('\n')
    const dagHashMaterial = {
      phase: '06',
      task: {
        kind: 'phase_06_script',
        scene_count: sceneCount,
        target_pages: targetPages,
        duration_seconds: durationSeconds,
      },
      source_context: sourceContext,
      response_contract: responseContract,
      creator_agent: 'script-writer',
      reviewer_agent: 'script-reviewer',
      max_retries: 2,
    }
    const dagGoalHash = `fnv1a32:${fnv1a32(stableJson(dagHashMaterial))}`
    return {
      schema: 'dream.script.prompt_payload.v1',
      metadata: {
        phase: '06',
        gate_state: stage.status,
        timestamp: new Date().toISOString(),
      },
      tau_orchestration: {
        required: true,
        schema: 'tau.dag_contract.v1',
        dag_id: 'persona-dream-phase-06-script',
        goal: {
          goal_id: 'persona-dream-phase-06-script',
          goal_version: 1,
          goal_hash: dagGoalHash,
          goal_hash_algorithm: 'fnv1a32',
          goal_hash_material: dagHashMaterial,
        },
        target: {
          project: 'persona-dream',
          pane: '06 Script',
          route: '/dream#script',
          output_artifact: 'script_contract.json',
          output_artifact_schema: 'dream.script.contract.v1',
          artifact_root: 'experiments/goal-locked-subagents/proofs/persona-dream-script-ui-dispatch/**/run',
          memory_persistence: {
            required: true,
            collections: ['persona_dream_projects', 'persona_memory'],
            graph_edges: ['project->script_contract', 'script_contract->interaction_matrix_rows', 'script_contract->linked_assets'],
            indexes: ['ArangoSearch BM25 View', 'Arango graph traversal', 'Qdrant semantic vectors'],
          },
        },
        limits: {
          max_iterations: 2,
          max_retries: 2,
          default_timeout_seconds: 300,
          fail_fast: true,
        },
        entry_node: 'script-writer',
        terminal_nodes: ['human'],
        nodes: [
          {
            id: 'script-writer',
            agent: 'script-writer',
            executor: 'local',
            role: 'creator',
            max_attempts: 2,
            input_refs: ['source_context', 'response_contract', 'messages[1].content'],
            output: 'strict JSON matching response_contract',
            required_evidence: [
              'script_contract.json',
              'entity_environment_script_table.json',
              'interaction_matrix_coverage.json',
              'realism_contract.json',
              'persona_memory_grounding_ledger.json',
            ],
          },
          {
            id: 'script-reviewer',
            agent: 'script-reviewer',
            executor: 'local',
            role: 'reviewer',
            max_attempts: 2,
            input_refs: ['script-writer.output', 'source_context.interaction_matrix', 'response_contract'],
            output: 'PASS_SCRIPT_CONTRACT or NEEDS_CHANGES with failed source_seed_id rows',
            required_evidence: [
              'script-reviewer-verdict.json',
              'validate_script_contract.json',
              'interaction_matrix_coverage_verdict.json',
              'extract_entities_coverage.json',
              'memory_persistence_receipt.json',
            ],
          },
          {
            id: 'human',
            agent: 'human',
            executor: 'human',
            role: 'terminal',
            receives: ['PASS_SCRIPT_CONTRACT', 'BLOCKED_MAX_RETRIES'],
          },
        ],
        edges: [
          { from: 'script-writer', to: 'script-reviewer' },
          {
            from: 'script-reviewer',
            to: 'script-writer',
            condition: 'NEEDS_CHANGES and script-writer.attempts_remaining > 0',
            repair_payload: 'failed source_seed_id rows, missing_script_details, missing entity/environment evidence',
          },
          {
            from: 'script-reviewer',
            to: 'human',
            condition: 'PASS_SCRIPT_CONTRACT or BLOCKED_MAX_RETRIES',
          },
        ],
        required_evidence: [
          'script_contract.json',
          'script-reviewer-verdict.json',
          'validate_script_contract.json',
          'entity_environment_script_table.json',
          'interaction_matrix_coverage.json',
          'extract_entities_coverage.json',
          'memory_persistence_receipt.json',
        ],
        pass_condition: 'script-reviewer returns PASS_SCRIPT_CONTRACT and every interaction_matrix_coverage row has covered_in_script=true, non-empty script_evidence, non-empty environmental_realism_evidence, and missing_script_details=[]',
        stop_condition: 'PASS_SCRIPT_CONTRACT, or max_retries is exceeded and Tau returns BLOCKED_MAX_RETRIES with failed source_seed_id rows',
        fail_closed_on: [
          'missing_goal_hash',
          'missing_required_evidence',
          'malformed_script_contract',
          'missing_interaction_matrix_row',
          'covered_in_script_false',
          'missing_script_evidence',
          'missing_environmental_realism_evidence',
          'missing_script_details_non_empty',
          'missing_extract_entities_coverage',
          'missing_memory_persistence_receipt',
          'screenplay_body_contains_timestamps',
          'entity_mentioned_without_description',
          'max_attempts_exceeded',
        ],
      },
      model: {
        provider: 'tau',
        default_creator_model: 'gpt-5.5',
        reasoning_effort: 'medium',
        reviewer_model: 'moonshotai/Kimi-K2.6-TEE',
        creativity,
      },
      task: {
        kind: 'phase_06_script',
        scene_count: sceneCount,
        target_pages: targetPages,
        duration_seconds: durationSeconds,
        output_format: 'strict_json',
      },
      source_context: sourceContext,
      response_contract: responseContract,
      messages: [
        {
          role: 'system',
          content: 'You are the Phase 06 script creator/reviewer loop for persona-dream. Return strict JSON only.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
    }
  }

  const copyPayload = async () => {
    await navigator.clipboard.writeText(JSON.stringify(buildScriptPayload(), null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }

  const generateScript = async () => {
    const payload = buildScriptPayload()
    setIsGenerating(true)
    updateStatus('Dispatching Tau script loop...')
    try {
      const response = await fetch('/api/tau/dream/script-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof data?.error === 'string'
          ? data.error
          : typeof data?.detail === 'string'
            ? data.detail
            : `HTTP ${response.status}`
        if (message === 'tau_script_runner_missing') {
          const blockedPayload = {
            status: 'BLOCKED',
            blocker: message,
            detail: typeof data?.detail === 'string' ? data.detail : 'Tau Phase 06 script runner is missing.',
            tau_issue: typeof data?.tau_issue === 'string' ? data.tau_issue : 'https://github.com/grahama1970/tau/issues/47',
            mocked: data?.mocked === true,
            live: data?.live === true,
            out_dir: typeof data?.out_dir === 'string' ? data.out_dir : null,
            artifacts: data?.artifacts ?? null,
            counts: data?.counts ?? null,
          }
          updateDraft(JSON.stringify(blockedPayload, null, 2))
          updateStatus(`Blocked: ${message} · ${blockedPayload.tau_issue}`)
          return
        }
        throw new Error(message)
      }
      const scriptDraft = data?.script_contract && typeof data.script_contract === 'object'
        ? JSON.stringify(data.script_contract, null, 2)
        : typeof data?.script_contract?.script === 'string' && data.script_contract.script.trim().length > 0
          ? data.script_contract.script.trim()
          : JSON.stringify(data, null, 2)
      updateDraft(scriptDraft)
      updateStatus(`Tau script loop ${data?.status || 'returned'}`)
    } catch (error) {
      updateStatus(`Script failed: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const matrixCount = storyContract.interactionMatrix.length

  return (
    <section data-qid="dream:script:console" style={nvis.crewConsole}>
      <div style={nvis.crewTopBar}>
        <div style={nvis.crewTopMeta}>
          <p data-qid="dream:script:phase-description" style={nvis.scriptPhaseDescription}>
            Generate screenplay JSON from the accepted idea, Phase 02 story, interaction matrix, crew choices, contact sheets, voices, and linked assets.
          </p>
        </div>
        <div style={nvis.crewActions}>
          <label style={nvis.directorSliderGroup}>
            <span style={nvis.directorSliderHeader}>
              <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
              <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
            </span>
            <input
              data-qid="dream:script:creativity"
              title="Adjust script creativity"
              type="range"
              min="0.2"
              max="1.2"
              step="0.1"
              value={creativity}
              onChange={(event) => setCreativity(Number(event.target.value))}
              style={nvis.directorRange}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><Clapperboard size={12} /> Scenes</span>
            <input
              data-qid="dream:script:scene-count"
              title="Set script scene count"
              type="number"
              min="1"
              max="8"
              value={sceneCount}
              onChange={(event) => setSceneCount(Math.max(1, Math.min(8, Math.round(Number(event.target.value) || 1))))}
              style={nvis.directorNumberInput}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><FileText size={12} /> Pages</span>
            <input
              data-qid="dream:script:target-pages"
              title="Set target script pages"
              type="number"
              min="1"
              max="20"
              value={targetPages}
              onChange={(event) => setTargetPages(Math.max(1, Math.min(20, Math.round(Number(event.target.value) || 1))))}
              style={nvis.directorNumberInput}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><Play size={12} /> Duration</span>
            <input
              data-qid="dream:script:duration-seconds"
              title="Set target script duration in seconds"
              type="number"
              min="1"
              max="180"
              value={durationSeconds}
              onChange={(event) => setDurationSeconds(Math.max(1, Math.min(180, Math.round(Number(event.target.value) || 10))))}
              style={nvis.directorNumberInput}
            />
            <span style={nvis.directorValue}>sec</span>
          </label>
        </div>
      </div>

      <div style={nvis.scriptPayloadGroup}>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><Lightbulb size={13} /> Idea</span>
          <p style={nvis.scriptPayloadContent}>{compactCrewText(ideaText || researchSeed || stage.summary || 'No core idea loaded.', 300)}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><BookOpen size={13} /> Story</span>
          <p style={nvis.scriptPayloadContent}>{compactCrewText(storyContract.story || storyStage?.summary || 'No accepted Phase 02 story loaded.', 360)}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><Table2 size={13} /> Matrix</span>
          <p style={nvis.scriptPayloadContent}>{matrixCount > 0 ? `${matrixCount} interaction rows included in the script payload.` : 'No interaction matrix rows loaded from Phase 02.'}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.crewRoleLabel}><Images size={13} /> Assets</span>
          <div style={nvis.scriptAssetGrid}>
            {linkedAssets.slice(0, 6).map((asset) => (
              <ScriptAssetTile key={asset.id} asset={asset} />
            ))}
            {linkedAssets.length === 0 && <span style={nvis.crewContextText}>No linked assets loaded.</span>}
          </div>
        </section>
      </div>

      {status && (
        <div data-qid="dream:script:status" style={nvis.directorStatusRow}>
          <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
          <span style={nvis.directorStatus}>{status}</span>
        </div>
      )}

      <div style={nvis.scriptStoryAreaWrap}>
        <div style={nvis.scriptSectionHeader}>
          <span style={nvis.scriptSectionRule} />
          <span style={nvis.scriptSectionTitle}><FileText size={13} /> Script Area</span>
          <span style={nvis.scriptSectionRuleWide} />
        </div>
        <div style={nvis.directorStoryContent}>
          <div data-qid="dream:script:canvas" style={nvis.directorStoryCanvas}>
            <ScriptTable draft={draft} storyContract={storyContract} durationSeconds={durationSeconds} />
          </div>
          <details style={nvis.directorJsonDetails}>
            <summary style={nvis.directorJsonSummary}>Edit Script JSON</summary>
            <textarea
              data-qid="dream:script:draft"
              title="Script JSON draft area"
              value={draft}
              onChange={(event) => updateDraft(event.target.value)}
              placeholder="Generated strict script JSON will appear here..."
              style={nvis.directorStoryArea}
            />
          </details>
        </div>
      </div>

      <div data-qid="dream:script:action-bar" style={nvis.scriptActionBar}>
        <button
          type="button"
          data-qid="dream:script:copy-payload:footer"
          title="Copy Phase 06 script prompt payload JSON"
          onClick={() => { void copyPayload() }}
          style={nvis.directorDebugBtn}
        >
          {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
          {copyStatus || 'Copy Payload'}
        </button>
        <button
          type="button"
          data-qid="dream:script:generate:footer"
          title="Dispatch Phase 06 script payload to Tau"
          disabled={isGenerating}
          onClick={() => { void generateScript() }}
          style={{ ...nvis.directorGenerateBtn, ...(isGenerating ? nvis.directorBtnDisabled : null) }}
        >
          <Sparkles size={14} />
          {isGenerating ? 'Dispatching' : 'Generate Script'}
        </button>
      </div>
    </section>
  )
}
