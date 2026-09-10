import {
  useState,
} from 'react'

import {
  useAudioVolume,
} from '../useAudioVolume'

import {
  useRegisterAction,
} from '../useRegisterAction'

/**
 * Google-Meet-style 3-dot mic indicator for the header.
 *
 * Off by default: click (or grant mic) to start listening so the
 * page never auto-prompts for microphone permission on load.
 */
export function CockpitAudioIndicator() {
  const [enabled, setEnabled] = useState(false)
  const { volume, isSpeaking, denied } = useAudioVolume(enabled)

  useRegisterAction({
    element_id: 'cockpit:audio:listen-toggle',
    app: 'explain-project',
    action: 'AUDIO_LISTEN_TOGGLE',
    label: 'Toggle live mic listening indicator',
    description: (
      'Start or stop the browser-local microphone volume '
      + 'indicator. No transcript or speaker identity claimed.'
    ),
  })

  const scale = isSpeaking
    ? 1 + volume * 0.45
    : 1

  const label = !enabled
    ? 'MIC OFF'
    : denied
      ? 'MIC BLOCKED'
      : isSpeaking
        ? 'LISTENING'
        : 'STANDBY'

  return (
    <button
      type="button"
      data-qid="cockpit:audio:listen-toggle"
      data-qs-action="AUDIO_LISTEN_TOGGLE"
      data-audio-state={label.toLowerCase().replace(' ', '-')}
      title={enabled
        ? 'Mic indicator active — click to stop'
        : 'Mic indicator off — click to listen'}
      aria-pressed={enabled}
      className={[
        'inline-flex h-7 items-center gap-2 rounded-full border',
        'px-2.5 font-mono text-[10px] font-semibold tracking-wider uppercase',
        'transition-colors',
        enabled && !denied
          ? 'border-cyan-500/50 bg-cyan-950/40 text-cyan-300'
          : 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500',
      ].join(' ')}
      onClick={() => {
        setEnabled((on) => !on)
      }}
    >
      <span
        className="cockpit-audio__wrapper"
        data-speaking={isSpeaking ? 'true' : 'false'}
        style={{ transform: `scale(${scale})` }}
        aria-hidden="true"
      >
        {isSpeaking ? (
          <>
            <span className="cockpit-audio__ring cockpit-audio__ring--1" />
            <span className="cockpit-audio__ring cockpit-audio__ring--2" />
          </>
        ) : null}

        <span className="cockpit-audio__core">
          <span className="cockpit-audio__dot" />
          <span className="cockpit-audio__dot" />
          <span className="cockpit-audio__dot" />
        </span>
      </span>

      <span>{label}</span>
    </button>
  )
}
