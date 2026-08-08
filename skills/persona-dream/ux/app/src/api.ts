/** Typed client for ux/server.py.
 *
 * Every shape here mirrors a schema the server actually emits, so a field that
 * disappears upstream becomes a type error rather than a blank panel. The
 * boundary fields are non-optional on purpose: a dream journal is what she made
 * of her day, not a record of it, and the UI must not be able to drop that
 * qualifier by forgetting to render an optional.
 */

export interface JournalBoundary {
  canon_status: string
  never_promote_to_event_fact: boolean
  asserts_only_own_inner_state: boolean
  note: string
}

/** A paragraph carries its own delivery tone.
 *
 * `status` is almost always "requested", and that word is load-bearing: it says
 * this tone was asked of the renderer, not that a listener would perceive it.
 * Render the qualifier, never just the tone name.
 */
export interface JournalParagraph {
  text: string
  tone?: string
  intensity?: string
  status?: string
}

export interface JournalSource {
  n: number
  source_id: string
  scope: string
  excerpt: string
  synthetic: boolean
}

export interface Journal {
  run_id: string
  persona: string
  title: string
  preamble: string[]
  paragraphs: JournalParagraph[]
  footnotes: Record<string, string>
  journal_present: boolean
  sources: JournalSource[]
  tensions: Array<Record<string, unknown>>
  audio: string | null
  boundary: JournalBoundary
  session_mood: { mood_label?: string; mood_description?: string }
  unresolved_tension: string
  expanded_understanding: string
}

/** One conversation turn.
 *
 * The tone field is `requested_delivery_tone`, not `tone`, and the name is the
 * point: it records what was asked of Chatterbox, not what the audio achieved.
 * Each turn carries its own `tone_boundary` saying so. Do not shorten either
 * one in the UI -- collapsing them to "tone" is how a request quietly becomes
 * a claim about what a listener heard.
 */
export interface Turn {
  role: 'human' | 'agent' | 'embry'
  text: string
  requested_delivery_tone?: string
  tone_boundary?: string
  audio?: string
  audio_sha256?: string
  journal_spoken_sha256?: string
  created_at?: string
}

export interface Conversation {
  run_id: string
  turns: Turn[]
  tone_boundary: string
}

export interface RunSummary {
  run_id: string
  persona: string
  has_audio: boolean
  turns: number
}

export interface VoiceHealth {
  speak: { available: boolean; engine?: string; error?: string }
  listen: { available: boolean; engine?: string; reason?: string | null }
}

/** A reply that could not be spoken is never recorded, so the UI must be able
 *  to show the refusal rather than silently showing nothing. */
export interface ReplyResult {
  status: string
  text?: string
  tone?: string
  audio?: string
  chose_tone?: string
  tone_was_in_vocabulary?: boolean
  affect_effect?: { applied?: boolean; knob_source?: string } | null
  failed_gates?: string[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<{ ok: boolean; data: T }> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return { ok: res.ok, data: (await res.json()) as T }
}

export const api = {
  runs: () => get<{ runs: RunSummary[] }>('/api/runs'),
  journal: (id: string) => get<Journal>(`/api/runs/${id}/journal`),
  conversation: (id: string) => get<Conversation>(`/api/runs/${id}/conversation`),
  voiceHealth: () => get<VoiceHealth>('/api/voice/health'),

  say: (id: string, text: string) =>
    post<Record<string, unknown>>(`/api/runs/${id}/conversation`, { text, role: 'human' }),

  /** Ask her to reply. The server drafts through Tau, renders through
   *  Chatterbox, and appends only if both succeed. A 502 carries the gates. */
  reply: (id: string, text?: string) =>
    post<{ reply: ReplyResult } | ReplyResult>(`/api/runs/${id}/reply`, { text: text ?? null }),

  transcribe: async (blob: Blob): Promise<{ status: string; text: string }> => {
    const form = new FormData()
    form.append('audio', blob, 'utterance.webm')
    const res = await fetch('/api/voice/transcribe', { method: 'POST', body: form })
    return res.json()
  },

  audioUrl: (id: string, name: string) => `/api/runs/${id}/audio/${encodeURIComponent(name)}`,
}
