/**
 * VoiceBoard, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { assetExtension, dreamAssetUrl } from '../lib/asset'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { nvis } from '../styles'
import { Mic2, Play, RotateCcw, Volume2 } from 'lucide-react'

export function VoiceBoard({ stage }: { stage: DreamStage }) {
  const ready = isStagePassed(stage)
  const toneOptions = [
    { value: 'neutral_warm', label: 'Neutral warm' },
    { value: 'calm_precise', label: 'Calm precise' },
    { value: 'careful_concerned', label: 'Careful concerned' },
    { value: 'serious_low_energy', label: 'Serious low energy' },
    { value: 'memory_confident', label: 'Memory confident' },
    { value: 'memory_uncertain', label: 'Memory uncertain' },
    { value: 'curious_searching', label: 'Curious searching' },
    { value: 'playful_light', label: 'Playful light' },
    { value: 'relieved', label: 'Relieved' },
    { value: 'firm_boundary', label: 'Firm boundary' },
    { value: 'identity_clarification', label: 'Identity clarification' },
    { value: 'one_at_a_time_interrupt', label: 'One at a time interrupt' },
    { value: 'deflect_calm', label: 'Deflect calm' },
    { value: 'grief_safe', label: 'Grief safe' },
    { value: 'wait_presence', label: 'Wait presence' },
  ]
  const pauseOptions = [
    { value: '0', label: 'No pause' },
    { value: '250', label: '250ms' },
    { value: '500', label: '500ms' },
    { value: '750', label: '750ms' },
  ]
  const voiceProfiles = useMemo(() => ([
    {
      id: 'embry',
      name: 'Embry',
      role: 'Lead voice',
      thumbnail: '/mnt/storage12tb/media/personas/embry/assets/surfing/embry_surfing_big_island_2024.png',
      refAudio: '/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated/bakeoff/runs/voice_route_refresh_20260609T0800Z/reference/embry_authorized_ref_30s_8s.wav',
      status: 'Chatterbox reference available',
      defaultText: "Kai, wait. If we paddle now, we're cutting across the lineup.",
    },
    {
      id: 'kai',
      name: 'Kai',
      role: 'Secondary voice',
      thumbnail: '/mnt/storage12tb/media/personas/kai_akana/assets/contact_sheets/kai_akana_character_sheet.png',
      refAudio: '/mnt/storage12tb/skills/persona-dream/outputs/kai-voice-kling-reference-20260703/kai_kling_chatterbox_reference_30s.wav',
      status: '30s Kai reference ready',
      defaultText: "One more set. Watch the reef line, then angle left.",
    },
  ]), [])
  const [auditionText, setAuditionText] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, profile.defaultText])))
  const [tone, setTone] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, 'neutral_warm'])))
  const [pauseBeforeMs, setPauseBeforeMs] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, '250'])))
  const [renderStatus, setRenderStatus] = useState<Record<string, string>>({})

  const playReference = (profile: typeof voiceProfiles[number]) => {
    const url = dreamAssetUrl(profile.refAudio)
    if (!url) return
    const audio = new Audio(url)
    void audio.play()
  }

  const renderDemo = async (profile: typeof voiceProfiles[number]) => {
    const text = (auditionText[profile.id] || '').trim()
    if (!text) {
      setRenderStatus((current) => ({ ...current, [profile.id]: 'Enter audition text first.' }))
      return
    }
    setRenderStatus((current) => ({ ...current, [profile.id]: 'Rendering through Chatterbox...' }))
    try {
      const response = await fetch('/api/projects/dream/voices/audition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character: profile.id,
          text,
          refAudioPath: profile.refAudio,
          tone: tone[profile.id] || 'neutral_warm',
          pauseBeforeMs: Number(pauseBeforeMs[profile.id] || 0),
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload?.status !== 'ok' || !payload?.audioUrl) {
        setRenderStatus((current) => ({
          ...current,
          [profile.id]: payload?.error || 'Chatterbox audition failed; server did not return audio.',
        }))
        return
      }
      const delayMs = Number(payload.pauseBeforeMs ?? pauseBeforeMs[profile.id] ?? 0)
      setRenderStatus((current) => ({ ...current, [profile.id]: `Rendered ${payload.durationSeconds ?? 'audio'}s demo${delayMs ? ` with ${delayMs}ms pause` : ''}.` }))
      const audio = new Audio(payload.audioUrl)
      window.setTimeout(() => { void audio.play() }, Number.isFinite(delayMs) ? delayMs : 0)
    } catch (error) {
      setRenderStatus((current) => ({
        ...current,
        [profile.id]: error instanceof Error ? error.message : 'Chatterbox audition request failed.',
      }))
    }
  }

  return (
    <div data-qid="voice-plugin" style={nvis.voicePlugin}>
      <div style={nvis.voiceHeaderRow}>
        <span style={nvis.voiceMeta}><Mic2 size={13} /> Chatterbox / provider voice references</span>
        <span style={ready ? nvis.matrixReadyPill : nvis.matrixMutedPill}>{ready ? 'Voice gate ready' : 'Voice gate pending'}</span>
      </div>
      {voiceProfiles.map((profile) => {
        const status = renderStatus[profile.id]
        return (
          <div key={profile.id} data-qid={`dream:voice-card:${profile.id}`} style={nvis.voiceChannelCard}>
            <div style={nvis.voicePortraitFrame}>
              <img src={dreamAssetUrl(profile.thumbnail)} alt={`${profile.name} thumbnail`} style={nvis.voicePortrait} />
            </div>
            <div style={nvis.voiceCardBody}>
              <div style={nvis.voiceCardTopline}>
                <span style={nvis.voiceName}>{profile.name}</span>
                <span style={nvis.voiceRole}>{profile.role}</span>
              </div>
              <span style={nvis.voiceStatus}>{profile.status}</span>
              <textarea
                style={nvis.voiceAuditionTextarea}
                value={auditionText[profile.id] || ''}
                onChange={(event) => setAuditionText((current) => ({ ...current, [profile.id]: event.target.value }))}
                placeholder={`Type ${profile.name}'s demo line...`}
                data-qid={`dream:voice:text:${profile.id}`}
                data-qs-action="DREAM_VOICE_AUDITION_TEXT"
              />
              <div style={nvis.voicePerformanceRow}>
                <label style={nvis.voiceControlLabel}>
                  Tone
                  <select
                    value={tone[profile.id] || 'neutral_warm'}
                    onChange={(event) => setTone((current) => ({ ...current, [profile.id]: event.target.value }))}
                    style={nvis.voiceSelect}
                    data-qid={`dream:voice:tone:${profile.id}`}
                    data-qs-action="DREAM_VOICE_TONE"
                  >
                    {toneOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label style={nvis.voiceControlLabel}>
                  Playback pause
                  <select
                    value={pauseBeforeMs[profile.id] || '0'}
                    onChange={(event) => setPauseBeforeMs((current) => ({ ...current, [profile.id]: event.target.value }))}
                    style={nvis.voiceSelect}
                    data-qid={`dream:voice:pause:${profile.id}`}
                    data-qs-action="DREAM_VOICE_PAUSE"
                  >
                    {pauseOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
              </div>
              <div style={nvis.voiceActionRow}>
                <button
                  type="button"
                  data-qid={`dream:voice-reference:${profile.id}`}
                  data-qs-action="DREAM_VOICE_PLAY_REFERENCE"
                  title={`Play ${profile.name} reference sample`}
                  onClick={() => playReference(profile)}
                  style={nvis.voiceGhostBtn}
                >
                  <Volume2 size={14} />
                  Reference
                </button>
                <button
                  type="button"
                  data-qid={`dream:voice-render:${profile.id}`}
                  data-qs-action="DREAM_VOICE_RENDER_DEMO"
                  title={`Render ${profile.name} demo through Chatterbox`}
                  onClick={() => { void renderDemo(profile) }}
                  style={nvis.voicePrimaryBtn}
                >
                  <Play size={13} />
                  Demo Voice
                </button>
                {status && <span style={nvis.voiceRenderStatus}>{status}</span>}
              </div>
            </div>
          </div>
        )
      })}
      <div style={nvis.voiceCommitRow}>
        <span style={nvis.voiceMeta}>Kai reference is shared by Chatterbox local ref_audio and provider voice upload.</span>
        <button
          type="button"
          data-qid="dream:voice-commit"
          data-qs-action="DREAM_VOICE_COMMIT"
          disabled={!ready}
          style={{ ...nvis.voiceCommitBtn, ...(!ready ? nvis.disabled : null) }}
        >
          <RotateCcw size={12} />
          Commit
        </button>
      </div>
    </div>
  )
}
