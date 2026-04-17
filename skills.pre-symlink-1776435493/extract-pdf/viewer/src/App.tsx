import { useState } from 'react'
import { EmbryTopbarLogo } from '@embry/logo/react'
import DocumentView from './views/DocumentView'
import BatchView from './views/BatchView'
import CascadeView from './views/CascadeView'
import CompareView from './views/CompareView'

// NVIS color constants
export const NVIS = {
  bg: '#141414',
  border: 'rgba(255,255,255,0.13)',
  accent: '#4a9eff',
  green: '#00ff88',
  amber: '#ffaa00',
  red: '#ff4444',
} as const

type ViewTab = 'Document' | 'Batch' | 'Cascade' | 'Compare'

const TABS: ViewTab[] = ['Document', 'Batch', 'Cascade', 'Compare']

export default function App() {
  const [activeTab, setActiveTab] = useState<ViewTab>('Document')

  return (
    <div
      className="flex flex-col"
      style={{ backgroundColor: NVIS.bg, color: 'white', height: '100vh', overflow: 'hidden' }}
    >
      {/* Header bar */}
      <header
        className="flex items-center gap-3 px-4 shrink-0"
        style={{
          height: 48,
          borderBottom: `1px solid ${NVIS.border}`,
          backgroundColor: NVIS.bg,
        }}
      >
        {/* Logo */}
        <EmbryTopbarLogo size={28} nvis={false} state="idle" distance="close" />

        {/* Title */}
        <span
          className="text-sm font-semibold tracking-wide"
          style={{ color: NVIS.accent }}
        >
          /extract-pdf
        </span>

        {/* Divider */}
        <div
          className="shrink-0"
          style={{
            width: 1,
            height: 20,
            backgroundColor: NVIS.border,
            marginLeft: 4,
            marginRight: 4,
          }}
        />

        {/* View tabs */}
        <nav className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              aria-current={activeTab === tab ? 'page' : undefined}
              className="px-3 py-1 rounded text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[#4a9eff] focus:ring-offset-1 focus:ring-offset-[#141414]"
              style={{
                color: activeTab === tab ? NVIS.accent : 'rgba(255,255,255,0.65)',
                backgroundColor:
                  activeTab === tab ? 'rgba(74,158,255,0.10)' : 'transparent',
                border:
                  activeTab === tab
                    ? `1px solid rgba(74,158,255,0.25)`
                    : '1px solid transparent',
                cursor: 'pointer',
              }}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      {/* 3-pane layout */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'Document' && <DocumentView />}
        {activeTab === 'Batch' && <BatchView />}
        {activeTab === 'Cascade' && <CascadeView />}
        {activeTab === 'Compare' && <CompareView />}
      </div>
    </div>
  )
}
