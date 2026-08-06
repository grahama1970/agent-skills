import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Eraser, PanelLeftClose, Plus, Search, Settings, type LucideIcon } from 'lucide-react'
import { useRegisterAction } from './_support/useRegisterAction'

export type GlobalCommandId = 'export_log' | 'clear_chat' | 'toggle_sidebar' | 'new_session' | 'settings'

interface GlobalCommand {
  id: GlobalCommandId
  title: string
  category: string
  action: string
  icon: LucideIcon
}

type CommandPaletteProject = {
  id: string
  name: string
}

type CommandPaletteSession = {
  id: string
  projectId: string
  title: string
  messageCount?: number
}

interface CommandPaletteProps {
  onExecuteGlobal?: (commandId: GlobalCommandId) => void
  projects?: CommandPaletteProject[]
  sessions?: CommandPaletteSession[]
  onSelectSession?: (sessionId: string) => void
}

const GLOBAL_COMMANDS: GlobalCommand[] = [
  { id: 'export_log', icon: Download, title: 'Export Chat Log', category: 'Data', action: 'SPARTA_EXPORT_CHAT_LOG' },
  { id: 'clear_chat', icon: Eraser, title: 'Clear Execution History', category: 'Data', action: 'SPARTA_CLEAR_CHAT_HISTORY' },
  { id: 'toggle_sidebar', icon: PanelLeftClose, title: 'Toggle Sidebar', category: 'View', action: 'SHARED_CHAT_TOGGLE_SIDEBAR' },
  { id: 'new_session', icon: Plus, title: 'Start New Analysis Session', category: 'System', action: 'SPARTA_START_NEW_SESSION' },
  { id: 'settings', icon: Settings, title: 'Preferences...', category: 'System', action: 'OPEN_SETTINGS' },
]

