import { Mic, Send, Square } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Conversation, type Journal, type ReplyResult, type VoiceHealth } from '../api'
import { EmbryVoiceOrb, type EmbryVoiceStatus } from '../embry-voice/EmbryVoiceOrb'
import { useRegisterAction } from '../hooks/useRegisterAction'

/** Talk to Embry about the dream she just had.
 *
 * This pane is deliberately NOT a pipeline step. The generate-dream pipeline
 * ends when the journal exists; this reads that finished journal and appends to
 * conversation.jsonl, and touches nothing else. That is why it is a pane on the
 * journal rather than a page after it -- her reply is *about* the entry, so the
 * entry has to stay on screen while you read the reply.
 *
 * Every refusal is rendered. A reply that could not be spoken is never recorded
 * as a turn, so if the UI showed only successes it would silently drop the most
 * informative event: the one where the renderer declined and we learned why.
 */

interface Props {
  runId: string
  journal: Journal
}

const APP = 'persona-dream-ux'

export default function ChatWell({ runId, journal }: Props) {
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState<'idle' | 'sending' | 'thinking'>('idle')
  const [refusal, setRefusal] = useState<ReplyResult | null>(null)
  const [voice, setVoice] = useState<VoiceHealth | null>(null)
  const [recording, setRecording] = useState(false)
  const [nowPlaying, setNowPlaying] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useRegisterAction('dream:chat:send', {
    app: APP, action: 'DREAM_CHAT_SEND', label: 'Send',
    description: 'Send a message to Embry about her dream and ask her to reply',
  })
  useRegisterAction('dream:chat:mic', {
    app: APP, action: 'DREAM_CHAT_DICTATE', label: 'Dictate',
    description: 'Record an utterance and transcribe it locally into the composer',
  })

  const load = useCallback(() => {
    api.conversation(runId).then(setConversation).catch(() => setConversation(null))
  }, [runId])

  useEffect(() => { load() }, [load])
  useEffect(() => { api.voiceHealth().then(setVoice).catch(() => setVoice(null)) }, [])
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [conversation?.turns.length, busy])

  /** Say something, then ask her to answer it. The two are separate server
   *  calls because your turn is recorded even if hers cannot be. */
  const send = useCallback(async () => {
    const text = draft.trim()
    if (!text || busy !== 'idle') return
    setRefusal(null)
    setBusy('sending')
    await api.say(runId, text)
    setDraft('')
    load()
    setBusy('thinking')
    const { ok, data } = await api.reply(runId, text)
    const result = (data as { reply?: ReplyResult }).reply ?? (data as ReplyResult)
    if (!ok || result.status !== 'PASS_REPLY_SPOKEN') setRefusal(result)
    setBusy('idle')
    load()
  }, [draft, busy, runId, load])

  const dictate = useCallback(async () => {
    if (recording) {
      recorderRef.current?.stop()
      return
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const chunks: Blob[] = []
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => chunks.push(e.data)
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      setRecording(false)
      const out = await api.transcribe(new Blob(chunks, { type: 'audio/webm' }))
      if (out.status === 'PASS_TRANSCRIBED') setDraft((d) => (d ? `${d} ${out.text}` : out.text))
    }
    recorderRef.current = recorder
    recorder.start()
    setRecording(true)
  }, [recording])

  const play = useCallback((name: string) => {
    if (!audioRef.current) return
    audioRef.current.src = api.audioUrl(runId, name)
    audioRef.current.play().then(() => setNowPlaying(name)).catch(() => setNowPlaying(null))
  }, [runId])

  const status: EmbryVoiceStatus =
    busy === 'thinking' ? 'processing'
    : recording ? 'listening'
    : nowPlaying ? 'speaking'
    : 'idle'

  const canSpeak = voice?.speak.available !== false
  const canListen = voice?.listen.available === true
  const turns = conversation?.turns ?? []

  return (
    <div className="pd-chat" data-qid="dream:chat:well">
      <header className="pd-chat-head">
        <EmbryVoiceOrb
          voiceStatus={status}
          tone={turns.filter((t) => t.role === 'embry').slice(-1)[0]?.requested_delivery_tone}
          speechAudioElement={audioRef.current}
          speechSourceId={nowPlaying ?? undefined}
          size={72}
          surface="rail"
        />
        <div className="pd-chat-head-text">
          <h2>Talk to {journal.persona || 'Embry'}</h2>
          {/* She is answering about THIS entry, so the tension stays in view. */}
          <p title={journal.unresolved_tension}>{journal.unresolved_tension || journal.title}</p>
        </div>
      </header>

      {!canSpeak && (
        <p className="pd-chat-blocked" data-qid="dream:chat:speak-unavailable">
          Chatterbox is unreachable, so she cannot answer. Her turns are never recorded
          as text she did not say.
        </p>
      )}

      <div className="pd-chat-scroll" ref={scrollRef} data-qid="dream:chat:transcript">
        {turns.length === 0 && (
          <p className="pd-chat-empty">
            Nothing said yet. Ask her how the dream felt, or what it left open.
          </p>
        )}
        {turns.map((turn, i) => (
          <article key={i} className={`pd-turn pd-turn-${turn.role}`} data-qid={`dream:chat:turn:${i}`}>
            <div className="pd-turn-meta">
              <span className="pd-turn-role">{turn.role}</span>
              {turn.requested_delivery_tone && (
                <span
                  className="pd-tone-chip"
                  data-qid={`dream:chat:tone:${i}`}
                  title={turn.tone_boundary ?? 'Requested of the renderer, not achieved'}
                >
                  {turn.requested_delivery_tone}
                </span>
              )}
              {turn.audio && (
                <button
                  type="button"
                  className="pd-turn-play"
                  data-qid={`dream:chat:play:${i}`}
                  data-qs-action="DREAM_CHAT_PLAY_TURN"
                  title="Play this turn as it was spoken"
                  onClick={() => play(turn.audio as string)}
                >
                  {nowPlaying === turn.audio ? '❚❚' : '▶'}
                </button>
              )}
            </div>
            <p>{turn.text}</p>
          </article>
        ))}
        {busy === 'thinking' && (
          <p className="pd-chat-thinking" data-qid="dream:chat:thinking">
            Drafting through Tau, then rendering her voice…
          </p>
        )}
      </div>

      {refusal && (
        <div className="pd-chat-refusal" data-qid="dream:chat:refusal">
          <strong>{refusal.status}</strong>
          <p>
            Her turn was not recorded. A reply she never said is not a turn.
          </p>
          {refusal.failed_gates?.length ? <code>{refusal.failed_gates.join(' · ')}</code> : null}
        </div>
      )}

      <footer className="pd-chat-composer">
        <button
          type="button"
          className={recording ? 'pd-mic pd-mic-on' : 'pd-mic'}
          data-qid="dream:chat:mic"
          data-qs-action="DREAM_CHAT_DICTATE"
          title={canListen ? 'Dictate a message (transcribed locally)' : voice?.listen.reason ?? 'Dictation unavailable'}
          disabled={!canListen}
          onClick={dictate}
        >
          {recording ? <Square size={16} /> : <Mic size={16} />}
        </button>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
          placeholder="Ask her about the dream, or about the day it came from…"
          data-qid="dream:chat:composer"
          title="Your message to Embry"
          rows={2}
        />
        <button
          type="button"
          className="pd-send"
          data-qid="dream:chat:send"
          data-qs-action="DREAM_CHAT_SEND"
          title="Send and ask her to reply"
          disabled={!draft.trim() || busy !== 'idle' || !canSpeak}
          onClick={() => void send()}
        >
          <Send size={16} />
        </button>
      </footer>

      <p className="pd-chat-boundary">{conversation?.tone_boundary}</p>
      <audio ref={audioRef} onEnded={() => setNowPlaying(null)} hidden />
    </div>
  )
}
