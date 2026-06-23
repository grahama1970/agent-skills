import {
  __resetPersonaPlexSpeechFinalClientForTests,
  buildPersonaPlexSpeechFinalPayload,
  sendPersonaPlexSpeechFinal,
} from '../personaplexSpeechFinalClient'

class MockWebSocket extends EventTarget {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  url: string

  constructor(url: string) {
    super()
    this.url = url
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.dispatchEvent(new Event('open'))
    }, 0)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.dispatchEvent(new Event('close'))
  }
}

describe('personaplexSpeechFinalClient', () => {
  beforeEach(() => {
    sessionStorage.clear()
    __resetPersonaPlexSpeechFinalClientForTests()
  })

  it('builds the golden_state_server speech_final payload', () => {
    const payload = buildPersonaPlexSpeechFinalPayload(' hello Embry ', {
      sessionId: 's-1',
      personaId: 'embry',
      turnId: 7,
    })
    expect(payload).toEqual({
      type: 'speech_final',
      session_id: 's-1',
      text: 'hello Embry',
      persona_id: 'embry',
      turn_id: 7,
    })
  })

  it('sends JSON over the persistent WebSocket', async () => {
    const result = await sendPersonaPlexSpeechFinal('What did SPARTA find?', {
      wsUrl: 'ws://127.0.0.1:8788/ws',
      sessionId: 'test-session',
      turnId: 1,
      WebSocketCtor: MockWebSocket as unknown as typeof WebSocket,
    })
    expect(result.sent).toBe(true)
    expect(result.payload).toMatchObject({
      type: 'speech_final',
      session_id: 'test-session',
      text: 'What did SPARTA find?',
      persona_id: 'embry',
      turn_id: 1,
    })
  })
})
