import {
  useEffect,
  useRef,
  useState,
} from 'react'

/**
 * Live microphone volume via Web Audio AnalyserNode.
 *
 * Browser-local only: this drives the header listening indicator.
 * It is NOT a RealtimeSTT transcript or speaker-identity claim.
 */
export function useAudioVolume(enabled: boolean) {
  const [volume, setVolume] = useState(0)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [denied, setDenied] = useState(false)
  const frame = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) {
      setVolume(0)
      setIsSpeaking(false)
      setDenied(false)
      return
    }

    let context: AudioContext | null = null
    let analyser: AnalyserNode | null = null
    let stream: MediaStream | null = null
    let cancelled = false

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
        analyser.fftSize = 64
        context.createMediaStreamSource(stream)
          .connect(analyser)

        const data = new Uint8Array(
          analyser.frequencyBinCount,
        )

        const tick = (): void => {
          if (analyser === null) return

          analyser.getByteFrequencyData(data)

          let sum = 0
          for (let i = 0; i < data.length; i += 1) {
            sum += data[i]
          }

          // Quantize to 2 decimals so React re-renders
          // only on meaningful volume changes, not 60fps.
          const normalized = Math.min(
            1,
            Math.round((sum / data.length / 120) * 100) / 100,
          )

          setVolume(normalized)
          setIsSpeaking(normalized > 0.05)
          frame.current = requestAnimationFrame(tick)
        }

        tick()
      } catch {
        // Permission denied or no mic: stay in standby.
        setDenied(true)
      }
    }

    void init()

    return () => {
      cancelled = true
      if (frame.current !== null) {
        cancelAnimationFrame(frame.current)
      }
      if (stream !== null) {
        stream.getTracks().forEach((track) => track.stop())
      }
      if (context !== null) {
        void context.close()
      }
    }
  }, [enabled])

  return { volume, isSpeaking, denied }
}
