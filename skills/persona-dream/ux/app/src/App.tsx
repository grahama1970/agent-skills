import { useEffect, useState } from 'react'
import { DreamWorkspace } from '../../../ui/src'
import { api, type Journal, type RunSummary } from './api'
import ChatWell from './components/ChatWell'
import EmbryDrawer from './components/EmbryDrawer'
import JournalPage from './components/JournalPage'

/** The journal is the page; the conversation is a pane on it.
 *
 * That layout encodes the architecture rather than just looking tidy. The
 * generate-dream pipeline terminates at the journal, and the chat is a
 * downstream consumer of that finished artifact -- so the journal owns the
 * page, and the conversation docks beside it and can be closed without
 * anything being lost.
 *
 * The drawer is gated on a journal existing. With no entry there is no tension,
 * no session mood, and nothing for her to be answering about, so offering a
 * composer would invite a conversation the backend would refuse anyway.
 */

/** #dream mounts the pipeline workspace (phases 01-10) from ui/src; every
 * other hash keeps the journal + chat surface. This is the project-owned
 * mount the ux-lab registry's legacy-dream-route entry asks for. */
function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

export default function App() {
  const hash = useHashRoute()
  if (hash === '#dream') return <DreamWorkspace />
  return <JournalApp />
}

function JournalApp() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [journal, setJournal] = useState<Journal | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.runs()
      .then(({ runs }) => { setRuns(runs); setRunId((id) => id ?? runs[0]?.run_id ?? null) })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!runId) return
    setJournal(null)
    api.journal(runId).then(setJournal).catch((e) => setError(String(e)))
  }, [runId])

  return (
    <div className="pd-app" data-qid="dream:app">
      <nav className="pd-runs" data-qid="dream:runs">
        <label htmlFor="pd-run-select">Run</label>
        <select
          id="pd-run-select"
          value={runId ?? ''}
          data-qid="dream:runs:select"
          data-qs-action="DREAM_SELECT_RUN"
          title="Choose which dream run to read"
          onChange={(e) => { setRunId(e.target.value); setChatOpen(false) }}
        >
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.run_id}{run.turns ? ` · ${run.turns} turns` : ''}
            </option>
          ))}
        </select>
      </nav>

      {/* EmbryDrawer sizes itself with `flex: 0 0 <width>` and no position, so
          it must be a sibling of main inside a flex ROW. Wrapping them is what
          makes it dock beside the journal instead of falling below it. */}
      <div className="pd-body">
        <main className="pd-main">
          {error && <p className="pd-error" data-qid="dream:error">{error}</p>}
          {!error && !journal && <p className="pd-loading">Loading the entry…</p>}
          {journal && (
            <JournalPage
              journal={journal}
              chatOpen={chatOpen}
              onToggleChat={() => setChatOpen((open) => !open)}
            />
          )}
        </main>

        <EmbryDrawer
          isOpen={chatOpen && !!journal?.journal_present}
          onClose={() => setChatOpen(false)}
          dock="right"
          title="Talk to Embry"
          qid="dream:chat:drawer"
        >
          {journal && runId && <ChatWell runId={runId} journal={journal} />}
        </EmbryDrawer>
      </div>
    </div>
  )
}
