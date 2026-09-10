import {
  Mic,
  MicOff,
} from 'lucide-react'

import {
  useRef,
  useState,
} from 'react'

import {
  useAudioVolume,
} from '../useAudioVolume'

import {
  useRegisterAction,
} from '../useRegisterAction'

/**
 * Header mic badge: mic icon + volume-driven pulse ring.
 *
 * RMS volume drives a CSS variable on this element directly
 * (no React re-render per frame); only STANDBY/LISTENING
 * transitions re-render, debounced by hysteresis.
 *
 * Off by default: click to start listening so the page never
 * auto-prompts for microphone permission on load.
 */
export function CockpitAudioIndicator() {
  const [enabled, setEnabled] = useState(false)
  const badgeRef = useRef<HTMLButtonElement>(null)

  const { audioState, denied } = useAudioVolume(
    enabled,
    (rms) => {
      badgeRef.current?.style.setProperty(
        '--mic-volume',
        rms.toFixed(3),
      )
    },
  )

  useRegisterAction({
    element_id: 'cockpit:audio:listen-toggle',
    app: 'explain-project',
    action: 'AUDIO_LISTEN_TOGGLE',
    label: 'Toggle live mic listening indicator',
    description: (
      'Start or stop the browser-local microphone RMS '
      + 'indicator. No transcript or speaker identity claimed.'
    ),
  })

  const listening = enabled && !denied
    && audioState === 'LISTENING'

  const stateWord = !enabled
    ? 'MIC OFF'
    : denied
      ? 'MIC BLOCKED'
      : audioState

  const Icon = enabled && !denied ? Mic : MicOff

  return (
    <button
      type="button"
      ref={badgeRef}
      data-qid="cockpit:audio:listen-toggle"
      data-qs-action="AUDIO_LISTEN_TOGGLE"
      data-audio-state={stateWord.toLowerCase().replace(' ', '-')}
      title={`${stateWord}${enabled ? ' — click to stop' : ' — click to listen'}`}
      aria-label={`Microphone indicator: ${stateWord}`}
      aria-pressed={enabled}
      className={[
        'cockpit-audio__badge',
        'inline-flex h-7 items-center gap-2 rounded-full border',
        'px-2.5 font-mono text-[10px] font-semibold uppercase',
        listening
          ? 'cockpit-audio__badge--listening'
          : 'cockpit-audio__badge--standby',
      ].join(' ')}
      onClick={() => {
        setEnabled((on) => !on)
      }}
    >
      <span className="cockpit-audio__icon-wrap" aria-hidden="true">
        <span className="cockpit-audio__ring" />
        <Icon className="cockpit-audio__icon size-3.5" />
      </span>
    </button>
  )
}
