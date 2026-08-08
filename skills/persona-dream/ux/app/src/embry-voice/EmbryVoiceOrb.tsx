import { useEffect, useRef } from 'react'
import { useEmbryOrbContainerSize } from '../hooks/useEmbryOrbContainerSize'
import { useEmbryDecodedAudioBands, useEmbryEnvelopeAudioBands, useEmbryPlaybackAudioBands, type EmbryPlaybackAudioBands, type EmbryVoiceEnvelope } from '../hooks/useEmbryPlaybackAudioLevel'
import { resolveEmbryVisualState } from './embryOrbState'
import type { IdentitySignal } from './identityNodeState'

export type EmbryVoiceStatus = 'off' | 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
export type EmbryState = 'idle' | 'listening' | 'thinking' | 'synthesizing' | 'speaking'

type FlowParticle = {
  x: number
  y: number
  homeX: number
  homeY: number
  targetX: number
  targetY: number
  vx: number
  vy: number
  speed: number
  seed: number
  fieldAffinity: number
  glyphWeight: number
  flockIndex: number
  brightness: number
}

type EngineState = {
  visualState: EmbryState
  reducedMotion: boolean
  audio: EmbryPlaybackAudioBands
  attentionBoost: number
  releaseBoost: number
  phaseSpeedMs: number
}

const MICRO_CANVAS_SIZE = 400
const PARTICLE_COUNT = 6500
const GLYPH_PARTICLE_RATIO = 0.48
const GLYPH_FIELD_SCALE = 1.42
const IDLE_FLOCK_COUNT = 7
const DEFAULT_PHASE_SPEED_MS = 650
const MIN_PHASE_SPEED_MS = 250
const MAX_PHASE_SPEED_MS = 1400
const BACKGROUND = '#0c0c0e'
const SILENT_AUDIO: EmbryPlaybackAudioBands = { level: 0, bass: 0, mid: 0, treble: 0 }

type GlyphPoint = {
  x: number
  y: number
  alpha: number
}

type IdleFlock = {
  x: number
  y: number
  strength: number
  radius: number
  phase: number
}

function clampPhaseSpeedMs(value?: number): number {
  if (!Number.isFinite(value)) return DEFAULT_PHASE_SPEED_MS
  return Math.max(MIN_PHASE_SPEED_MS, Math.min(MAX_PHASE_SPEED_MS, Math.round(value ?? DEFAULT_PHASE_SPEED_MS)))
}

function statePalette(visualState: EmbryState): { base: [number, number, number]; hot: [number, number, number] } {
  switch (visualState) {
    case 'speaking':
      return { base: [80, 255, 180], hot: [190, 255, 225] }
    case 'synthesizing':
      return { base: [180, 100, 255], hot: [230, 205, 255] }
    case 'thinking':
      return { base: [80, 160, 255], hot: [180, 220, 255] }
    case 'listening':
      return { base: [0, 220, 170], hot: [140, 255, 220] }
    case 'idle':
    default:
      return { base: [58, 145, 255], hot: [150, 205, 255] }
  }
}

function createMask(): Float32Array {
  const maskCanvas = document.createElement('canvas')
  maskCanvas.width = MICRO_CANVAS_SIZE
  maskCanvas.height = MICRO_CANVAS_SIZE
  const ctx = maskCanvas.getContext('2d')
  const mask = new Float32Array(MICRO_CANVAS_SIZE * MICRO_CANVAS_SIZE)
  if (!ctx) return mask

  ctx.fillStyle = '#ffffff'
  ctx.font = '900 310px Inter, system-ui, -apple-system, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('e', MICRO_CANVAS_SIZE / 2, MICRO_CANVAS_SIZE / 2 + 4)

  const data = ctx.getImageData(0, 0, MICRO_CANVAS_SIZE, MICRO_CANVAS_SIZE).data
  for (let index = 0; index < data.length; index += 4) {
    mask[index / 4] = data[index + 3] / 255
  }
  return mask
}

