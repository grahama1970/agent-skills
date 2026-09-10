import {
  useEffect,
  useRef,
  useState,
} from 'react'

export type AudioMonitorState =
  | 'STANDBY'
  | 'LISTENING'

/**
 * Live microphone RMS monitor with hysteresis.
 *
 * - RMS energy (0..1) per animation frame, delivered via
 *   onVolume so callers can drive a CSS variable without
 *   React re-renders.
 * - State transitions use hysteresis: speech threshold 0.02
 *   RMS, 700ms hold before dropping back to STANDBY so
 *   pauses in speech do not flicker the label.
 *
 * Browser-local only: no transcript or speaker identity.
 */
export function useAudioVolume(
  enabled: boolean,
  onVolume: (rms: number) => void,
): {
  audioState: AudioMonitorState
  denied: boolean
} {
  const [audioState, setAudioState]
    = useState<AudioMonitorState>('STANDBY')
  const [denied, setDenied] = useState(false)

  const volumeRef = useRef(onVolume)
  volumeRef.current = onVolume

  useEffect(() => {
    if (!enabled) {
      setAudioState('STANDBY')
      setDenied(false)
      volumeRef.current(0)
      return
    }

    const VOLUME_THRESHOLD = 0.02
    const HOLD_MS = 700

    let context: AudioContext | null = null
    let analyser: AnalyserNode | null = null
    let stream: MediaStream | null = null
    let frame: number | null = null
    let silenceTimer: ReturnType<
      typeof setTimeout
    > | null = null
    let cancelled = false
    let state: AudioMonitorState = 'STANDBY'

    async function init(): Promise<void> {
      try {
        stream = await navigator.mediaDevices.getUserMedia(
          { audio: true },
        )
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        context = new AudioContext()
        analyser = context.createAnalyser()
        analyser.fftSize = 256
        context.createMediaStreamSource(stream)
          .connect(analyser)

        const data = new Uint8Array(
          analyser.frequencyBinCount,
        )

        const setState = (
          next: AudioMonitorState,
        ): void => {
          state = next
          setAudioState(next)
        }

        const loop = (): void => {
          if (analyser === null) return

          analyser.getByteFrequencyData(data)

          let sum = 0
          for (let i = 0; i < data.length; i += 1) {
            const value = data[i] / 255
            sum += value * value
          }
          const rms = Math.sqrt(sum / data.length)

          volumeRef.current(rms)

          if (rms >= VOLUME_THRESHOLD) {
            if (silenceTimer !== null) {
              clearTimeout(silenceTimer)
              silenceTimer = null
            }
            if (state !== 'LISTENING') {
              setState('LISTENING')
            }
          } else if (
            state === 'LISTENING'
            && silenceTimer === null
          ) {
            silenceTimer = setTimeout(() => {
              silenceTimer = null
              setState('STANDBY')
            }, HOLD_MS)
          }

          frame = requestAnimationFrame(loop)
        }

        loop()
      } catch {
        // Permission denied or no mic: stay in standby.
        setDenied(true)
        volumeRef.current(0)
      }
    }

    void init()

    return () => {
      cancelled = true
      if (frame !== null) cancelAnimationFrame(frame)
      if (silenceTimer !== null) clearTimeout(silenceTimer)
      if (stream !== null) {
        stream.getTracks().forEach((track) => track.stop())
      }
      if (context !== null) {
        void context.close()
      }
    }
  }, [enabled])

  return { audioState, denied }
}
