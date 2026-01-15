import type { ClarifySessionPayload, SubmitResponse } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') ?? ''

const withBase = (path: string) => `${API_BASE}${path}`

export async function fetchSession(): Promise<ClarifySessionPayload> {
  const res = await fetch(withBase('/api/questions'))
  if (!res.ok) {
    throw new Error(`Failed to load questions (${res.status})`)
  }
  return res.json()
}

export async function submitResponses(payload: SubmitResponse): Promise<void> {
  const res = await fetch(withBase('/api/responses'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || 'Failed to submit responses')
  }
}