function glyphPointsFromMask(mask: Float32Array): GlyphPoint[] {
  const points: GlyphPoint[] = []
  for (let y = 52; y < MICRO_CANVAS_SIZE - 38; y += 3) {
    for (let x = 54; x < MICRO_CANVAS_SIZE - 54; x += 3) {
      const alpha = mask[y * MICRO_CANVAS_SIZE + x]
      if (alpha > 0.45) points.push({ x, y, alpha })
    }
  }
  return points
}

function createParticles(mask: Float32Array): FlowParticle[] {
  const center = MICRO_CANVAS_SIZE / 2
  const radius = 170
  const glyphPoints = glyphPointsFromMask(mask)
  return Array.from({ length: PARTICLE_COUNT }, (_, index) => {
    const glyphParticle = glyphPoints.length > 0 && index / PARTICLE_COUNT < GLYPH_PARTICLE_RATIO
    const angle = Math.random() * Math.PI * 2
    const distance = Math.sqrt(Math.random()) * radius
    const x = center + Math.cos(angle) * distance
    const y = center + Math.sin(angle) * distance
    const glyphPoint = glyphParticle ? glyphPoints[Math.floor(Math.random() * glyphPoints.length)] : undefined
    const targetX = glyphPoint
      ? center + (glyphPoint.x - center) * GLYPH_FIELD_SCALE + (Math.random() - 0.5) * 9
      : x
    const targetY = glyphPoint
      ? center + (glyphPoint.y - center) * GLYPH_FIELD_SCALE + (Math.random() - 0.5) * 9
      : y
    const glyphWeight = glyphPoint ? 0.55 + glyphPoint.alpha * 0.45 : 0
    return {
      x,
      y,
      homeX: x,
      homeY: y,
      targetX,
      targetY,
      vx: 0,
      vy: 0,
      speed: glyphPoint ? Math.random() * 0.22 + 0.08 : Math.random() * 0.34 + 0.12,
      seed: Math.random() * 1000,
      fieldAffinity: Math.random(),
      glyphWeight,
      flockIndex: Math.floor(Math.random() * IDLE_FLOCK_COUNT),
      brightness: 0,
    }
  })
}

function maskProbability(mask: Float32Array, x: number, y: number): number {
  const px = Math.floor(x)
  const py = Math.floor(y)
  if (px < 0 || px >= MICRO_CANVAS_SIZE || py < 0 || py >= MICRO_CANVAS_SIZE) return 0
  return mask[py * MICRO_CANVAS_SIZE + px]
}

