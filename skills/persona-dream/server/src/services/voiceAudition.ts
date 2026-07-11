import { createHash } from 'node:crypto'
import { copyFile, mkdir, writeFile } from 'node:fs/promises'
import { existsSync, realpathSync } from 'node:fs'
import { basename, resolve } from 'node:path'
import type { VoiceAuditionPort, VoiceAuditionRequest } from './contracts'

export type ChatterboxVoiceAdapterOptions = {
  agentUrl: string
  outputRoot: string
  allowedReferenceRoots: readonly string[]
  hostOutputRoot: string
  hostReferenceRoot: string
  containerReferenceRoot: string
  fetchImpl?: typeof fetch
}

const allowedCues = new Set(['', '[laugh]', '[chuckle]', '[sigh]', '[gasp]', '[whispering]'])
const cueAliases: Record<string, string> = { laugh: '[laugh]', laughs: '[laugh]', laughing: '[laugh]', chuckle: '[chuckle]', chuckles: '[chuckle]', chuckling: '[chuckle]', sigh: '[sigh]', sighs: '[sigh]', sighing: '[sigh]', gasp: '[gasp]', gasps: '[gasp]', gasping: '[gasp]', whisper: '[whispering]', whispers: '[whispering]', whispering: '[whispering]' }
const tones = new Set(['neutral_warm', 'calm_precise', 'careful_concerned', 'serious_low_energy', 'memory_confident', 'memory_uncertain', 'curious_searching', 'playful_light', 'relieved', 'firm_boundary', 'identity_clarification', 'one_at_a_time_interrupt', 'deflect_calm', 'grief_safe', 'wait_presence'])
const toneStages: Record<string, string> = { neutral_warm: 'neutral', calm_precise: 'neutral', careful_concerned: 'slightly_concerned', serious_low_energy: 'neutral', memory_confident: 'satisfied', memory_uncertain: 'slightly_concerned', curious_searching: 'holding', playful_light: 'positive', relieved: 'satisfied', firm_boundary: 'deflecting', identity_clarification: 'clarifying', one_at_a_time_interrupt: 'deflecting', deflect_calm: 'deflecting', grief_safe: 'slightly_concerned', wait_presence: 'holding' }
const stageAliases: Record<string, string> = { setup: 'neutral', slightly_concerned: 'slightly_concerned', neutral: 'neutral', positive: 'positive', satisfied: 'satisfied', clarify: 'clarifying', clarifying: 'clarifying', boundary: 'deflecting', interrupted: 'deflecting', deflect: 'deflecting', deflecting: 'deflecting', wait: 'holding', holding: 'holding' }

function normalizedToken(value: unknown): string {
  return typeof value === 'string' ? value.trim().replace(/[^a-z0-9_-]/gi, '').toLowerCase() : ''
}

function normalizeSpacing(text: string): string { return text.replace(/[ \t]+/g, ' ').replace(/\s+([,.;:!?])/g, '$1').trim() }
function stripControls(text: string): string { return normalizeSpacing(text.replace(/\[[^\]]+\]/g, '').replace(/<[^>]+>/g, '')) }
function cueFromText(text: string): string {
  let cue = ''
  text.replace(/\[([a-z\s_-]+)\]/gi, (_match, raw: string) => { if (!cue) cue = cueAliases[raw.toLowerCase().replace(/[\s_-]+/g, '')] ?? ''; return '' })
  return cue
}
function renderText(text: string, clean: string, cue: string): string {
  const normalized = normalizeSpacing(text.replace(/\[([a-z\s_-]+)\]/gi, (_match, raw: string) => cueAliases[raw.toLowerCase().replace(/[\s_-]+/g, '')] ?? '').replace(/<[^>]+>/g, ''))
  return /\[(?:laugh|chuckle|sigh|gasp|whispering)\]/i.test(normalized) ? normalized : cue ? `${cue} ${clean}` : clean
}
function pause(value: unknown): number { const parsed = typeof value === 'number' ? value : Number(value); return Number.isFinite(parsed) ? Math.max(0, Math.min(2000, Math.round(parsed))) : 0 }

