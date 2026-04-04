import { useState, useEffect, useRef, useCallback } from 'react'
import { NVIS } from '../theme'
import type { ChatMessage } from '../types'

interface ChatFABProps {
  currentView: string
  selectedDocId?: string
  selectedSection?: string
}

const CHAT_SVG = (
  <svg viewBox="0 0 24 24" width={22} height={22} fill="white" aria-hidden="true">
    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" />
    <path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z" />
  </svg>
)

const CLOSE_SVG = (
  <svg viewBox="0 0 24 24" width={22} height={22} fill="white" aria-hidden="true" style={{ transform: 'rotate(45deg)' }}>
    <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
  </svg>
)

export default function ChatFAB({ currentView, selectedDocId, selectedSection }: ChatFABProps) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)

  // Build context string shown in the placeholder / first message
  const contextParts: string[] = []
  if (currentView) contextParts.push(`view=${currentView}`)
  if (selectedDocId) contextParts.push(`doc=${selectedDocId}`)
  if (selectedSection) contextParts.push(`section=${selectedSection}`)
  const contextStr = contextParts.join(', ')
  const placeholder = `Ask about ${currentView}${contextStr ? ` (${contextStr})` : ''}… routes to /memory clarify`

  // Keyboard shortcut: ? opens drawer
  const handleGlobalKey = useCallback((e: KeyboardEvent) => {
    if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
      e.preventDefault()
      setOpen((prev) => !prev)
    }
    if (e.key === 'Escape' && open) {
      setOpen(false)
    }
  }, [open])

  useEffect(() => {
    window.addEventListener('keydown', handleGlobalKey)
    return () => window.removeEventListener('keydown', handleGlobalKey)
  }, [handleGlobalKey])

  // Focus input when drawer opens
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' })
  }, [messages])

  // Close on click outside drawer
  useEffect(() => {
    if (!open) return
    const handle = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        // Don't close if the FAB itself was clicked (it toggles)
        setOpen(false)
      }
    }
    // Delay so the open-click doesn't immediately close
    const id = setTimeout(() => document.addEventListener('mousedown', handle), 100)
    return () => { clearTimeout(id); document.removeEventListener('mousedown', handle) }
  }, [open])

  const sendMessage = () => {
    const text = input.trim()
    if (!text) return

    const userMsg: ChatMessage = { id: `msg-${Date.now()}`, role: 'user', text, timestamp: new Date().toLocaleTimeString() }
    const agentMsg: ChatMessage = {
      id: `msg-${Date.now() + 1}`, role: 'agent',
      text: `[/memory clarify] Context: ${contextStr || currentView}. Query: "${text}" — routed to Embry Agent.`,
      timestamp: new Date().toLocaleTimeString(),
    }
    setMessages((prev) => [...prev, userMsg, agentMsg])
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <>
      {/* Drawer */}
      {open && (
        <div
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-label="Embry Agent chat"
          style={{
            position: 'fixed', right: 0, bottom: 0, top: 0,
            width: 400, background: NVIS.surface,
            borderLeft: `1px solid ${NVIS.borderSolid}`,
            display: 'flex', flexDirection: 'column',
            zIndex: 200,
          }}
        >
          {/* Drawer header */}
          <div style={{
            height: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 16px', borderBottom: `1px solid ${NVIS.borderSolid}`, flexShrink: 0,
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: NVIS.white }}>Embry Agent</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {contextStr && (
                <span style={{ fontSize: 10, color: NVIS.dim, background: NVIS.surface2, padding: '2px 6px', borderRadius: 3 }}>
                  {contextStr}
                </span>
              )}
              <button
                aria-label="Close chat"
                onClick={() => setOpen(false)}
                style={{
                  background: 'none', border: 'none', color: NVIS.dim, cursor: 'pointer',
                  fontSize: 18, padding: '2px 4px', fontFamily: 'monospace',
                }}
              >
                &times;
              </button>
            </div>
          </div>

          {/* Messages area */}
          <div
            role="log"
            aria-label="Chat messages"
            aria-live="polite"
            style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}
          >
            {messages.length === 0 && (
              <div style={{ color: NVIS.dim, fontSize: 12, textAlign: 'center', marginTop: 32 }}>
                <div style={{ marginBottom: 8, color: NVIS.dim }}>Ask about the current view</div>
                <div style={{ fontSize: 11, color: NVIS.dim }}>Routes to /memory clarify</div>
                {contextStr && (
                  <div style={{ marginTop: 12, fontSize: 10, color: NVIS.dim }}>
                    Context: {contextStr}
                  </div>
                )}
              </div>
            )}
            {messages.map((msg) => {
              const isUser = msg.role === 'user'
              return (
                <div
                  key={msg.id}
                  style={{
                    display: 'flex', flexDirection: 'column',
                    alignItems: isUser ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div style={{
                    maxWidth: '85%', padding: '8px 12px', borderRadius: 6, fontSize: 12,
                    background: isUser ? `${NVIS.accent}22` : NVIS.surface2,
                    border: `1px solid ${isUser ? `${NVIS.accent}40` : NVIS.borderSolid}`,
                    color: NVIS.white,
                  }}>
                    {msg.text}
                  </div>
                  <span style={{ fontSize: 9, color: NVIS.dim, marginTop: 3 }}>{msg.timestamp}</span>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area */}
          <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${NVIS.borderSolid}` }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                aria-label="Chat message input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                rows={2}
                style={{
                  flex: 1, background: NVIS.bg, border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: 4, color: NVIS.white, fontSize: 12, padding: '8px 10px',
                  fontFamily: 'monospace', resize: 'none',
                  // Keep outline for focus-visible (overridden below via CSS in App.tsx)
                }}
                onFocus={(e) => {
                  const el = e.currentTarget as HTMLTextAreaElement
                  el.style.borderColor = NVIS.accent
                  el.style.outline = `2px solid ${NVIS.accent}`
                  el.style.outlineOffset = '2px'
                }}
                onBlur={(e) => {
                  const el = e.currentTarget as HTMLTextAreaElement
                  el.style.borderColor = NVIS.borderSolid
                  el.style.outline = 'none'
                }}
              />
              <button
                aria-label="Send message"
                onClick={sendMessage}
                disabled={!input.trim()}
                style={{
                  background: input.trim() ? NVIS.accent : NVIS.surface2,
                  border: 'none', borderRadius: 4, color: 'white', fontSize: 11,
                  padding: '8px 12px', cursor: input.trim() ? 'pointer' : 'default',
                  fontFamily: 'monospace', flexShrink: 0,
                  opacity: input.trim() ? 1 : 0.5,
                }}
              >
                Send
              </button>
            </div>
            <div style={{ fontSize: 9, color: NVIS.dim, marginTop: 6 }}>
              Enter to send · Shift+Enter for newline · Esc to close · ? to toggle
            </div>
          </div>
        </div>
      )}

      {/* FAB button */}
      <button
        aria-label={open ? 'Close Embry Agent chat' : 'Open Embry Agent chat (press ? to toggle)'}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((prev) => !prev)}
        style={{
          position: 'fixed',
          bottom: 44,  // above MonitorStrip (32px) + 12px margin
          right: 20,
          width: 48, height: 48,
          borderRadius: 24,
          background: open ? NVIS.red : NVIS.accent,
          border: `2px solid ${open ? `${NVIS.red}80` : `${NVIS.accent}80`}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', zIndex: 201,
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        }}
        onMouseEnter={(e) => { if (!open) (e.currentTarget as HTMLButtonElement).style.background = '#5babff' }}
        onMouseLeave={(e) => { if (!open) (e.currentTarget as HTMLButtonElement).style.background = NVIS.accent }}
      >
        {open ? CLOSE_SVG : CHAT_SVG}
      </button>
    </>
  )
}
