/**
 * PersonaPlex ChatWell speech_final bridge.
 *
 * The SPARTA Explorer ChatWell still sends the normal Pi chat request, but this
 * client mirrors each final text turn to the PersonaPlex golden_state_server so
 * PersonaPlexVoiceTracePanel receives live grounding/tool events.
 *
 * Protocol accepted by golden_state_server:
 *   ws://127.0.0.1:8788/ws
 *   {"type":"speech_final","session_id":"...","text":"...","persona_id":"embry","turn_id":1}
 */

export type PersonaPlexSpeechFinalPayload = {
  type: 'speech_final'
  session_id: string
  text: string
  persona_id: string
  turn_id: number
}

export type PersonaPlexSpeechFinalResult = {
  sent: boolean
  wsUrl: string
  payload: PersonaPlexSpeechFinalPayload | null
  reason?: string
  error?: string
}

export type PersonaPlexSpeechFinalOptions = {
  wsUrl?: string
  sessionId?: string
  personaId?: string
  turnId?: number
  timeoutMs?: number
  logger?: Pick<Console, 'debug' | 'warn'>
  WebSocketCtor?: typeof WebSocket
}

const DEFAULT_WS_URL = 'ws://127.0.0.1:8788/ws'
const DEFAULT_PERSONA_ID = 'embry'
const SESSION_KEY = 'personaplex.chatwell.session_id'
const TURN_KEY = 'personaplex.chatwell.turn_id'
const WS_CONNECTING = 0
const WS_OPEN = 1
const WS_CLOSED = 3

let activeSocket: WebSocket | null = null
let activeSocketUrl: string | null = null
let openingSocket: Promise<WebSocket> | null = null
let fallbackSessionId: string | null = null
let fallbackTurnId = 0

function getStorage(): Storage | null {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      return window.sessionStorage
    }
  } catch {
    return null
  }
  return null
}

