import { useCallback, useState } from 'react'
import { Check, X } from 'lucide-react'
import { ChatWell } from '@ux-lab/ui/ChatWell'
import type { ChatMessage } from '@ux-lab/ui/ChatWell'
import { revisionStore } from '../hooks'
import type { UiDeckBundle } from '../types'
// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'

// Claim-review chat over the shared ux-lab ChatWell. The interpreter is
// deterministic: it answers from the emitted (seam-validated) bundle and
// emits exact CLI commands for mutations — it never edits deck content
// directly, so the fail-closed claim boundary stays with the compiler.
// Deck mutations parse into typed COMMAND OBJECTS (roundtable decision):
// chat proposes, the human confirms via an explicit Apply card, and the
// compiler validates — nothing is ever applied from text alone.
// Set VITE_DECK_AGENT_URL to forward unrecognized turns to a live agent.

export type SimulatePreview = { would_pass: boolean; gate_codes: string[]; error: string | null; diff: string }

export type DeckCommand = (
  | { kind: 'slide-edit'; slide_id: string; field: string; value: string; summary: string }
  | { kind: 'deck-op'; op: string; slide_id: string; target_order?: number; summary: string }
) & { base_revision?: number; preview?: SimulatePreview | null }

// Simulate-first proposals (#1228): the Apply card shows the compiler's
// verdict BEFORE anything is committed — propose -> preview -> confirm.
async function fetchSimulate(command: DeckCommand): Promise<SimulatePreview | null> {
  try {
    const response = await fetch('/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        command.kind === 'slide-edit'
          ? { slide_id: command.slide_id, field: command.field, value: command.value }
          : { slide_id: command.slide_id, op: command.op, target_order: command.target_order },
      ),
    })
    return (await response.json()) as SimulatePreview
  } catch {
    return null
  }
}

function slideByNumber(deck: UiDeckBundle, n: number) {
  return deck.slides.find((s) => s.order === n) ?? null
}

// Deterministic command grammar (known, bounded): each pattern names an
// existing compiler operation. Anything outside it falls through to Q&A.
export function parseCommand(deck: UiDeckBundle, text: string): DeckCommand | null {
  const input = text.trim()
  const lower = input.toLowerCase()
  let m = lower.match(/^(hide|unhide|show) slide (\d+)$/)
  if (m && m[1] !== 'show') {
    const slide = slideByNumber(deck, Number(m[2]))
    if (!slide) return null
    const hidden = m[1] === 'hide'
    return { kind: 'slide-edit', slide_id: slide.id, field: 'hidden', value: String(hidden), summary: `${hidden ? 'Hide' : 'Unhide'} slide ${m[2]} (${slide.title})` }
  }
  m = lower.match(/^(delete|duplicate) slide (\d+)$/)
  if (m) {
    const slide = slideByNumber(deck, Number(m[2]))
    if (!slide) return null
    const op = m[1] === 'delete' ? 'delete' : 'duplicate'
    return { kind: 'deck-op', op, slide_id: slide.id, summary: `${m[1][0].toUpperCase() + m[1].slice(1)} slide ${m[2]} (${slide.title})` }
  }
  m = lower.match(/^move slide (\d+) to (\d+)$/)
  if (m) {
    const slide = slideByNumber(deck, Number(m[1]))
    if (!slide) return null
    return { kind: 'deck-op', op: 'move_to', slide_id: slide.id, target_order: Number(m[2]), summary: `Move slide ${m[1]} (${slide.title}) to position ${m[2]}` }
  }
  m = input.match(/^set (title|message|notes|footer) of slide (\d+) to (.+)$/i)
  if (m) {
    const slide = slideByNumber(deck, Number(m[2]))
    if (!slide) return null
    return { kind: 'slide-edit', slide_id: slide.id, field: m[1].toLowerCase(), value: m[3].trim(), summary: `Set ${m[1].toLowerCase()} of slide ${m[2]} to “${m[3].trim()}”` }
  }
  return null
}

