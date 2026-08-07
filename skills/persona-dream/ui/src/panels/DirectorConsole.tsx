/**
 * DirectorConsole, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { useRegisterAction } from '../useRegisterAction'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { contactSheetDecisionForStoryRow } from '../lib/contact'
import { authorStyleGuide, groupResearchContext, personaText, personaThumbnailUrl, productionTechniquePackage, roleFitCandidates, rolePrompt } from '../lib/persona'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from '../lib/story'
import { nvis } from '../styles'
import { BookOpen, CheckCircle2, ChevronDown, Clapperboard, ClipboardCheck, Copy, FileText, Gauge, Lightbulb, Play, Sparkles, UserRound } from 'lucide-react'

export function DirectorConsole({
  rows,
  location,
  environment,
  gateState,
  coreIdea,
  linkedAssets,
}: {
  rows: StoryMatrixRow[]
  location: string
  environment: string
  gateState: string
  coreIdea: string
  linkedAssets: LinkedStoryAsset[]
}) {
  const [creativity, setCreativity] = useState(0.6)
  const [panelCount, setPanelCount] = useState(1)
  const [durationSeconds, setDurationSeconds] = useState(10)
  const [writer, setWriter] = useState('')
  const [writers, setWriters] = useState<StoryWriterOption[]>([])
  const [draft, setDraft] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [generateStatus, setGenerateStatus] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    let cancelled = false
    try {
      const savedDraft = localStorage.getItem(DREAM_STORY_DRAFT_STORAGE_KEY)
      const savedStatus = localStorage.getItem(DREAM_STORY_STATUS_STORAGE_KEY)
      if (savedDraft) {
        setDraft(savedDraft)
        if (savedStatus) setGenerateStatus(compactStoryStatus(savedStatus))
        return () => { cancelled = true }
      }
      if (savedStatus) setGenerateStatus(compactStoryStatus(savedStatus))
    } catch {
      // Local storage is a convenience cache; generation still works without it.
    }
    fetch('/api/tau/dream/story-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data || typeof data.draft !== 'string' || data.draft.trim().length === 0) return
        updateDraft(data.draft)
        updateGenerateStatus('Loaded latest Tau story')
      })
      .catch(() => {
        // No prior Tau story artifact is acceptable; the user can still draft one.
      })
    return () => { cancelled = true }
  }, [])

  const updateDraft = (nextDraft: string) => {
    setDraft(nextDraft)
    try {
      if (nextDraft) {
        localStorage.setItem(DREAM_STORY_DRAFT_STORAGE_KEY, nextDraft)
      } else {
        localStorage.removeItem(DREAM_STORY_DRAFT_STORAGE_KEY)
      }
    } catch {
      // Ignore storage failures; React state remains authoritative for this session.
    }
  }

  const updateGenerateStatus = (nextStatus: string) => {
    const compact = compactStoryStatus(nextStatus)
    setGenerateStatus(compact)
    try {
      if (compact) {
        localStorage.setItem(DREAM_STORY_STATUS_STORAGE_KEY, compact)
      } else {
        localStorage.removeItem(DREAM_STORY_STATUS_STORAGE_KEY)
      }
    } catch {
      // Ignore storage failures; visible state still updates.
    }
  }

  useRegisterAction('dream:story:writer', {
    app: 'ux-lab',
    action: 'DREAM_STORY_WRITER_SELECT',
    label: 'Select author persona',
    description: 'Choose the Phase 02 author persona from persona_memory',
  })
  useRegisterAction('dream:story:creativity', {
    app: 'ux-lab',
    action: 'DREAM_STORY_CREATIVITY_SET',
    label: 'Set story creativity',
    description: 'Adjust the Phase 02 story creativity control',
  })
  useRegisterAction('dream:story:generate', {
    app: 'ux-lab',
    action: 'DREAM_STORY_GENERATE',
    label: 'Draft treatment',
    description: 'Generate a story treatment from current actors, objects, environment, and dynamics rows',
  })
  useRegisterAction('dream:story:draft', {
    app: 'ux-lab',
    action: 'DREAM_STORY_DRAFT_EDIT',
    label: 'Edit story draft',
    description: 'Edit the Phase 02 generated story treatment',
  })

	  useEffect(() => {
	    let cancelled = false
	    async function loadWriters() {
	      try {
	        const personasResponse = await fetch('/api/memory/list', {
	          method: 'POST',
	          headers: { 'Content-Type': 'application/json' },
	          body: JSON.stringify({
	            collection: 'personas',
	            filters: { doc_type: 'persona_profile' },
	            limit: 200,
	          }),
	        })
	        if (personasResponse.ok) {
	          const personasData = await personasResponse.json()
	          const personaItems = Array.isArray(personasData.documents) ? personasData.documents : []
	          const personaWriters = personaItems
	            .filter((item: Record<string, unknown>) => {
	              if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return false
	              const tags = Array.isArray(item.tags) ? item.tags.map(String) : []
	              const haystack = [
	                item.template,
	                item.source_path,
	                item.runtime_persona_card,
	                item.content,
	                item.writing_style,
	                ...tags,
	              ].join(' ').toLowerCase()
	              return haystack.includes('writer') || haystack.includes('author') || tags.includes('template:writer')
	            })
	            .map((item: Record<string, unknown>) => {
	              const id = String(item.persona_id || item._key || '').trim()
	              const label = String(item.canonical_name || item.display_name || id.replace(/_/g, ' ')).trim()
	              const description = String(item.writing_style || item.runtime_persona_card || item.summary || item.content || '').replace(/\s+/g, ' ').trim()
	              return { id, label, description: description.slice(0, 1200) }
	            })
	            .filter((option: StoryWriterOption) => option.id && option.description)
	          if (personaWriters.length > 0) {
	            if (!cancelled) {
	              setWriters(personaWriters)
	              setWriter((current) => current || personaWriters[0]?.id || '')
	            }
	            return
	          }
	        }

	        const [identityResponse, styleResponse] = await Promise.all([
	          fetch('/api/memory/list', {
	            method: 'POST',
	            headers: { 'Content-Type': 'application/json' },
	            body: JSON.stringify({
	              collection: 'persona_memory',
	              filters: { record_type: 'persona_identity' },
	              limit: 200,
	            }),
	          }),
	          fetch('/api/memory/list', {
	            method: 'POST',
	            headers: { 'Content-Type': 'application/json' },
	            body: JSON.stringify({
	              collection: 'persona_memory',
	              filters: { record_type: 'persona_style' },
	              limit: 200,
	            }),
	          }),
	        ])
	        if (!identityResponse.ok || !styleResponse.ok) return
	        const identityData = await identityResponse.json()
	        const styleData = await styleResponse.json()
	        const identityItems = Array.isArray(identityData.documents) ? identityData.documents : []
	        const styleItems = Array.isArray(styleData.documents) ? styleData.documents : []
	        const writersById = new Map<string, {
	          label: string
	          identityText: string[]
	          styleText: string[]
	        }>()
	        const ensureWriter = (personaId: string) => {
	          const existing = writersById.get(personaId)
	          if (existing) return existing
	          const created = {
	            label: personaId.replace(/^persona_/, '').replace(/_/g, ' '),
	            identityText: [] as string[],
	            styleText: [] as string[],
	          }
	          writersById.set(personaId, created)
	          return created
	        }
	        identityItems.forEach((item: Record<string, unknown>) => {
	          if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return
	          const sourcePath = String(item.source_path ?? '')
	          const text = `${item.retrieval_text ?? ''} ${item.evidence_text ?? ''}`.toLowerCase()
	          if (!sourcePath.includes('/writers/') && !text.includes('template: writer') && !text.includes('writer template') && !text.includes('author')) return
	          const personaId = String(item.persona_id || item._key || '').trim()
	          if (!personaId) return
	          const writerRecord = ensureWriter(personaId)
	          const raw = String(item.evidence_text || item.retrieval_text || personaId)
	          const nameMatch = raw.match(/(?:^|\n)\s*name:\s*([^\n]+)/i)
	            || raw.match(/#\s*([^-#\n]+?)\s*-\s*(?:Science Fiction Writer|Writer|Author)/i)
	          writerRecord.label = (nameMatch?.[1] || writerRecord.label).trim()
	          writerRecord.identityText.push(raw.replace(/\s+/g, ' ').trim())
	        })
	        styleItems.forEach((item: Record<string, unknown>) => {
	          if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return
	          const personaId = String(item.persona_id || item._key || '').trim()
	          if (!personaId || !writersById.has(personaId)) return
	          const raw = String(item.claim_text || item.answer_text || item.evidence_text || item.retrieval_text || '').replace(/\s+/g, ' ').trim()
	          if (raw) ensureWriter(personaId).styleText.push(raw)
	        })
	        const next = [...writersById.entries()]
	          .map(([id, value]) => ({
	            id,
	            label: value.label,
	            description: (value.styleText.length > 0 ? value.styleText : value.identityText).join(' ').slice(0, 900),
	          }))
	          .filter((option) => option.description.trim().length > 0)
	        if (!cancelled) {
	          setWriters(next)
	          setWriter((current) => current || next[0]?.id || '')
        }
      } catch {
        if (!cancelled) setWriters([])
      }
    }
    void loadWriters()
    return () => { cancelled = true }
  }, [])

  const buildStoryPromptPayload = (): StoryPromptPayload => {
    const selectedWriter = writers.find((option) => option.id === writer)
    const requestedAuthor = selectedWriter?.label || writer || 'unselected_author'
    const authorMemoryStyle = selectedWriter?.description || ''
    const expandedAuthorStyleGuide = authorStyleGuide(requestedAuthor, authorMemoryStyle)
    const storyKind = panelCount === 1 ? 'one_panel_10_second_story' : 'multi_panel_story_sequence'
    const targetStoryLengthWords = {
      min: Math.max(35, panelCount * 45),
      max: Math.max(70, panelCount * 90),
    }
    const panelSchema = {
      type: 'object',
      additionalProperties: false,
      required: [
        'shot',
        'action',
        'emotional_turn',
        'dialogue',
      ],
      properties: {
        shot: {
          type: 'string',
          description: 'Camera/framing for this panel.',
        },
        action: {
          type: 'string',
          description: 'What happens in this panel moment.',
        },
        emotional_turn: {
          type: 'string',
          description: 'The visible internal shift.',
        },
        dialogue: {
          type: ['string', 'null'],
          description: 'One short line or null.',
        },
      },
    }
    const authorStyleDirective = {
      requested_author: requestedAuthor,
      style_policy: 'High-level craft traits only; do not directly imitate the living author.',
      memory_style_context: authorMemoryStyle,
      expanded_style_guide: expandedAuthorStyleGuide,
      style_summary: expandedAuthorStyleGuide,
      actionable_traits: [
        'practical problem-solving under physical constraints',
        'clear cause-and-effect scene logic',
        'dry, understated observational humor',
        'technical specificity that changes character choices',
        'characters thinking through immediate problems step by step',
        'exposition that feels like active problem-solving rather than lecturing',
        'conversational, precise, propulsive pacing',
        'reader satisfaction from understanding the problem and the earned solution',
        'tension created by real-world timing, physics, etiquette, and limited information',
        'grounded stakes rather than melodrama',
      ],
      application_to_this_story: [
        'Use swell timing as a procedural problem.',
        'Use the lava reef as a hard physical constraint.',
        'Use heat, humidity, softened wax, glare, and fatigue as active causes of mistakes or hesitation.',
        'Let Embry and Kai reveal character through how they solve or avoid problems in the water.',
        'Move through problem, constraint, attempted solution, complication, and embodied decision.',
        'Keep humor understated and observational, never jokey or detached from the stakes.',
      ],
      prohibited_imitation: [
        'Do not copy the requested author exact prose style.',
        'Do not echo specific phrasing, character types, plots, or scenes from the requested author works.',
        'Do not make the story sound like fan fiction of an existing book.',
      ],
    }
    const creativityDirective = {
      slider_value: creativity,
      label: 'grounded moderate invention',
      actionable_interpretation: 'Stay realistic and physically plausible while allowing selective invented details that intensify tension, character contrast, and scene texture.',
      allowed_inventions: [
        'small work-related phone interruptions',
        'specific family-obligation pressure for Embry',
        'a plausible local-etiquette tension in the lineup',
        'a softened-wax or grip problem caused by heat',
        'a tricky but realistic summer swell set',
        'small practical surf details that clarify risk and decision-making',
      ],
      limits: [
        'no surrealism',
        'no supernatural events',
        'no catastrophic rescue sequence unless explicitly requested',
        'no major new plotline unrelated to the sick-day surf premise',
        'no exaggerated recklessness',
        'no melodramatic confession scene',
        'no ignoring the support matrix',
      ],
      plot_risk_level: 'moderate',
      realism_requirement: 'Every major beat must be explainable through character choice, surf conditions, reef constraints, social etiquette, heat, fatigue, or phone obligations.',
    }
    const beatIds = [
      'opening_image',
      'the_lie',
      'entering_the_water',
      'failed_or_hesitant_attempt',
      'kai_restraint',
      'mid_scene_tension',
      'decisive_set',
      'resolution',
    ]
    const normalizedRows = rows.map((row) => ({
      id: row.id,
      name: row.name,
      category: storyRowCategory(row),
      objects: splitStoryObjects(row.objects),
      environment_ref: 'env-0',
      environment: row.environment,
      dynamics: row.dynamics,
      note: row.note,
      is_complete: row.isComplete,
      contact_sheet: contactSheetDecisionForStoryRow(row),
    }))
    const sourceContext = {
      core_idea: coreIdea,
      author: {
        id: writer || null,
        name: requestedAuthor,
        memory_style_context: authorMemoryStyle,
        expanded_style_guide: expandedAuthorStyleGuide,
      },
      location: {
        place: 'Kahaluʻu Bay',
        region: 'Kona Coast',
        island: 'Big Island',
        weekday: 'Wednesday',
        month: 'June',
        year: 2024,
        time_window: 'daylight surf window',
        display: location,
      },
      environment: {
        id: 'env-0',
        description: environment,
        active_pressures: [
          'sweat',
          'glare',
          'wax softness',
          'saltwater',
          'fatigue',
          'grip changes',
          'footing changes',
          'board control changes',
          'reef caution',
          'social patience',
        ],
      },
      interaction_rows: normalizedRows,
      linked_assets: linkedAssets.map((asset) => ({
        id: asset.id,
        title: asset.title,
        description: asset.description || '',
        memory_key: asset.memoryKey || null,
        media_type: asset.mediaType || 'unknown',
        source: asset.source || null,
        visibility: asset.description ? 'caption_grounded' : 'metadata_only',
      })),
    }
    const generationDirectives = {
      thematic_pivot: 'Autonomy vs. Obligation',
      author_style_directive: authorStyleDirective,
      creativity_directive: creativityDirective,
    }
    const assetPolicy = {
      visibility: linkedAssets.some((asset) => asset.description) ? 'caption_grounded_or_metadata_only' : 'metadata_only',
      rule: 'Use stored media descriptions when present. If a linked asset lacks a description, use its title only and do not invent visual, audio, or video details from an inaccessible URL.',
      allowed_asset_use: [
        'character identity continuity',
        'surfing pose and board continuity',
        'environment and coastline continuity',
        'sound or video reference only when a stored description exists',
      ],
      forbidden_asset_use: [
        'do not infer facial features from a URL',
        'do not infer body type from a URL',
        'do not infer colors or clothing beyond prompt fields and stored descriptions',
        'do not claim to have seen media that is metadata-only',
      ],
    }
    const responseContract = {
      type: 'object',
      additionalProperties: false,
      required: [
        'story',
        'panel_count',
        'duration_seconds',
        'location',
        'environment',
        'panel',
        'panels',
        'interaction_matrix',
        'asset_usage',
        'style_application',
        'quality_checks',
      ],
      properties: {
        story: {
          type: 'string',
          minLength: targetStoryLengthWords.min * 4,
          maxLength: targetStoryLengthWords.max * 9,
          description: `A concise, human-written story beat for ${panelCount} panel(s) and ${durationSeconds} seconds, approximately ${targetStoryLengthWords.min}-${targetStoryLengthWords.max} words.`,
        },
        panel_count: {
          type: 'number',
          const: panelCount,
          description: 'The exact number of story panels requested by the Phase 02 controls.',
        },
        duration_seconds: {
          type: 'number',
          const: durationSeconds,
          description: 'Target duration represented by the requested panel sequence.',
        },
        location: {
          type: 'object',
          additionalProperties: false,
          required: ['place', 'time', 'month', 'year', 'description'],
          properties: {
            place: { type: 'string', description: 'Place name and region from source_context.location.' },
            time: { type: 'string', description: 'Weekday and daylight/time window from source_context.location.' },
            month: { type: 'string', description: 'Month from source_context.location.' },
            year: { type: 'number', description: 'Year from source_context.location.' },
            description: { type: 'string', description: 'Concise setting description used by the story.' },
          },
        },
        environment: {
          type: 'object',
          additionalProperties: false,
          required: ['weather_description', 'active_pressures', 'story_effect'],
          properties: {
            weather_description: { type: 'string', description: 'Descriptive weather and surf conditions characters physically respond to.' },
            active_pressures: {
              type: 'array',
              minItems: 4,
              items: { type: 'string' },
            },
            story_effect: { type: 'string', description: 'How weather, surf, reef, and public beach pressure drive the story beat.' },
          },
        },
        panel: {
          ...panelSchema,
          description: 'Primary or first panel, duplicated from panels[0] for consumers that expect a single panel.',
        },
        panels: {
          type: 'array',
          minItems: panelCount,
          maxItems: panelCount,
          items: panelSchema,
          description: 'Exactly panel_count panels. For one panel, this array contains the same panel as panel.',
        },
        interaction_matrix: {
          type: 'array',
          minItems: rows.length,
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['source_seed_id', 'entity', 'category', 'objects_used', 'environment_interaction', 'story_function', 'visible_in_panel', 'contact_sheet'],
            properties: {
              source_seed_id: { type: 'string', description: 'Copy from source_context.interaction_rows[].id.' },
              entity: { type: 'string', description: 'Copy from source_context.interaction_rows[].name.' },
              category: {
                type: 'string',
                enum: ['character', 'character_object', 'environmental_force', 'location_social_system'],
              },
              objects_used: {
                type: 'array',
                items: { type: 'string' },
              },
              environment_interaction: { type: 'string', description: 'Complete explanation of how heat, humidity, water, reef, light, fatigue, or public etiquette changes this entity/object/force.' },
              story_function: { type: 'string', description: 'Why this row matters to the one-panel story beat and what would be missing if it were removed.' },
              visible_in_panel: { type: 'boolean' },
              contact_sheet: {
                type: 'object',
                additionalProperties: false,
                required: ['required', 'kind', 'status', 'send_to_kling', 'priority', 'rationale'],
                description: 'Whether this row needs a contact sheet/reference pack for Phase 04 video provider preparation.',
                properties: {
                  required: { type: 'boolean', description: 'True when a stable visual reference is needed for this row.' },
                  kind: { type: 'string', enum: ['character', 'prop', 'environment', 'prompt_only'] },
                  status: { type: 'string', enum: ['existing_or_required', 'missing', 'not_needed'] },
                  send_to_kling: { type: 'boolean', description: 'True only when the reference should be part of the video provider element pack.' },
                  priority: { type: 'string', enum: ['required', 'recommended', 'conditional', 'prompt_only'] },
                  rationale: { type: 'string', description: 'One sentence explaining why the row does or does not require a contact sheet.' },
                },
              },
            },
          },
        },
        asset_usage: {
          type: 'array',
          minItems: Math.min(linkedAssets.length, 1),
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['asset_id', 'used_for', 'usage_confidence'],
            properties: {
              asset_id: { type: 'string', description: 'Copy from source_context.linked_assets[].id.' },
              used_for: { type: 'string', description: 'Specific visual, audio, video, or text grounding role in the story.' },
              usage_confidence: { type: 'string', enum: ['metadata_only', 'caption_grounded', 'image_grounded', 'audio_grounded', 'video_grounded'] },
            },
          },
        },
        style_application: {
          type: 'object',
          additionalProperties: false,
          required: ['author_reference_used_as', 'creativity_level_used_as'],
          properties: {
            author_reference_used_as: { type: 'string' },
            creativity_level_used_as: { type: 'string' },
          },
        },
        quality_checks: {
          type: 'object',
          additionalProperties: false,
          required: [
            'covered_seed_ids',
            'missing_seed_ids',
            'used_only_provided_context',
            'no_direct_author_imitation',
            'valid_one_panel_10_second_moment',
          ],
          properties: {
            covered_seed_ids: {
              type: 'array',
              items: { type: 'string' },
            },
            missing_seed_ids: {
              type: 'array',
              items: { type: 'string' },
            },
            used_only_provided_context: { type: 'boolean' },
            no_direct_author_imitation: { type: 'boolean' },
            valid_one_panel_10_second_moment: { type: 'boolean' },
          },
        },
      },
    }
    const invalidIf = [
      'The response includes markdown, prose outside JSON, or a code fence.',
      'The response includes any top-level key not listed in response_contract.required.',
      'The response adds an asset_id that is not present in source_context.linked_assets[].id.',
      'The response omits any completed source_context.interaction_rows[].id from interaction_matrix[].source_seed_id.',
      'The story or panel ignores source_context.environment when describing character or object behavior.',
      'A surfboard appears but the output omits shape, wax state, condition, or age in story, panel, or interaction_matrix.',
      'The output expands into a multi-scene treatment instead of one 10-second panel beat.',
      'The output directly imitates a living author instead of using high-level craft traits.',
      'author_style_directive does not translate the requested author into high-level non-imitative craft traits.',
      'creativity_directive does not convert the slider value into concrete allowed inventions and limits.',
    ]
    const deterministicChecks = [
      'Parse response as JSON.',
      'Reject if any key outside response_contract.properties appears at the top level.',
      'Validate the JSON object against response_contract with additionalProperties=false at every object level.',
      'Check every completed source_context.interaction_rows[].id appears in interaction_matrix[].source_seed_id.',
      'Check every interaction_matrix[] row includes contact_sheet with required, kind, status, send_to_kling, priority, and rationale.',
      'Check every asset_usage[].asset_id exists in source_context.linked_assets[].id.',
      'Check quality_checks.missing_seed_ids is empty.',
      'Check quality_checks.used_only_provided_context, no_direct_author_imitation, and valid_one_panel_10_second_moment are true.',
      'If any interaction row entity contains "surfboard", require the output text to mention shape, wax, condition, or age.',
      'Check style_application explains how the author reference and creativity slider were converted into behavior.',
    ]
    const example = {
      input: {
        context: {
          core_idea: 'Embry and Kai fake a sick day to surf at Kahaluʻu Bay.',
          location: 'Kahaluʻu Bay, Kona Coast · Wednesday · daylight surf window · June · 2024',
          environment: 'Hot humid air, bright glare, lava reef, and soft wax change footing and timing.',
          interaction_rows: [
            {
              id: 'seed-embry',
              name: 'Embry',
              category: 'character',
              objects: ['navy rashguard', 'waxed older white shortboard', 'phone'],
              environment_ref: 'env-0',
              dynamics: 'Glare and fatigue make timing a physical test.',
              note: 'Show salt, sweat, careful rail grip, and hesitation before the wave.',
              is_complete: true,
              contact_sheet: {
                required: true,
                kind: 'character',
                status: 'existing_or_required',
                send_to_kling: true,
                priority: 'required',
                rationale: 'Embry identity continuity must be locked before video provider generation.',
              },
            },
          ],
          linked_assets: [
            {
              id: 'embry_media_asset__example_png',
              title: 'Embry surfing reference',
              description: 'Embry crouches on a white surfboard with lava rocks and green mountains behind her.',
              memoryKey: 'embry_media_asset__example_png',
              mediaType: 'image',
              visibility: 'caption_grounded',
            },
          ],
        },
      },
      expected_output: {
        story: 'Embry’s phone buzzes inside the beach bag just as a clean shoulder stands up over the reef; she squints through the glare, palms slipping on sun-soft wax, and chooses the paddle while Kai, already angled safely outside, only lifts two fingers toward the channel instead of telling her what to do.',
        panel_count: panelCount,
        duration_seconds: durationSeconds,
        location: {
          place: 'Kahaluʻu Bay, Kona Coast, Big Island',
          time: 'Wednesday daylight surf window',
          month: 'June',
          year: 2024,
          description: 'A public Kona Coast surf break where private escape is constrained by shared lineup rules.',
        },
        environment: {
          weather_description: 'Hot, humid coastal air with bright glare, saltwater, summer swell, shallow lava reef, and sun-softened wax.',
          active_pressures: ['heat', 'humidity', 'glare', 'softened wax', 'fatigue', 'lava reef caution', 'local etiquette'],
          story_effect: 'The weather and reef make each surf decision physical: grip, timing, patience, and restraint all matter.',
        },
        panel: {
          shot: 'Low waterline three-quarter shot facing the reef line, with Embry in the foreground on the older white shortboard and Kai farther out, half-turned toward the incoming set.',
          action: 'A June swell rises over the dark lava shapes; Embry commits to the paddle despite sweat, glare, and the phone buzzing onshore.',
          emotional_turn: 'Embry moves from borrowed escape to embodied choice: she is still obligated, still exposed, but the decision is hers.',
          dialogue: null,
        },
        panels: [
          {
            shot: 'Low waterline three-quarter shot facing the reef line, with Embry in the foreground on the older white shortboard and Kai farther out, half-turned toward the incoming set.',
            action: 'A June swell rises over the dark lava shapes; Embry commits to the paddle despite sweat, glare, and the phone buzzing onshore.',
            emotional_turn: 'Embry moves from borrowed escape to embodied choice: she is still obligated, still exposed, but the decision is hers.',
            dialogue: null,
          },
        ],
        interaction_matrix: [
          {
            source_seed_id: 'seed-embry',
            entity: 'Embry',
            category: 'character',
            objects_used: ['navy rashguard', 'waxed older white shortboard', 'phone'],
            environment_interaction: 'Humidity softens wax, glare hides the reef line, and fatigue makes her commitment visible.',
            story_function: 'Turns autonomy into a bodily choice in the exact surf moment.',
            visible_in_panel: true,
            contact_sheet: {
              required: true,
              kind: 'character',
              status: 'existing_or_required',
              send_to_kling: true,
              priority: 'required',
              rationale: 'Embry appears in the panel and needs stable character identity continuity.',
            },
          },
        ],
        asset_usage: [
          {
            asset_id: 'embry_media_asset__example_png',
            used_for: 'Embry body posture, surfboard color, lava rock coastline, and mountain backdrop.',
            usage_confidence: 'caption_grounded',
          },
        ],
        style_application: {
          author_reference_used_as: 'High-level craft guidance: practical cause-and-effect staging, physical constraints, and dry restraint without direct imitation.',
          creativity_level_used_as: 'Grounded moderate invention: a plausible phone buzz and decisive swell heighten the moment without breaking realism.',
        },
        quality_checks: {
          covered_seed_ids: ['seed-embry'],
          missing_seed_ids: [],
          used_only_provided_context: true,
          no_direct_author_imitation: true,
          valid_one_panel_10_second_moment: true,
        },
      },
    }
    const rawPrompt = [
      '## Role',
      'You are the Phase 02 Story author for Embry OS.',
      '',
      '## Task',
      `Generate an original ${panelCount}-panel, ${durationSeconds}-second story beat for the Phase 02 Story pane. Return one JSON object that matches the Output Format section at the end of this prompt.`,
      '',
      '## Input Field Paths',
      '- source_context.core_idea: story directive text.',
      '- source_context.location: place, weekday, daylight/time window, month, and year.',
      '- source_context.environment.description: weather, heat, humidity, swell, reef, light, water, fatigue, and physical constraints.',
      '- source_context.environment.active_pressures[]: specific physical pressures the story must operationalize.',
      '- source_context.interaction_rows[].id: stable row id that must be copied into interaction_matrix[].source_seed_id.',
      '- source_context.interaction_rows[].category: one of character, character_object, environmental_force, location_social_system.',
      '- source_context.interaction_rows[].objects[]: physical objects or body-worn items.',
      '- source_context.interaction_rows[].dynamics: how the row behaves under the environment.',
      '- source_context.interaction_rows[].note: script/panel staging instruction.',
      '- source_context.interaction_rows[].contact_sheet: deterministic Phase 04 reference-pack decision. Copy and refine this into interaction_matrix[].contact_sheet.',
      '- source_context.linked_assets[].id: stable asset id that must be copied into asset_usage[].asset_id.',
      '- source_context.linked_assets[].description: stored image, sound, video, or text description.',
      '- source_context.author.memory_style_context: selected persona memory style that determines how the story is written.',
      '- generation_directives.author_style_directive: high-level, non-imitative author craft traits.',
      '- generation_directives.creativity_directive: slider value translated into concrete generation behavior.',
      '- response_contract: strict JSON schema suitable for Pydantic/dataclass validation.',
      '',
      '## Source Material',
      '<source_context>',
      JSON.stringify(sourceContext, null, 2),
      '</source_context>',
      '',
      '## Generation Directives',
      '<generation_directives>',
      JSON.stringify(generationDirectives, null, 2),
      '</generation_directives>',
      '',
      '## Asset Policy',
      JSON.stringify(assetPolicy, null, 2),
      '',
      '## Constraints',
      '- Use only facts present in source_context and generation_directives.',
      '- Do not imitate any living author directly. Apply generation_directives.author_style_directive as high-level craft guidance only.',
      '- The selected author determines prose behavior. Use source_context.author.memory_style_context and generation_directives.author_style_directive to shape rhythm, humor, technical detail, and causality.',
      '- Apply generation_directives.creativity_directive. Creativity 0.6 means grounded moderate invention, not surrealism or melodrama.',
      '- Treat the environment as plot machinery, not scenery.',
      `- Produce exactly ${panelCount} panel(s) totaling ${durationSeconds} seconds, not a full short story and not an eight-beat treatment.`,
      `- Set panel_count to ${panelCount} and duration_seconds to ${durationSeconds}.`,
      `- Return panels[] with exactly ${panelCount} item(s), and set panel equal to panels[0].`,
      `- Keep story to roughly ${targetStoryLengthWords.min}-${targetStoryLengthWords.max} words so the panel sequence stays focused.`,
      '- Include one interaction_matrix row for every source_context.interaction_rows[] item where is_complete is true.',
      '- The interaction_matrix is the completeness ledger: every character, object, location, environmental force, and relevant pressure used by the story must be explained there.',
      '- Every interaction_matrix row must include contact_sheet. Characters require character contact sheets. Visually specific hero props such as surfboards require prop sheets when visible. Stable locations/environments require compact environment sheets when they anchor a video provider panel. Abstract pressures such as heat, humidity, glare, fatigue, etiquette, and timing are prompt-only unless embodied by a stable visual element.',
      '- Do not mark send_to_kling true for abstract forces alone. Do mark send_to_kling true for Embry, Kai, visible surfboards, and the active surf-break environment when they appear in the panel.',
      '- Include asset_usage rows only for source_context.linked_assets[] entries that influence the story.',
      '- Include top-level location and environment objects. They must be populated from source_context.location and source_context.environment, not omitted.',
      '- Copy asset_usage[].asset_id from source_context.linked_assets[].id.',
      '- Copy interaction_matrix[].source_seed_id from source_context.interaction_rows[].id.',
      '- If Embry, Kai, a surfboard, reef, swell, phone, heat, humidity, glare, wax, or fatigue appears in source_context, show how it changes visible behavior.',
      '- If a surfboard appears, mention shape, wax state, condition, or age in story or interaction_matrix.',
      '- Show Kai competence through restraint and efficient movement, not lecturing.',
      '- Show Embry autonomy through physical choices: hand placement, rail grip, paddle fatigue, uncertain footing, and commitment or withdrawal near reef.',
      '- Keep dialogue sparse, practical, and character-revealing.',
      '- Avoid generic surf cliches, melodrama, reckless danger, and savior dynamics.',
      '',
      '## Invalid Output',
      ...invalidIf.map((item) => `- ${item}`),
      '',
      '## Complete Example',
      'Example input:',
      JSON.stringify(example.input, null, 2),
      '',
      'Expected output:',
      JSON.stringify(example.expected_output, null, 2),
      '',
      '## Output Format',
      'Output NOTHING but one raw JSON object. No markdown fence, heading, preamble, explanation, or trailing notes.',
      'Start with { and end with }.',
      'Return this exact JSON schema:',
      JSON.stringify(responseContract, null, 2),
    ].join('\n')
    return {
      schema: 'dream.story.prompt_payload.v1',
      rationale: {
        purpose: 'Generate one grounded Phase 02 Embry/Kai story treatment JSON object from Phase 02 story inputs.',
        consumer: 'ux-lab /dream#story Author Console -> /api/tau/dream/story-draft -> Tau story-writer/story-editor loop.',
        why_this_matters: 'Bad output breaks storyboard generation by inventing assets, omitting environment physics, or producing prose that cannot populate the interaction matrix.',
        input: [
          'context.core_idea',
          'context.location',
          'context.environment',
          'context.interaction_rows[]',
          'context.linked_assets[]',
          'author_profile',
        ],
        output: 'JSON object matching response_contract; consumed by Tau story agents and the Phase 02 Story Area.',
        last_reviewed: '2026-07-01 by Graham/Codex',
      },
      metadata: {
        phase: '02',
        timestamp: new Date().toISOString(),
        gate_state: gateState,
      },
      model: {
        provider: 'tau',
        model: 'gpt-5.5',
        reasoning_effort: 'medium',
        temperature: creativity,
      },
      task: {
        kind: storyKind,
        panel_count: panelCount,
        target_duration_seconds: durationSeconds,
        target_story_length_words: targetStoryLengthWords,
        output_format: 'strict_json',
      },
      generation_directives: generationDirectives,
      source_context: sourceContext,
      asset_policy: assetPolicy,
      context: {
        thematic_pivot: 'Autonomy vs. Obligation',
        core_idea: coreIdea,
        location,
        environment,
        interaction_rows: normalizedRows.map((row) => ({
          id: row.id,
          name: row.name,
          objects: row.objects.join(', '),
          environment: row.environment,
          dynamics: row.dynamics,
          note: row.note,
          isComplete: row.is_complete,
          contact_sheet: row.contact_sheet,
        })),
        linked_assets: linkedAssets,
      },
      author_profile: {
        persona_id: writer || null,
        persona: requestedAuthor,
        persona_context: selectedWriter?.description || null,
        creativity_index: creativity,
      },
      response_contract: responseContract,
      output_contract: responseContract,
      validation: {
        deterministic_checks: deterministicChecks,
        invalid_if: invalidIf,
      },
      example,
      messages: [
        {
          role: 'system',
          content: 'You are the Phase 02 Story author for Embry OS. Follow the user prompt exactly. Return only the requested JSON object.',
        },
        {
          role: 'user',
          content: rawPrompt,
        },
      ],
    }
  }

  const generateDraft = async () => {
    const payload = buildStoryPromptPayload()
    setIsGenerating(true)
    updateGenerateStatus('Dispatching Tau story loop...')
    try {
      const response = await fetch('/api/tau/dream/story-draft', {
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
        throw new Error(message)
      }
      const story = typeof data?.story_contract?.story === 'string' && data.story_contract.story.trim().length > 0
        ? data.story_contract.story.trim()
        : JSON.stringify(data, null, 2)
      updateDraft(story)
      const receipt = typeof data?.manifest_path === 'string' ? data.manifest_path : 'Tau receipt unavailable'
      updateGenerateStatus(`Tau story loop ${data?.status || 'returned'}: ${receipt}`)
    } catch (error) {
      updateGenerateStatus(`Draft failed: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const copyDebugPayload = async () => {
    const payload = buildStoryPromptPayload()
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }
  useEffect(() => {
    const handleHeaderCopy = () => { void copyDebugPayload() }
    window.addEventListener('dream:copy-story-payload', handleHeaderCopy)
    return () => window.removeEventListener('dream:copy-story-payload', handleHeaderCopy)
  })
  const storyText = useMemo(() => storyDisplayText(draft), [draft])
  const storyGlossary = useMemo(() => storyEntityGlossary(draft), [draft])
  const selectedWriterForDisplay = writers.find((option) => option.id === writer)
  const writerStylePreview = authorStyleGuide(
    selectedWriterForDisplay?.label || writer || 'unselected_author',
    selectedWriterForDisplay?.description || ''
  )
  return (
    <section data-qid="dream:story:director-console" style={nvis.directorConsole}>
      <div data-qid="dream:story:core-idea" style={nvis.directorIdeaBand}>
        <span style={nvis.directorLabel}><Lightbulb size={12} /> Core Idea</span>
        <p style={nvis.directorIdeaText}>{coreIdea || 'No core idea supplied for this story pass.'}</p>
      </div>
      <div style={nvis.directorControls}>
        <span style={nvis.directorLabel}><UserRound size={12} /> Author</span>
        <div style={nvis.directorCommandColumn}>
          <div style={nvis.directorCommandStrip}>
            <label style={nvis.directorAuthorGroup}>
              <span style={nvis.directorSelectWrap}>
                <select
                  data-qid="dream:story:writer"
                  data-qs-action="DREAM_STORY_WRITER_SELECT"
                  title="Choose author persona"
                  value={writer}
                  onChange={(event) => setWriter(event.target.value)}
                  style={nvis.directorSelect}
                >
                  {writers.length === 0 && <option value="">No memory writers found</option>}
                  {writers.map((option) => (
                    <option key={option.id} value={option.id}>{option.label}</option>
                  ))}
                </select>
                <ChevronDown size={13} style={nvis.directorSelectIcon} />
              </span>
            </label>
            <label style={nvis.directorSliderGroup}>
              <span style={nvis.directorSliderHeader}>
                <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
                <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
              </span>
              <input
                data-qid="dream:story:creativity"
                data-qs-action="DREAM_STORY_CREATIVITY_SET"
                title="Adjust story creativity"
                aria-label="Adjust story creativity"
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
              <span style={nvis.directorLabel}><Clapperboard size={12} /> Panels</span>
              <input
                data-qid="dream:story:panel-count"
                data-qs-action="DREAM_STORY_PANEL_COUNT_SET"
                title="Set story panel count"
                aria-label="Set story panel count"
                type="number"
                min="1"
                max="8"
                step="1"
                value={panelCount}
                onChange={(event) => setPanelCount(Math.max(1, Math.min(8, Math.round(Number(event.target.value) || 1))))}
                style={nvis.directorNumberInput}
              />
            </label>
            <label style={nvis.directorNumberGroup}>
              <span style={nvis.directorLabel}><Play size={12} /> Seconds</span>
              <input
                data-qid="dream:story:duration-seconds"
                data-qs-action="DREAM_STORY_DURATION_SET"
                title="Set story duration in seconds"
                aria-label="Set story duration in seconds"
                type="number"
                min="1"
                max="120"
                step="1"
                value={durationSeconds}
                onChange={(event) => setDurationSeconds(Math.max(1, Math.min(120, Math.round(Number(event.target.value) || 10))))}
                style={nvis.directorNumberInput}
              />
            </label>
            <button
              type="button"
              data-qid="dream:story:generate"
              data-qs-action="DREAM_STORY_GENERATE"
              title="Dispatch Phase 02 story prompt payload to Tau"
              disabled={isGenerating}
              onClick={() => { void generateDraft() }}
              style={{
                ...nvis.directorGenerateBtn,
                ...(isGenerating ? nvis.directorBtnDisabled : null),
              }}
            >
              <Sparkles size={14} />
              {isGenerating ? 'Dispatching' : 'Draft Story'}
            </button>
            <button
              type="button"
              data-qid="dream:story:copy-debug-payload"
              title="Copy Phase 02 story prompt payload JSON"
              onClick={() => { void copyDebugPayload() }}
              style={nvis.directorDebugBtn}
            >
              {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
              {copyStatus || 'Copy Payload'}
            </button>
          </div>
          <div data-qid="dream:story:author-style" style={nvis.directorInlineStylePreview}>
            <span style={nvis.directorInlineStyleLabel}><FileText size={12} /> Author Style</span>
            <p style={nvis.directorStyleText}>{writerStylePreview}</p>
          </div>
        </div>
      </div>
      {generateStatus && (
        <div data-qid="dream:story:generation-status" style={nvis.directorStatusRow}>
          <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
          <span style={nvis.directorStatus}>{compactStoryStatus(generateStatus)}</span>
        </div>
      )}
      <div style={nvis.directorStoryAreaWrap}>
        <span style={nvis.directorLabel}><BookOpen size={12} /> Story Area</span>
        <div style={nvis.directorStoryContent}>
          <div
            data-qid="dream:story:highlighted-canvas"
            title="Generated story with memory and interaction-matrix entity highlighting"
            style={nvis.directorStoryCanvas}
          >
            {storyText
              ? highlightWithGlossary(storyText, storyGlossary)
              : <span style={nvis.directorStoryPlaceholder}>Generate the Phase 02 story beat here.</span>}
          </div>
          <details style={nvis.directorJsonDetails}>
            <summary style={nvis.directorJsonSummary}>Edit JSON payload</summary>
            <textarea
              data-qid="dream:story:draft"
              data-qs-action="DREAM_STORY_DRAFT_EDIT"
              title="Story JSON draft area"
              value={draft}
              onChange={(event) => updateDraft(event.target.value)}
              placeholder="Generated strict story JSON will appear here..."
              style={nvis.directorStoryArea}
            />
          </details>
        </div>
      </div>
    </section>
  )
}
