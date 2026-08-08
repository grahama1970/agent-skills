import { MessageSquare, Play } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, type Journal } from '../api'
import { useRegisterAction } from '../hooks/useRegisterAction'

/** Embry's journal entry for one dream.
 *
 * The boundary block is not decoration and must not be styled away: this is an
 * interpretation she made of her own day, and a page that reads like a record
 * of events would be making a claim the artifact does not support. Same for the
 * tone chips -- a tone is what was REQUESTED of the renderer, which is a weaker
 * statement than what a listener would perceive.
 */

interface Props {
  journal: Journal
  chatOpen: boolean
  onToggleChat: () => void
}

const APP = 'persona-dream-ux'

export default function JournalPage({ journal, chatOpen, onToggleChat }: Props) {
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useRegisterAction('dream:journal:toggle-chat', {
    app: APP, action: 'DREAM_TOGGLE_CHAT', label: 'Talk to Embry',
    description: 'Open or close the conversation pane beside the journal entry',
  })
  useRegisterAction('dream:journal:play', {
    app: APP, action: 'DREAM_PLAY_JOURNAL', label: 'Play spoken entry',
    description: 'Play the journal entry as Embry spoke it',
  })

  const toggleAudio = () => {
    const el = audioRef.current
    if (!el || !journal.audio) return
    if (playing) { el.pause(); setPlaying(false); return }
    el.src = api.audioUrl(journal.run_id, journal.audio)
    el.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
  }

  const mood = journal.session_mood?.mood_label

  return (
    <article className="pd-journal" data-qid="dream:journal:page">
      <header className="pd-journal-head">
        <div>
          <p className="pd-journal-persona">{journal.persona || 'Embry'}</p>
          <h1 data-qid="dream:journal:title">{journal.title || journal.run_id}</h1>
          {mood && (
            <p className="pd-mood" title={journal.session_mood.mood_description}>
              woke up feeling <em>{mood}</em>
            </p>
          )}
        </div>
        <div className="pd-journal-actions">
          {journal.audio && (
            <button
              type="button"
              data-qid="dream:journal:play"
              data-qs-action="DREAM_PLAY_JOURNAL"
              title="Play the entry as she spoke it"
              onClick={toggleAudio}
            >
              <Play size={15} /> {playing ? 'Pause' : 'Spoken entry'}
            </button>
          )}
          <button
            type="button"
            className={chatOpen ? 'pd-primary pd-on' : 'pd-primary'}
            data-qid="dream:journal:toggle-chat"
            data-qs-action="DREAM_TOGGLE_CHAT"
            title="Talk to her about this dream"
            disabled={!journal.journal_present}
            onClick={onToggleChat}
          >
            <MessageSquare size={15} /> Talk to her
          </button>
        </div>
      </header>

      {!journal.journal_present && (
        <p className="pd-chat-blocked" data-qid="dream:journal:absent">
          This run has no journal entry, so there is nothing to talk about yet.
        </p>
      )}

      {journal.preamble.map((line, i) => (
        <p className="pd-preamble" key={i}>{line}</p>
      ))}

      {/* Each paragraph carries its own requested delivery tone. The chip says
          "requested" because that is all the artifact supports -- what a
          listener perceives is a different claim, and an untested one. */}
      <div className="pd-prose" data-qid="dream:journal:prose">
        {journal.paragraphs.map((para, i) => (
          <p key={i} data-qid={`dream:journal:para:${i}`}>
            {para.tone && (
              <span
                className="pd-para-tone"
                title={`Delivery tone ${para.status ?? 'requested'} of the renderer${
                  para.intensity ? ` at intensity ${para.intensity}` : ''
                }. Not a claim about what a listener hears.`}
              >
                {para.tone}
              </span>
            )}
            {para.text}
          </p>
        ))}
      </div>

      {(journal.unresolved_tension || journal.expanded_understanding) && (
        <section className="pd-tension" data-qid="dream:journal:tension">
          {journal.unresolved_tension && (
            <p><span>What it left open</span>{journal.unresolved_tension}</p>
          )}
          {journal.expanded_understanding && (
            <p><span>What it expanded</span>{journal.expanded_understanding}</p>
          )}
        </section>
      )}

      {journal.sources.length > 0 && (
        <section className="pd-sources" data-qid="dream:journal:sources">
          <h2>What she was working from</h2>
          {journal.sources.map((source) => (
            <p key={source.source_id} data-qid={`dream:journal:source:${source.n}`}>
              <sup>{source.n}</sup>
              <code title={`scope: ${source.scope}`}>{source.source_id}</code>
              {source.synthetic && <span className="pd-synthetic" title="This residue was itself synthetic">synthetic</span>}
              <span className="pd-excerpt">{source.excerpt}</span>
            </p>
          ))}
        </section>
      )}

      {Object.keys(journal.footnotes).length > 0 && (
        <section className="pd-footnotes" data-qid="dream:journal:footnotes">
          {Object.entries(journal.footnotes).map(([key, value]) => (
            <p key={key}><sup>{key}</sup> {value}</p>
          ))}
        </section>
      )}

      {/* Structural, data-bound: an interpretation must never read as a record. */}
      <footer className="pd-boundary" data-qid="dream:journal:boundary">
        <p>{journal.boundary.note}</p>
        <p className="pd-boundary-flags">
          {journal.boundary.canon_status}
          {journal.boundary.never_promote_to_event_fact && ' · never promoted to event fact'}
          {journal.boundary.asserts_only_own_inner_state && ' · asserts only her own inner state'}
        </p>
      </footer>

      <audio ref={audioRef} onEnded={() => setPlaying(false)} hidden />
    </article>
  )
}