async function applyCommand(command: DeckCommand): Promise<string | null> {
  const isEdit = command.kind === 'slide-edit'
  const response = await fetch(isEdit ? '/api/slide-edit' : '/api/deck-op', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(
      isEdit
        ? { slide_id: command.slide_id, field: command.field, value: command.value, base_revision: command.base_revision ?? revisionStore.current }
        : { op: command.op, slide_id: command.slide_id, target_order: command.target_order, base_revision: command.base_revision ?? revisionStore.current },
    ),
  })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `command failed (${response.status})`
}

let counter = 0
function msg(
  role: 'user' | 'assistant',
  content: string,
  extra?: Partial<Pick<ChatMessage, 'title' | 'footer' | 'skillUsed' | 'evidenceCase' | 'thinkingTrace'>>,
): ChatMessage {
  counter += 1
  return { id: `deck-chat-${counter}`, role, content, createdAt: new Date().toISOString(), ...extra }
}

function findClaim(deck: UiDeckBundle, id: string) {
  for (const slide of deck.slides) {
    const claim = slide.claims.find((c) => c.id === id)
    if (claim) return { claim, slide }
  }
  return null
}

function interpret(deck: UiDeckBundle, text: string): string | { content: string; extra: Partial<ChatMessage> } {
  const input = text.trim()
  const lower = input.toLowerCase()
  if (lower === 'gaps' || lower.includes('validation gap')) {
    return deck.validation_gaps.length
      ? `Open validation gaps (${deck.validation_gaps.length}):\n${deck.validation_gaps.map((g) => `- ${g}`).join('\n')}`
      : 'No open validation gaps. Readiness: ' + deck.validation_readiness
  }
  if (lower === 'candidates' || lower.includes('candidate claims')) {
    const candidates = deck.slides.flatMap((s) => s.claims.filter((c) => c.status === 'candidate').map((c) => `- ${c.id} (slide ${s.order}): ${c.text}`))
    return candidates.length
      ? `Candidate claims awaiting review (${candidates.length}):\n${[...new Set(candidates)].join('\n')}`
      : 'No candidate claims — everything referenced is approved, qualified, or rejected.'
  }
  const showMatch = lower.startsWith('show ') ? input.slice(5).trim() : null
  if (showMatch) {
    const hit = findClaim(deck, showMatch)
    if (!hit) return `No claim '${showMatch}' is bound to any slide in this deck.`
    return {
      content: [
        hit.claim.text,
        hit.claim.required_qualifier ? `Required qualifier: ${hit.claim.required_qualifier}` : '',
      ].filter(Boolean).join('\n'),
      extra: {
        evidenceCase: true,
        title: `Claim ${hit.claim.id} · slide ${hit.slide.order}`,
        footer: `status ${hit.claim.status} · risk ${hit.claim.risk} · kind ${hit.claim.kind}`,
        skillUsed: 'pitchdeck',
      },
    }
  }
  for (const verb of ['approve', 'reject', 'qualify'] as const) {
    if (lower.startsWith(`${verb} `)) {
      const id = input.slice(verb.length + 1).trim()
      const hit = findClaim(deck, id)
      if (!hit) return `No claim '${id}' found in this deck's slides.`
      const status = verb === 'reject' ? 'rejected' : 'approved'
      return [
        `To ${verb} '${id}', edit claim_ledger.yaml: set its status to '${status}'` +
          (verb === 'qualify' ? " (valid statuses are candidate/approved/rejected) and set 'required_qualifier' — a qualified claim is an approved claim carrying its required qualifier." : '.'),
        'Then re-validate and re-emit — chat never mutates the deck directly:',
        '```',
        './run.sh verify --bundle-dir <bundle>',
        './run.sh emit-ui --bundle-dir <bundle> --output-dir ui/public',
        '```',
        'The claim boundary stays with the compiler; this panel only reads the emitted bundle.',
      ].join('\n')
    }
  }
  return [
    'Commands I answer deterministically from the validated bundle:',
    '- `gaps` — open validation gaps',
    '- `candidates` — claims awaiting human review',
    '- `show <claim-id>` — full claim record',
    '- `approve|reject|qualify <claim-id>` — exact ledger edit + re-emit commands',
    'Deck edits I can PROPOSE (you confirm, the compiler validates):',
    '- `hide|unhide slide <n>` · `delete|duplicate slide <n>` · `move slide <n> to <m>`',
    '- `set title|message|notes|footer of slide <n> to <text>`',
    'Set VITE_DECK_AGENT_URL to route free-form questions to a live project agent.',
  ].join('\n')
}