export function createChatterboxVoiceAuditionPort(options: ChatterboxVoiceAdapterOptions): VoiceAuditionPort {
  const allowedRoots = options.allowedReferenceRoots.map((root) => realpathSync(root))
  return {
    async audition(request: VoiceAuditionRequest) {
      const character = normalizedToken(request.character)
      const text = typeof request.text === 'string' ? request.text.trim() : ''
      const refAudioPath = typeof request.refAudioPath === 'string' ? request.refAudioPath : ''
      if (!['embry', 'kai'].includes(character)) throw new Error('character must be embry or kai')
      if (!text) throw new Error('text required')
      if (text.length > 1200) throw new Error('text exceeds 1200 characters')
      const cleanText = stripControls(text)
      if (!cleanText) throw new Error('text contains only unsupported speech controls')
      const refReal = realpathSync(refAudioPath)
      if (!allowedRoots.some((root) => refReal === root || refReal.startsWith(`${root}/`))) throw new Error('refAudioPath not allowed')
      const toneCandidate = normalizedToken(request.tone)
      const tone = tones.has(toneCandidate) ? toneCandidate : 'neutral_warm'
      const requestedStage = normalizedToken(request.deliveryStage)
      const deliveryStage = stageAliases[requestedStage] ?? toneStages[tone] ?? 'neutral'
      const requestedCue = typeof request.paralinguisticCue === 'string' ? request.paralinguisticCue.trim().toLowerCase() : typeof request.emotionTag === 'string' ? request.emotionTag.trim().toLowerCase() : ''
      const selectedCue = allowedCues.has(requestedCue) ? requestedCue : ''
      const inlineCue = cueFromText(text)
      const paralinguisticCue = selectedCue || inlineCue
      const ttsRenderText = renderText(text, cleanText, selectedCue)
      const stagedRef = resolve(options.hostReferenceRoot, basename(refReal))
      const chatterboxRef = existsSync(stagedRef) ? `${options.containerReferenceRoot.replace(/\/+$/, '')}/${basename(stagedRef)}` : refReal
      const upstream = await (options.fetchImpl ?? fetch)(`${options.agentUrl.replace(/\/+$/, '')}/synthesize`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ttsRenderText, ref_audio: chatterboxRef, label: `dream-${character}-${Date.now()}`, delivery_stage: deliveryStage, temperature: 0.7 }),
      })
      const payload = await upstream.json().catch(() => null) as Record<string, unknown> | null
      if (!upstream.ok || payload?.ok !== true) throw new Error(String(payload?.error ?? payload?.detail ?? `Chatterbox returned ${upstream.status}`))
      const rawAudio = typeof payload.audio === 'string' ? payload.audio.trim() : ''
      const generatedPath = rawAudio.startsWith('/out/') ? resolve(options.hostOutputRoot, rawAudio.slice(5)) : rawAudio
      if (!generatedPath || !existsSync(generatedPath)) throw new Error('Chatterbox returned an audio path that is not readable by persona-dream')
      const outDir = resolve(options.outputRoot, 'dream-voice-auditions')
      await mkdir(outDir, { recursive: true })
      const textHash = createHash('sha256').update(text).digest('hex').slice(0, 12)
      const outPath = resolve(outDir, `${new Date().toISOString().replace(/[:.]/g, '-')}-${character}-${textHash}.wav`)
      await copyFile(generatedPath, outPath)
      const receiptPath = outPath.replace(/\.wav$/i, '.json')
      const pauseBeforeMs = pause(request.pauseBeforeMs)
      const pauseAfterMs = pause(request.pauseAfterMs)
      await writeFile(receiptPath, JSON.stringify({ schema: 'persona_dream.voice_audition_receipt.v1', created_at: new Date().toISOString(), mocked: false, live: true, character, answer_text: cleanText, answer_text_sha256: createHash('sha256').update(cleanText).digest('hex'), tts_render_text: ttsRenderText, tts_render_text_sha256: createHash('sha256').update(ttsRenderText).digest('hex'), tone, delivery_stage: deliveryStage, paralinguistic_cue: paralinguisticCue, chatterbox_tags: paralinguisticCue ? [paralinguisticCue] : [], selected_paralinguistic_cue: selectedCue, inline_paralinguistic_cue: inlineCue, pause_before_ms: pauseBeforeMs, pause_after_ms: pauseAfterMs, ref_audio: refReal, chatterbox_ref_audio: chatterboxRef, chatterbox_agent_url: options.agentUrl, chatterbox_receipt: payload, output_wav: outPath }, null, 2))
      return { status: 'ok', mocked: false, live: true, character, audioPath: outPath, audioUrl: `/api/projects/dream/asset?path=${encodeURIComponent(outPath)}`, receiptPath, receiptUrl: `/api/projects/dream/asset?path=${encodeURIComponent(receiptPath)}`, durationSeconds: payload.duration_seconds, ttsRenderText, tone, deliveryStage, paralinguisticCue, chatterboxTags: paralinguisticCue ? [paralinguisticCue] : [], selectedParalinguisticCue: selectedCue, inlineParalinguisticCue: inlineCue, pauseBeforeMs, pauseAfterMs }
    },
  }
}