export default function CommandPalette({
  onExecuteGlobal,
  projects = [],
  sessions = [],
  onSelectSession,
}: CommandPaletteProps): JSX.Element | null {
  useRegisterAction('shared-chat:command-palette:input', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_COMMAND_PALETTE_SEARCH',
    label: 'Search global commands',
    description: 'Filter the global command palette',
  })
  useRegisterAction('shared-chat:command-palette:command:export_log', {
    app: 'sparta-explorer',
    action: 'SPARTA_EXPORT_CHAT_LOG',
    label: 'Export Chat Log',
    description: 'Export the current Sparta chat log',
  })
  useRegisterAction('shared-chat:command-palette:command:clear_chat', {
    app: 'sparta-explorer',
    action: 'SPARTA_CLEAR_CHAT_HISTORY',
    label: 'Clear Execution History',
    description: 'Clear the current Sparta chat history',
  })
  useRegisterAction('shared-chat:command-palette:command:toggle_sidebar', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_TOGGLE_SIDEBAR',
    label: 'Toggle Sidebar',
    description: 'Collapse or expand the Sparta chat sidebar',
  })
  useRegisterAction('shared-chat:command-palette:command:new_session', {
    app: 'sparta-explorer',
    action: 'SPARTA_START_NEW_SESSION',
    label: 'Start New Analysis Session',
    description: 'Start a fresh Sparta analysis session',
  })
  useRegisterAction('shared-chat:command-palette:command:settings', {
    app: 'sparta-explorer',
    action: 'OPEN_SETTINGS',
    label: 'Preferences',
    description: 'Open Sparta preferences',
  })

  const [isOpen, setOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const projectNamesById = useMemo(() => new Map(projects.map((project) => [project.id, project.name])), [projects])
  const filteredCommands = useMemo(() => {
    const needle = searchText.trim().toLowerCase()
    if (!needle) return GLOBAL_COMMANDS
    return GLOBAL_COMMANDS.filter((command) => (
      command.title.toLowerCase().includes(needle)
      || command.category.toLowerCase().includes(needle)
      || command.id.toLowerCase().includes(needle)
    ))
  }, [searchText])
  const filteredSessions = useMemo(() => {
    const needle = searchText.trim().toLowerCase()
    if (!needle) return sessions.slice(0, 8)
    return sessions.filter((session) => {
      const projectName = projectNamesById.get(session.projectId) ?? ''
      return session.title.toLowerCase().includes(needle)
        || projectName.toLowerCase().includes(needle)
        || session.id.toLowerCase().includes(needle)
    }).slice(0, 8)
  }, [projectNamesById, searchText, sessions])
  const selectableCount = filteredCommands.length + filteredSessions.length

  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((current) => !current)
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [])

  useEffect(() => {
    if (!isOpen) return
    setSearchText('')
    setSelectedIndex(0)
    window.setTimeout(() => inputRef.current?.focus(), 50)
  }, [isOpen])

  useEffect(() => {
    setSelectedIndex((current) => {
      if (selectableCount === 0) return 0
      return Math.min(current, selectableCount - 1)
    })
  }, [selectableCount])

  const executeCommand = (command: GlobalCommand) => {
    onExecuteGlobal?.(command.id)
    setOpen(false)
  }

  const executeSession = (sessionId: string) => {
    onSelectSession?.(sessionId)
    setOpen(false)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setSelectedIndex((current) => (current < selectableCount - 1 ? current + 1 : current))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setSelectedIndex((current) => (current > 0 ? current - 1 : 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const selectedCommand = filteredCommands[selectedIndex]
      if (selectedCommand) {
        executeCommand(selectedCommand)
        return
      }
      const selectedSession = filteredSessions[selectedIndex - filteredCommands.length]
      if (selectedSession) executeSession(selectedSession.id)
    }
  }

  if (!isOpen) return null

  return (
    <div
      data-qid="shared-chat:command-palette:backdrop"
      onClick={() => setOpen(false)}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(13, 17, 23, 0.7)',
        backdropFilter: 'blur(4px)',
        zIndex: 99999,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'flex-start',
        padding: '15vh 20px 20px',
      }}
    >
      <div
        data-qid="shared-chat:command-palette"
        onClick={(event) => event.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 600,
          backgroundColor: 'var(--surface-base)',
          border: '1px solid var(--border-default)',
          borderRadius: 12,
          boxShadow: '0 24px 48px rgba(0,0,0,0.8), 0 0 0 1px rgba(88, 166, 255, 0.2)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', padding: 16, borderBottom: '1px solid var(--border-subtle)' }}>
          <Search size={18} color="#58a6ff" style={{ marginRight: 12, flexShrink: 0 }} />
          <input
            ref={inputRef}
            data-qid="shared-chat:command-palette:input"
            data-qs-action="SHARED_CHAT_COMMAND_PALETTE_SEARCH"
            title="Search commands"
            type="text"
            value={searchText}
            onChange={(event) => setSearchText(event.currentTarget.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search commands..."
            style={{
              flex: 1,
              minWidth: 0,
              backgroundColor: 'transparent',
              border: 'none',
              color: 'var(--text-primary)',
              fontSize: 16,
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              outline: 'none',
            }}
          />
          <span style={{ color: '#484f58', fontFamily: '"SF Mono", Consolas, monospace', fontSize: 12, padding: '2px 6px', backgroundColor: 'var(--surface-raised)', borderRadius: 4, border: '1px solid var(--border-default)' }}>
            ESC
          </span>
        </div>

        <div style={{ maxHeight: 300, overflowY: 'auto', padding: 8 }}>
          {selectableCount === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
              No commands found.
            </div>
          ) : null}
          {filteredCommands.map((command, index) => {
            const Icon = command.icon
            const isSelected = index === selectedIndex
            return (
              <button
                key={command.id}
                type="button"
                data-qid={`shared-chat:command-palette:command:${command.id}`}
                data-qs-action={command.action}
                title={command.title}
                onMouseEnter={() => setSelectedIndex(index)}
                onClick={() => executeCommand(command)}
                style={{
                  width: '100%',
                  minHeight: 48,
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px 16px',
                  backgroundColor: isSelected ? 'var(--surface-raised)' : 'transparent',
                  border: 0,
                  borderLeft: isSelected ? '3px solid #58a6ff' : '3px solid transparent',
                  borderRadius: 6,
                  cursor: 'pointer',
                  gap: 12,
                  textAlign: 'left',
                  transition: 'background-color 0.1s',
                }}
              >
                <Icon size={16} strokeWidth={1.8} color={isSelected ? '#58a6ff' : 'var(--text-muted)'} />
                <span style={{ color: isSelected ? 'var(--text-primary)' : '#c9d1d9', fontSize: 13, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontWeight: isSelected ? 600 : 400, flex: 1 }}>
                  {command.title}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: '"SF Mono", Consolas, monospace' }}>
                  {command.category}
                </span>
              </button>
            )
          })}
          {filteredSessions.length > 0 && (
            <div style={{ padding: '10px 12px 6px', color: '#64748b', fontSize: 10, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Investigations
            </div>
          )}
          {filteredSessions.map((session, index) => {
            const absoluteIndex = filteredCommands.length + index
            const isSelected = absoluteIndex === selectedIndex
            const projectName = projectNamesById.get(session.projectId) ?? 'Workspace'
            return (
              <button
                key={session.id}
                type="button"
                data-qid={`shared-chat:command-palette:session:${session.id}`}
                data-qs-action="SHARED_CHAT_SELECT_SESSION"
                title={`Open investigation: ${session.title || 'New Investigation'}`}
                onMouseEnter={() => setSelectedIndex(absoluteIndex)}
                onClick={() => executeSession(session.id)}
                style={{
                  width: '100%',
                  minHeight: 48,
                  minWidth: 0,
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px 16px',
                  backgroundColor: isSelected ? 'var(--surface-raised)' : 'transparent',
                  border: 0,
                  borderLeft: isSelected ? '3px solid #58a6ff' : '3px solid transparent',
                  borderRadius: 6,
                  cursor: 'pointer',
                  gap: 12,
                  textAlign: 'left',
                  transition: 'background-color 0.1s',
                }}
              >
                <Search size={16} strokeWidth={1.8} color={isSelected ? '#58a6ff' : 'var(--text-muted)'} style={{ flexShrink: 0 }} />
                <span style={{ display: 'flex', flexDirection: 'column', gap: 3, flex: 1, minWidth: 0 }}>
                  <span style={{ color: isSelected ? 'var(--text-primary)' : '#c9d1d9', fontSize: 13, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontWeight: isSelected ? 600 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {session.title || 'New Investigation'}
                  </span>
                  <span style={{ color: '#64748b', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {projectName}
                  </span>
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: '"SF Mono", Consolas, monospace', flexShrink: 0 }}>
                  {session.messageCount ?? 0}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