function drawFrame(
  ctx: CanvasRenderingContext2D,
  particles: FlowParticle[],
  mask: Float32Array,
  idleFlocks: IdleFlock[],
  engineState: EngineState,
  time: number,
): void {
  ctx.globalCompositeOperation = 'source-over'
  const centerX = MICRO_CANVAS_SIZE / 2
  const centerY = MICRO_CANVAS_SIZE / 2
  const active = engineState.visualState !== 'idle'
  const idle = engineState.visualState === 'idle'
  const speaking = engineState.visualState === 'speaking'
  const palette = statePalette(engineState.visualState)
  const audioLevel = speaking ? engineState.audio.level : 0
  const bassLevel = speaking ? engineState.audio.bass : 0
  const midLevel = speaking ? engineState.audio.mid : 0
  const trebleLevel = speaking ? engineState.audio.treble : 0
  const speechEnergy = speaking ? Math.min(1, audioLevel * 2.2 + midLevel * 0.35 + trebleLevel * 0.22) : 0
  const speechPulse = speaking ? 0.5 + Math.sin(time * 95) * 0.5 : 0
  ctx.fillStyle = speaking ? 'rgba(12, 12, 14, 0.18)' : 'rgba(12, 12, 14, 0.30)'
  ctx.fillRect(0, 0, MICRO_CANVAS_SIZE, MICRO_CANVAS_SIZE)

  const attentionBoost = engineState.visualState === 'listening' ? engineState.attentionBoost : 0
  const releaseBoost = idle ? engineState.releaseBoost : 0
  const forceRadius = 170
  if (idle) {
    for (let index = 0; index < idleFlocks.length; index += 1) {
      const flock = idleFlocks[index]
      const drift = time * (0.45 + index * 0.07) + flock.phase
      const orbitRadius = 72 + (index % 4) * 22
      const pulse = Math.max(0, Math.sin(drift * 1.7 + index * 0.9))
      flock.x = centerX + Math.cos(drift * 0.69) * orbitRadius + Math.sin(drift * 2.3) * 26
      flock.y = centerY + Math.sin(drift * 0.57) * (orbitRadius * 0.92) + Math.cos(drift * 1.9) * 24
      flock.radius = 44 + pulse * 48
      flock.strength = (0.0001 + pulse * pulse * 0.00062) * (0.85 + index * 0.035)
    }
  }

  ctx.globalCompositeOperation = 'lighter'
  for (let index = 0; index < particles.length; index += 1) {
    const particle = particles[index]
    const noise = Math.sin(particle.x * 0.01 + time + particle.seed)
      * Math.cos(particle.y * 0.01 + time)
      + Math.sin(particle.x * 0.02 - time + particle.seed) * 0.5
    const angle = noise * Math.PI * 4
    let dx = particle.x - centerX
    let dy = particle.y - centerY

    if (!engineState.reducedMotion) {
      const fieldForce = (idle ? 0.048 + releaseBoost * 0.08 : 0.038 + engineState.audio.bass * 0.05) * (1 - (active ? particle.glyphWeight * 0.45 : 0))
      const jitter = (idle ? 0.075 + releaseBoost * 0.22 : 0.024 + engineState.audio.treble * 0.09) * (1 - (active ? particle.glyphWeight * 0.3 : 0))
      particle.vx += Math.cos(angle) * fieldForce
      particle.vy += Math.sin(angle) * fieldForce
      particle.vx += (Math.random() - 0.5) * jitter
      particle.vy += (Math.random() - 0.5) * jitter
      const homePull = idle ? 0.00008 : 0.00045 + engineState.audio.mid * 0.00025
      particle.vx += (particle.homeX - particle.x) * homePull
      particle.vy += (particle.homeY - particle.y) * homePull
      if (particle.glyphWeight > 0) {
        const glyphPull = active ? 0.00165 + attentionBoost * 0.0038 + audioLevel * 0.00055 + midLevel * 0.00085 : 0
        particle.vx += (particle.targetX - particle.x) * glyphPull * particle.glyphWeight
        particle.vy += (particle.targetY - particle.y) * glyphPull * particle.glyphWeight
        if (releaseBoost > 0) {
          particle.vx += (particle.x - particle.targetX) * releaseBoost * 0.0048 * particle.glyphWeight
          particle.vy += (particle.y - particle.targetY) * releaseBoost * 0.0048 * particle.glyphWeight
        }
      }
      if (idle) {
        const centerDistance = Math.max(1, Math.hypot(dx, dy))
        if (centerDistance < 108) {
          const centerPush = (108 - centerDistance) * 0.00018
          particle.vx += dx / centerDistance * centerPush
          particle.vy += dy / centerDistance * centerPush
        }
        const orbit = 0.00016 + particle.fieldAffinity * 0.00014
        particle.vx += -dy * orbit
        particle.vy += dx * orbit
        particle.vx += (Math.random() - 0.5) * 0.14
        particle.vy += (Math.random() - 0.5) * 0.14
        const flock = idleFlocks[particle.flockIndex % idleFlocks.length]
        const flockDx = flock.x - particle.x
        const flockDy = flock.y - particle.y
        const flockDistanceSquared = flockDx * flockDx + flockDy * flockDy
        const swirlGate = (Math.sin(time * 2.6 + particle.seed + flock.phase) + 1) * 0.5
        if (flockDistanceSquared < flock.radius * flock.radius && swirlGate > 0.26) {
          const pull = flock.strength * (0.75 + swirlGate * 0.7)
          const swirl = flock.strength * (1.9 + particle.fieldAffinity * 1.35)
          particle.vx += flockDx * pull
          particle.vy += flockDy * pull
          particle.vx += -flockDy * swirl
          particle.vy += flockDx * swirl
        }
      }
      if (speaking) {
        const distance = Math.max(1, Math.hypot(dx, dy))
        const speechWave = Math.sin(distance * 0.105 - time * 72 + particle.seed * 0.021)
        const consonantJitter = Math.sin(time * 180 + particle.seed) * trebleLevel * 0.11
        const radialPressure = (0.032 + bassLevel * 0.19 + audioLevel * 0.34 + speechEnergy * 0.12) * (0.34 + particle.fieldAffinity)
        const wavePressure = speechWave * (0.026 + midLevel * 0.095 + speechEnergy * 0.04)
        particle.vx += (dx / distance) * (radialPressure + wavePressure)
        particle.vy += (dy / distance) * (radialPressure + wavePressure)
        particle.vx += -dy / distance * (trebleLevel * 0.085 + consonantJitter)
        particle.vy += dx / distance * (trebleLevel * 0.085 + consonantJitter)
      }
    }
    particle.vx *= idle ? 0.88 + releaseBoost * 0.07 : speaking ? 0.91 + speechEnergy * 0.035 : 0.9
    particle.vy *= idle ? 0.88 + releaseBoost * 0.07 : speaking ? 0.91 + speechEnergy * 0.035 : 0.9
    particle.x += particle.vx * particle.speed
    particle.y += particle.vy * particle.speed

    dx = particle.x - centerX
    dy = particle.y - centerY
    const distanceSquared = dx * dx + dy * dy
    if (distanceSquared > forceRadius * forceRadius) {
      particle.vx -= dx * 0.0013
      particle.vy -= dy * 0.0013
    }

    const field = maskProbability(mask, particle.x, particle.y)
    const fieldStrength = active ? field : 0
    const ignites = fieldStrength > 0 && particle.fieldAffinity < fieldStrength * (0.16 + particle.glyphWeight * 0.1)
    if (ignites) {
      const targetBrightness = 0.035
        + fieldStrength * (0.11 + attentionBoost * 0.14 + speechEnergy * 0.18)
        + particle.glyphWeight * (0.035 + attentionBoost * 0.035 + midLevel * 0.08)
        + audioLevel * 0.32
      particle.brightness += (targetBrightness - particle.brightness) * (speaking ? 0.12 : 0.06)
      ctx.fillStyle = `rgba(${palette.hot[0]}, ${palette.hot[1]}, ${palette.hot[2]}, ${particle.brightness})`
    } else {
      particle.brightness *= 0.86
      const alpha = (idle ? 0.13 : 0.052 + particle.glyphWeight * 0.08) + audioLevel * 0.34 + speechEnergy * 0.08
      ctx.fillStyle = `rgba(${palette.base[0]}, ${palette.base[1]}, ${palette.base[2]}, ${alpha})`
    }
    const particleSize = speaking
      ? 1 + Math.min(2.35, audioLevel * 3.1 + midLevel * 0.85 + particle.brightness * 2.8)
      : 1
    ctx.fillRect(particle.x, particle.y, particleSize, particleSize)
  }

  if (speaking && audioLevel > 0.002) {
    ctx.globalCompositeOperation = 'lighter'
    const ringRadius = forceRadius - 7 + bassLevel * 20 + speechPulse * speechEnergy * 8
    const pulseAlpha = Math.min(0.62, 0.08 + audioLevel * 1.1 + speechEnergy * 0.18)
    ctx.beginPath()
    ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(${palette.base[0]}, ${palette.base[1]}, ${palette.base[2]}, ${pulseAlpha})`
    ctx.lineWidth = 0.8 + bassLevel * 2.4 + speechEnergy * 1.2
    ctx.stroke()

    ctx.beginPath()
    for (let step = 0; step <= 160; step += 1) {
      const theta = (step / 160) * Math.PI * 2
      const voiceWave = Math.sin(theta * 9 + time * 96) * trebleLevel * 16
        + Math.sin(theta * 4 - time * 46) * midLevel * 13
        + Math.sin(theta * 2 + time * 28) * audioLevel * 17
      const radius = 90 + bassLevel * 18 + speechEnergy * 10 + voiceWave
      const x = centerX + Math.cos(theta) * radius
      const y = centerY + Math.sin(theta) * radius
      if (step === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.strokeStyle = `rgba(${palette.hot[0]}, ${palette.hot[1]}, ${palette.hot[2]}, ${Math.min(0.32, 0.04 + audioLevel * 0.5)})`
    ctx.lineWidth = 0.55
    ctx.stroke()

    for (let lane = 0; lane < 3; lane += 1) {
      ctx.beginPath()
      const baseRadius = 56 + lane * 34 + bassLevel * (lane + 1) * 5
      for (let step = 0; step <= 144; step += 1) {
        const theta = (step / 144) * Math.PI * 2
        const wave = Math.sin(theta * (7 + lane * 3) - time * (58 + lane * 21)) * (midLevel * 9 + speechEnergy * 5)
          + Math.sin(theta * (17 + lane) + time * 120) * trebleLevel * 5
        const radius = baseRadius + wave
        const x = centerX + Math.cos(theta) * radius
        const y = centerY + Math.sin(theta) * radius
        if (step === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.strokeStyle = `rgba(${palette.hot[0]}, ${palette.hot[1]}, ${palette.hot[2]}, ${Math.min(0.22, 0.035 + speechEnergy * 0.18 - lane * 0.035)})`
      ctx.lineWidth = 0.45 + audioLevel * 0.55
      ctx.stroke()
    }
  }

  ctx.globalCompositeOperation = 'source-over'
}

function applyPhaseImpulse(particles: FlowParticle[], nextState: EmbryState, previousState: EmbryState): void {
  if (nextState === previousState) return
  const center = MICRO_CANVAS_SIZE / 2
  for (const particle of particles) {
    const fromTargetX = particle.x - particle.targetX
    const fromTargetY = particle.y - particle.targetY
    const fromCenterX = particle.x - center
    const fromCenterY = particle.y - center
    const distance = Math.max(1, Math.hypot(fromCenterX, fromCenterY))

    if (nextState === 'idle') {
      particle.brightness = 0
      particle.vx += (fromTargetX * 0.016 + (Math.random() - 0.5) * 2.8) * (0.35 + particle.glyphWeight)
      particle.vy += (fromTargetY * 0.016 + (Math.random() - 0.5) * 2.8) * (0.35 + particle.glyphWeight)
      continue
    }

    if (nextState === 'listening') {
      particle.vx += (particle.targetX - particle.x) * 0.015 * particle.glyphWeight
      particle.vy += (particle.targetY - particle.y) * 0.015 * particle.glyphWeight
      particle.brightness *= 0.45
      continue
    }

    if (nextState === 'thinking' || nextState === 'synthesizing') {
      particle.vx += -fromCenterY / distance * 0.8
      particle.vy += fromCenterX / distance * 0.8
      particle.brightness *= 0.65
      continue
    }

    if (nextState === 'speaking') {
      particle.vx += fromCenterX / distance * 0.55
      particle.vy += fromCenterY / distance * 0.55
      particle.brightness *= 0.55
    }
  }
}

export function EmbryVoiceOrb({
  voiceStatus,
  isStreaming,
  tone,
  signal,
  speechAudioElement,
  speechSourceId,
  speechAudioUrl,
  speechStartedAtMs,
  speechEnvelope,
  size: sizeProp = 96,
  surface = 'rail',
  phaseSpeedMs,
}: {
  voiceStatus?: EmbryVoiceStatus
  isStreaming?: boolean
  audioLevel?: number
  tone?: string
  signal?: IdentitySignal
  speechAudioElement?: HTMLMediaElement | null
  speechSourceId?: string
  speechAudioUrl?: string
  speechStartedAtMs?: number
  speechEnvelope?: EmbryVoiceEnvelope
  size?: number
  surface?: 'rail' | 'header' | 'toolbar'
  fillCanvas?: boolean
  letterAsParticles?: boolean
  phaseSpeedMs?: number
}): JSX.Element {
  const railBoost = surface === 'rail'
  const normalizedPhaseSpeedMs = clampPhaseSpeedMs(phaseSpeedMs)
  const { ref: containerRef, size: observedSize } = useEmbryOrbContainerSize(sizeProp, { min: 96, max: 240 })
  const size = railBoost ? observedSize : sizeProp
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const particlesRef = useRef<FlowParticle[]>([])
  const idleFlocksRef = useRef<IdleFlock[]>([])
  const maskRef = useRef<Float32Array | null>(null)
  const frameRef = useRef(0)
  const timeRef = useRef(0)
  const stateRef = useRef<EngineState>({
    visualState: 'idle',
    reducedMotion: false,
    audio: SILENT_AUDIO,
    attentionBoost: 0,
    releaseBoost: 0,
    phaseSpeedMs: DEFAULT_PHASE_SPEED_MS,
  })
  const previousVisualStateRef = useRef<EmbryState>('idle')
  const attentionStartedAtRef = useRef(0)
  const releaseStartedAtRef = useRef(0)

  const visualState: EmbryState = voiceStatus === 'off'
    ? 'idle'
    : resolveEmbryVisualState({ voiceStatus, isStreaming, tone, signal })
  const reducedMotion = false
  const mediaAudio = useEmbryPlaybackAudioBands(visualState === 'speaking', speechAudioElement)
  const envelopeAudio = useEmbryEnvelopeAudioBands(visualState === 'speaking', speechEnvelope, speechStartedAtMs)
  const decodedAudio = useEmbryDecodedAudioBands(visualState === 'speaking', speechAudioUrl, speechStartedAtMs)
  const hasServerEnvelope = Boolean(speechEnvelope?.frames.length)
  const audio = hasServerEnvelope ? envelopeAudio : mediaAudio.level > 0.002 ? mediaAudio : decodedAudio
  const speechLevel = visualState === 'speaking' ? audio.level : 0
  const speechRingScale = 1 + speechLevel * 0.16 + audio.bass * 0.035
  const speechRingOpacity = Math.min(0.9, 0.12 + speechLevel * 1.8)

  useEffect(() => {
    if (previousVisualStateRef.current !== visualState) {
      applyPhaseImpulse(particlesRef.current, visualState, previousVisualStateRef.current)
      if (visualState === 'listening') attentionStartedAtRef.current = performance.now()
      if (visualState === 'idle' && previousVisualStateRef.current !== 'idle') releaseStartedAtRef.current = performance.now()
      previousVisualStateRef.current = visualState
    }
    const attentionElapsed = attentionStartedAtRef.current ? performance.now() - attentionStartedAtRef.current : Number.POSITIVE_INFINITY
    const releaseElapsed = releaseStartedAtRef.current ? performance.now() - releaseStartedAtRef.current : Number.POSITIVE_INFINITY
    const attentionBoost = visualState === 'listening' ? Math.max(0, 1 - attentionElapsed / normalizedPhaseSpeedMs) : 0
    const releaseBoost = visualState === 'idle' ? Math.max(0, 1 - releaseElapsed / normalizedPhaseSpeedMs) : 0
    stateRef.current = { visualState, reducedMotion, audio, attentionBoost, releaseBoost, phaseSpeedMs: normalizedPhaseSpeedMs }
  }, [audio, normalizedPhaseSpeedMs, reducedMotion, visualState])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { alpha: false })
    if (!ctx) return
    ctx.fillStyle = BACKGROUND
    ctx.fillRect(0, 0, MICRO_CANVAS_SIZE, MICRO_CANVAS_SIZE)

    maskRef.current = createMask()
    particlesRef.current = createParticles(maskRef.current)
    idleFlocksRef.current = Array.from({ length: IDLE_FLOCK_COUNT }, (_, index) => ({
      x: MICRO_CANVAS_SIZE / 2,
      y: MICRO_CANVAS_SIZE / 2,
      strength: 0,
      radius: 64,
      phase: index * 1.37 + Math.random() * Math.PI * 2,
    }))

    const render = () => {
      timeRef.current += 0.004
      const mask = maskRef.current ?? createMask()
      const current = stateRef.current
      if (current.visualState === 'listening' && attentionStartedAtRef.current) {
        const elapsed = performance.now() - attentionStartedAtRef.current
        stateRef.current = { ...current, attentionBoost: Math.max(0, 1 - elapsed / current.phaseSpeedMs) }
      }
      if (current.visualState === 'idle' && releaseStartedAtRef.current) {
        const elapsed = performance.now() - releaseStartedAtRef.current
        stateRef.current = { ...stateRef.current, releaseBoost: Math.max(0, 1 - elapsed / stateRef.current.phaseSpeedMs) }
      }
      drawFrame(ctx, particlesRef.current, mask, idleFlocksRef.current, stateRef.current, timeRef.current)
      frameRef.current = window.requestAnimationFrame(render)
    }

    render()
    return () => window.cancelAnimationFrame(frameRef.current)
  }, [])

  return (
    <div
      ref={railBoost ? containerRef : undefined}
      data-qid="embry-voice:presence-orb"
      data-embry-state={visualState}
      data-embry-tone={tone ?? ''}
      data-embry-signal={signal ?? ''}
      data-embry-audio-level={audio.level.toFixed(3)}
      data-embry-audio-bass={audio.bass.toFixed(3)}
      data-embry-audio-mid={audio.mid.toFixed(3)}
      data-embry-audio-treble={audio.treble.toFixed(3)}
      data-embry-phase-speed-ms={normalizedPhaseSpeedMs}
      data-embry-speech-source-id={speechSourceId ?? ''}
      data-embry-speech-bound={speechAudioElement || hasServerEnvelope ? 'true' : 'false'}
      data-embry-decoded-source={speechAudioUrl ?? ''}
      data-embry-envelope-frames={speechEnvelope?.frames.length ?? 0}
      data-embry-orb-authority={hasServerEnvelope ? 'server-envelope' : speechAudioElement ? 'browser-analysis' : speechAudioUrl ? 'decoded-wav' : 'none'}
      style={{
        position: 'relative',
        lineHeight: 0,
        width: railBoost ? '100%' : size,
        height: railBoost ? '100%' : size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          position: 'relative',
          width: size,
          height: size,
          borderRadius: '50%',
          overflow: 'hidden',
          border: '1px solid rgba(96, 165, 250, 0.22)',
          boxShadow: 'inset 0 0 48px rgba(96, 165, 250, 0.12)',
        }}
      >
        <div
          aria-hidden
          data-qid="embry-voice:audio-reactive-ring"
          style={{
            position: 'absolute',
            inset: Math.max(2, size * 0.035),
            zIndex: 2,
            borderRadius: '50%',
            border: `${Math.max(1, size * 0.012 + audio.bass * size * 0.018)}px solid rgba(128, 255, 210, ${speechRingOpacity})`,
            boxShadow: `0 0 ${Math.round(size * (0.08 + speechLevel * 0.16))}px rgba(80, 255, 180, ${Math.min(0.7, speechRingOpacity)}), inset 0 0 ${Math.round(size * 0.08)}px rgba(80, 255, 180, ${Math.min(0.34, speechLevel)})`,
            opacity: visualState === 'speaking' ? 1 : 0,
            transform: `scale(${speechRingScale})`,
            transition: 'opacity 120ms ease-out',
            pointerEvents: 'none',
          }}
        />
        <canvas
          ref={canvasRef}
          width={MICRO_CANVAS_SIZE}
          height={MICRO_CANVAS_SIZE}
          className="embry-voice-orb"
          aria-label={`Embry ${visualState}`}
          role="img"
          style={{ width: '100%', height: '100%', filter: 'blur(0.3px) contrast(1.3) brightness(2.15)' }}
        />
      </div>
    </div>
  )
}

export default EmbryVoiceOrb