function randomId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    // fall through
  }
  return `chatwell-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function getPersonaPlexChatWellSessionId(explicitSessionId?: string): string {
  if (explicitSessionId && explicitSessionId.trim()) return explicitSessionId.trim()

  const storage = getStorage()
  if (storage) {
    const existing = storage.getItem(SESSION_KEY)
    if (existing) return existing
    const created = randomId()
    storage.setItem(SESSION_KEY, created)
    return created
  }

  if (!fallbackSessionId) fallbackSessionId = randomId()
  return fallbackSessionId
}

export function nextPersonaPlexChatWellTurnId(explicitTurnId?: number): number {
  if (typeof explicitTurnId === 'number' && Number.isFinite(explicitTurnId) && explicitTurnId > 0) {
    return Math.floor(explicitTurnId)
  }

  const storage = getStorage()
  if (storage) {
    const prior = Number.parseInt(storage.getItem(TURN_KEY) || '0', 10)
    const next = Number.isFinite(prior) ? prior + 1 : 1
    storage.setItem(TURN_KEY, String(next))
    return next
  }

  fallbackTurnId += 1
  return fallbackTurnId
}

function resolveWebSocketCtor(options: PersonaPlexSpeechFinalOptions): typeof WebSocket {
  if (options.WebSocketCtor) return options.WebSocketCtor
  if (typeof WebSocket !== 'undefined') return WebSocket
  throw new Error('WebSocket is not available in this runtime')
}

function waitForOpen(socket: WebSocket, timeoutMs: number): Promise<WebSocket> {
  if (socket.readyState === WS_OPEN) return Promise.resolve(socket)

  return new Promise((resolve, reject) => {
    let settled = false
    const timer = globalThis.setTimeout(() => {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error(`PersonaPlex WebSocket open timed out after ${timeoutMs}ms`))
    }, timeoutMs)

    const cleanup = () => {
      globalThis.clearTimeout(timer)
      socket.removeEventListener('open', onOpen)
      socket.removeEventListener('error', onError)
      socket.removeEventListener('close', onClose)
    }
    const onOpen = () => {
      if (settled) return
      settled = true
      cleanup()
      resolve(socket)
    }
    const onError = () => {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error('PersonaPlex WebSocket error while opening'))
    }
    const onClose = () => {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error('PersonaPlex WebSocket closed before opening'))
    }

    socket.addEventListener('open', onOpen)
    socket.addEventListener('error', onError)
    socket.addEventListener('close', onClose)
  })
}

async function ensurePersonaPlexSocket(
  wsUrl: string,
  options: PersonaPlexSpeechFinalOptions,
): Promise<WebSocket> {
  if (activeSocket && activeSocketUrl === wsUrl && activeSocket.readyState === WS_OPEN) {
    return activeSocket
  }

  if (activeSocket && activeSocket.readyState === WS_CONNECTING && activeSocketUrl === wsUrl) {
    if (!openingSocket) openingSocket = waitForOpen(activeSocket, options.timeoutMs ?? 2500)
    return openingSocket
  }

  if (activeSocket && activeSocket.readyState !== WS_CLOSED) {
    try {
      activeSocket.close()
    } catch {
      // ignore best-effort close failure
    }
  }

  const WebSocketCtor = resolveWebSocketCtor(options)
  const socket = new WebSocketCtor(wsUrl)
  activeSocket = socket
  activeSocketUrl = wsUrl
  socket.addEventListener('close', () => {
    if (activeSocket === socket) activeSocket = null
    if (activeSocketUrl === wsUrl) activeSocketUrl = null
    openingSocket = null
  })
  socket.addEventListener('error', () => {
    if (activeSocket === socket && socket.readyState !== WS_OPEN) activeSocket = null
    openingSocket = null
  })

  openingSocket = waitForOpen(socket, options.timeoutMs ?? 2500)
  try {
    return await openingSocket
  } finally {
    openingSocket = null
  }
}

export function buildPersonaPlexSpeechFinalPayload(
  text: string,
  options: PersonaPlexSpeechFinalOptions = {},
): PersonaPlexSpeechFinalPayload | null {
  const trimmedText = text.trim()
  if (!trimmedText) return null

  return {
    type: 'speech_final',
    session_id: getPersonaPlexChatWellSessionId(options.sessionId),
    text: trimmedText,
    persona_id: options.personaId ?? DEFAULT_PERSONA_ID,
    turn_id: nextPersonaPlexChatWellTurnId(options.turnId),
  }
}

export async function sendPersonaPlexSpeechFinal(
  text: string,
  options: PersonaPlexSpeechFinalOptions = {},
): Promise<PersonaPlexSpeechFinalResult> {
  const wsUrl = options.wsUrl ?? DEFAULT_WS_URL
  const payload = buildPersonaPlexSpeechFinalPayload(text, options)
  if (!payload) return { sent: false, wsUrl, payload: null, reason: 'empty_text' }

  const socket = await ensurePersonaPlexSocket(wsUrl, options)
  socket.send(JSON.stringify(payload))
  options.logger?.debug?.('PersonaPlex speech_final sent', payload)
  return { sent: true, wsUrl, payload }
}

export async function sendPersonaPlexSpeechFinalBestEffort(
  text: string,
  options: PersonaPlexSpeechFinalOptions = {},
): Promise<PersonaPlexSpeechFinalResult> {
  const wsUrl = options.wsUrl ?? DEFAULT_WS_URL
  try {
    return await sendPersonaPlexSpeechFinal(text, options)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    ;(options.logger ?? console).warn?.('PersonaPlex speech_final send failed', message)
    return { sent: false, wsUrl, payload: null, reason: 'send_failed', error: message }
  }
}

export function __resetPersonaPlexSpeechFinalClientForTests(): void {
  if (activeSocket && activeSocket.readyState !== WS_CLOSED) {
    try {
      activeSocket.close()
    } catch {
      // ignore
    }
  }
  activeSocket = null
  activeSocketUrl = null
  openingSocket = null
  fallbackSessionId = null
  fallbackTurnId = 0
}
