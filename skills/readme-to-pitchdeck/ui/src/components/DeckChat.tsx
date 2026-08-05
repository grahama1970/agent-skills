import { useCallback, useState } from 'react'
import { ChatWell } from '@ux-lab/ui/ChatWell'
import type { ChatMessage } from '@ux-lab/ui/ChatWell'
import type { UiDeckBundle } from '../types'

// Claim-review chat over the shared ux-lab ChatWell. The interpreter is
// deterministic: it answers from the emitted (seam-validated) bundle and
// emits exact CLI commands for mutations — it never edits deck content
// directly, so the fail-closed claim boundary stays with the compiler.
// Set VITE_DECK_AGENT_URL to forward unrecognized turns to a live agent.

let counter = 0
function msg(role: 'user' | 'assistant', content: string): ChatMessage {
  counter += 1
  return { id: `deck-chat-${counter}`, role, content, createdAt: new Date().toISOString() }
}

function findClaim(deck: UiDeckBundle, id: string) {
  for (const slide of deck.slides) {
    const claim = slide.claims.find((c) => c.id === id)
    if (claim) return { claim, slide }
  }
  return null
}

function interpret(deck: UiDeckBundle, text: string): string {
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
    return [
      `Claim ${hit.claim.id} (slide ${hit.slide.order}: ${hit.slide.title})`,
      `status: ${hit.claim.status} · risk: ${hit.claim.risk} · kind: ${hit.claim.kind}`,
      `text: ${hit.claim.text}`,
      hit.claim.required_qualifier ? `required qualifier: ${hit.claim.required_qualifier}` : '',
    ].filter(Boolean).join('\n')
  }
  for (const verb of ['approve', 'reject', 'qualify'] as const) {
    if (lower.startsWith(`${verb} `)) {
      const id = input.slice(verb.length + 1).trim()
      const hit = findClaim(deck, id)
      if (!hit) return `No claim '${id}' found in this deck's slides.`
      const status = verb === 'approve' ? 'approved' : verb === 'reject' ? 'rejected' : 'qualified'
      return [
        `To ${verb} '${id}', edit claim_ledger.yaml: set its status to '${status}'` +
          (verb === 'qualify' ? " and set 'required_qualifier'." : '.'),
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
    'Set VITE_DECK_AGENT_URL to route free-form questions to a live project agent.',
  ].join('\n')
}

export function DeckChat({ deck }: { deck: UiDeckBundle }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)

  const onSend = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, msg('user', text)])
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
            msg('assistant', `Agent endpoint failed (${String(error)}); falling back to local commands.\n\n${interpret(deck, text)}`),
          ])
        } finally {
          setBusy(false)
        }
        return
      }
      setMessages((prev) => [...prev, msg('assistant', interpret(deck, text))])
    },
    [deck],
  )

  const candidateCount = deck.slides
    .flatMap((slide) => slide.claims)
    .filter((claim) => claim.status === 'candidate')
  const firstCandidate = candidateCount[0]

  return (
    <ChatWell
      messages={messages}
      onSend={onSend}
      isStreaming={busy}
      qid="deck:chat:claims"
      surface="readme-to-pitchdeck"
      placeholder={`Review ${deck.title} — gaps · candidates · show <claim-id>`}
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
