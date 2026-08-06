import { useEffect, useState } from 'react'

// Phase 1 (Gemini spec) adapted: dual-pane source editor over the REAL
// document model — the deck manifest YAML — not a lossy Markdown projection.
// Canvas edits refresh this pane (via the version key); saving the pane runs
// the full fail-closed pipeline server-side (/api/source → source-edit CLI).
// Toggle with Cmd/Ctrl+\ (handled in App).

export function SourcePane({ version, onSaved, onClose, width }: { version: number; onSaved: () => void; onClose?: () => void; width?: number }) {
  const [yamlText, setYamlText] = useState('')
  const [loadedYaml, setLoadedYaml] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`/api/source?v=${version}`, { cache: 'no-store' })
      .then((res) => res.json() as Promise<{ yaml?: string; error?: string }>)
      .then((data) => {
        if (data.yaml !== undefined) {
          setYamlText(data.yaml)
          setLoadedYaml(data.yaml)
          setError(null)
        } else {
          setError(data.error ?? 'failed to load source')
        }
      })
      .catch((err: Error) => setError(err.message))
  }, [version])

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch('/api/source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: yamlText }),
      })
      const data = (await response.json()) as { error?: string }
      if (!response.ok) throw new Error(data.error ?? `save failed (${response.status})`)
      setLoadedYaml(yamlText)
      onSaved()
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setBusy(false)
    }
  }

  const dirty = yamlText !== loadedYaml

  return (
    <section aria-label="Deck source" style={width ? { width, minWidth: width } : undefined} className="flex w-[34rem] min-w-[24rem] flex-col bg-slate-950">
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-3 py-1.5 font-mono text-[11px] text-slate-400">
        <span>DECK SOURCE · deck.public.yaml</span>
        <span className="flex items-center gap-2">
          <span className="text-slate-600">Ctrl+\ toggles</span>
          {onClose ? (
            <button
              type="button"
              aria-label="Close source pane"
              data-qid="deck:source:close"
              data-qs-action="DECK_SOURCE_CLOSE"
              title="Close the source pane"
              onClick={onClose}
              className="cursor-pointer rounded border border-transparent px-1 text-slate-400 hover:border-slate-600 hover:text-cyan-300"
            >
              ×
            </button>
          ) : null}
        </span>
      </header>
      <textarea
        data-qid="deck:source:editor"
        title="Deck manifest YAML source"
        spellCheck={false}
        value={yamlText}
        onChange={(event) => setYamlText(event.target.value)}
        className="min-h-0 w-full flex-1 resize-none bg-slate-950 p-3 font-mono text-xs leading-relaxed text-slate-200 outline-none"
      />
      {error ? (
        <p role="alert" className="m-0 border-t border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          Rejected by validation: {error}
        </p>
      ) : null}
      <footer className="flex items-center gap-2 border-t border-slate-800 px-3 py-2">
        <button
          type="button"
          data-qid="deck:source:save"
          data-qs-action="DECK_SOURCE_SAVE"
          title="Validate and apply the edited deck source"
          disabled={busy || !dirty}
          onClick={() => void save()}
          className="cursor-pointer rounded-lg border border-cyan-600 bg-cyan-600/20 px-3 py-1.5 text-xs text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? 'Validating…' : 'Apply source'}
        </button>
        <button
          type="button"
          data-qid="deck:source:revert"
          data-qs-action="DECK_SOURCE_REVERT"
          title="Discard source edits"
          disabled={busy || !dirty}
          onClick={() => setYamlText(loadedYaml)}
          className="cursor-pointer rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Revert
        </button>
        {dirty ? <span className="text-[11px] text-amber-400">unsaved changes</span> : null}
      </footer>
    </section>
  )
}