export function DeckChat({ deck, onChanged }: { deck: UiDeckBundle; onChanged?: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<DeckCommand | null>(null)
  const [steps, setSteps] = useState<{ id: string; label: string; status: string }[]>([])
  // Voice dictation (RealtimeSTT + faster-whisper, local, no keys): the
  // transcript enters the NORMAL send path — command grammar, simulate,
  // human Apply — never the deck directly.
  const [voiceStatus, setVoiceStatus] = useState<'off' | 'listening'>('off')

  const onSend = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, msg('user', text)])
      const command = parseCommand(deck, text)
      if (command) {
        // Pin the revision the proposal was computed against (review P1):
        // a reorder before Apply produces a CAS 409, never a silent rebase
        // onto a different referent.
        const pinned = { ...command, base_revision: revisionStore.current, preview: null }
        setPending(pinned)
        setBusy(true)
        setSteps([{ id: 'checking-gates', label: 'Dry-running the proposal through the compiler', status: 'running' }])
        const preview = await fetchSimulate(pinned)
        setBusy(false)
        setSteps([])
        setPending((current) => (current && current.summary === pinned.summary ? { ...current, preview } : current))
        setMessages((prev) => [
          ...prev,
          msg(
            'assistant',
            preview
              ? preview.would_pass
                ? 'Simulated: this change PASSES validation. Confirm with the Apply card.'
                : `Simulated: this change would be REJECTED. Apply is disabled — amend and re-propose.`
              : 'Simulation unavailable; Apply will validate on commit.',
            preview
              ? {
                  title: pinned.summary,
                  footer: preview.would_pass ? 'compiler dry-run: PASS' : `blocked by ${preview.gate_codes.join(', ') || 'validation'}`,
                  skillUsed: 'pitchdeck simulate',
                  evidenceCase: !preview.would_pass,
                  thinkingTrace: preview.gate_codes.map((code) => ({ id: code, label: code, status: 'failed' })),
                }
              : undefined,
          ),
        ])
        return
      }
      const endpoint = import.meta.env.VITE_DECK_AGENT_URL as string | undefined
      if (endpoint) {
        setBusy(true)
        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ deck_id: deck.deck_id, text }),
          })
          if (!response.ok) throw new Error(`agent endpoint ${response.status}`)
          const data = (await response.json()) as { reply?: string }
          setMessages((prev) => [...prev, msg('assistant', data.reply ?? 'Agent returned no reply field.')])
        } catch (error) {
          setMessages((prev) => [
            ...prev,
            msg('assistant', `Agent endpoint failed (${String(error)}); falling back to local commands.`),
          ])
        } finally {
          setBusy(false)
        }
        return
      }
      const answer = interpret(deck, text)
      setMessages((prev) => [
        ...prev,
        typeof answer === 'string' ? msg('assistant', answer) : msg('assistant', answer.content, answer.extra),
      ])
    },
    [deck],
  )

  const onVoiceToggle = useCallback(
    async (enabled: boolean) => {
      if (!enabled) {
        setVoiceStatus('off')
        return
      }
      setVoiceStatus('listening')
      try {
        const response = await fetch('/api/record-transcript', { method: 'POST' })
        const data = (await response.json()) as { status?: string; transcript?: string; reason?: string; error?: string }
        if (data.status === 'PASS' && data.transcript) {
          await onSend(data.transcript)
        } else {
          setMessages((prev) => [...prev, msg('assistant', `Dictation unavailable: ${data.reason ?? data.error ?? 'no transcript'}`)])
        }
      } catch (error) {
        setMessages((prev) => [...prev, msg('assistant', `Dictation failed: ${String(error)}`)])
      } finally {
        setVoiceStatus('off')
      }
    },
    [onSend],
  )

  const candidateCount = deck.slides
    .flatMap((slide) => slide.claims)
    .filter((claim) => claim.status === 'candidate')
  const firstCandidate = candidateCount[0]

  const applyPending = async () => {
    if (!pending) return
    setBusy(true)
    const failure = await applyCommand(pending)
    setBusy(false)
    setPending(null)
    if (failure) {
      setMessages((prev) => [...prev, msg('assistant', `Rejected by the compiler: ${failure}`)])
    } else {
      setMessages((prev) => [...prev, msg('assistant', `Applied: ${pending.summary}. The bundle re-validated and re-emitted.`)])
      onChanged?.()
    }
  }

  const proposalCard = pending ? (
        <div
          data-qid="deck:chat:proposal"
          className="mx-2 mb-1 flex items-center gap-2 rounded-lg border border-cyan-700/60 bg-cyan-950/40 px-3 py-2 text-xs text-cyan-100"
        >
          <span className="min-w-0 flex-1 truncate" title={pending.summary}>{pending.summary}</span>
          {pending.preview ? (
            <span
              data-qid="deck:chat:proposal:verdict"
              title={pending.preview.would_pass ? 'Compiler dry-run passed' : `Would be rejected: ${pending.preview.gate_codes.join(', ')}`}
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${pending.preview.would_pass ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}
            >
              {pending.preview.would_pass ? 'PASS' : pending.preview.gate_codes[0] || 'REJECT'}
            </span>
          ) : null}
          <Button
            type="button"
            data-qid="deck:chat:proposal:apply"
            data-qs-action="DECK_CHAT_APPLY_PROPOSAL"
            title="Apply this proposed command (compiler validates first)"
            disabled={busy || (pending.preview ? !pending.preview.would_pass : false)}
            onClick={() => void applyPending()}
            className="inline-flex cursor-pointer items-center gap-1 rounded bg-cyan-600 px-2 py-1 font-medium text-white hover:bg-cyan-500 disabled:opacity-40"
          >
            <Check aria-hidden className="h-3 w-3" /> Apply
          </Button>
          <Button
            type="button"
            data-qid="deck:chat:proposal:dismiss"
            data-qs-action="DECK_CHAT_DISMISS_PROPOSAL"
            title="Dismiss this proposal without applying it"
            disabled={busy}
            onClick={() => setPending(null)}
            className="inline-flex cursor-pointer items-center rounded p-1 text-cyan-300 hover:bg-cyan-900/60"
          >
            <X aria-hidden className="h-3 w-3" />
          </Button>
        </div>
  ) : null

  return (
    <ChatWell
      actionSlot={proposalCard}
      messages={messages}
      onSend={onSend}
      isStreaming={busy}
      streamingSteps={steps}
      qid="deck:chat:claims"
      surface="pitchdeck"
      voiceEnabled={voiceStatus !== 'off'}
      voiceStatus={voiceStatus === 'listening' ? 'listening' : 'idle'}
      voiceLabel="dictation (RealtimeSTT)"
      projectLabel="PITCHDECK COMPILER"
      onVoiceToggle={(enabled: boolean) => void onVoiceToggle(enabled)}
      placeholder="Ask about this deck…"
      emptyTitle={`Reviewing ${deck.title}`}
      emptyDescription={`${deck.visibility} deck · ${deck.validation_readiness} · ${new Set(candidateCount.map((c) => c.id)).size} candidate claims await review. Ask for gaps, inspect a claim, or get the exact ledger commands to approve, reject, or qualify it.`}
      starterChips={[
        { label: `Open gaps (${deck.validation_gaps.length})`, prompt: 'gaps', dataQid: 'deck:chat:chip:gaps' },
        { label: 'Candidate claims', prompt: 'candidates', dataQid: 'deck:chat:chip:candidates' },
        ...(firstCandidate
          ? [{ label: 'Inspect first candidate', prompt: `show ${firstCandidate.id}`, dataQid: 'deck:chat:chip:first-candidate' }]
          : []),
      ]}
    />
  )
}
