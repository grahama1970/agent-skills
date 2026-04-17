import { useState, useEffect } from 'react'
import { NVIS } from './theme'
import SupervisorView from './views/SupervisorView'
import CorpusView from './views/CorpusView'
import QuarantineView from './views/QuarantineView'
import ProvidersView from './views/ProvidersView'
import CascadeView from './views/CascadeView'
import QualityView from './views/QualityView'
import RequirementsView from './views/RequirementsView'
import ThreatMatrixView from './views/ThreatMatrixView'
import LemmaGraphView from './views/LemmaGraphView'
import MonitorView from './views/MonitorView'
import MonitorStrip from './components/MonitorStrip'
import ChatFAB from './components/ChatFAB'

type Tab = 'Supervisor' | 'Corpus' | 'Quarantine' | 'Providers' | 'Cascade' | 'Quality' | 'Requirements' | 'Threats' | 'Lemmas' | 'Monitor'

const TABS: Tab[] = ['Supervisor', 'Corpus', 'Quarantine', 'Providers', 'Cascade', 'Quality', 'Requirements', 'Threats', 'Lemmas', 'Monitor']

function getTabFromHash(): Tab {
  const hash = window.location.hash.replace('#', '').toLowerCase()
  const match = TABS.find((t) => t.toLowerCase() === hash)
  return match ?? 'Supervisor'
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>(getTabFromHash)

  useEffect(() => {
    const onHashChange = () => setActiveTab(getTabFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const switchTab = (tab: Tab) => {
    window.location.hash = tab.toLowerCase()
    setActiveTab(tab)
  }

  // Navigate from MonitorStrip event source click
  const handleMonitorNavigate = (source: string) => {
    // Map source names to tabs where possible
    if (source.includes('skill')) switchTab('Supervisor')
    else if (source.includes('cascade') || source.includes('drift')) switchTab('Cascade')
    else if (source.includes('quality')) switchTab('Quality')
    else if (source.includes('threat') || source.includes('sparta')) switchTab('Threats')
    else if (source.includes('lemma') || source.includes('proof')) switchTab('Lemmas')
    else if (source.includes('monitor') || source.includes('workstation') || source.includes('codebase')) switchTab('Monitor')
  }

  return (
    <div style={{
      backgroundColor: NVIS.bg, color: NVIS.white,
      height: '100vh', display: 'flex', flexDirection: 'column',
      fontFamily: 'monospace', overflow: 'hidden',
    }}>
      {/* Global focus-visible style */}
      <style>{`
        button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible,
        [role="tab"]:focus-visible, [role="treeitem"]:focus-visible, [role="option"]:focus-visible,
        [role="radio"]:focus-visible, [tabindex]:focus-visible {
          outline: 2px solid ${NVIS.accent};
          outline-offset: 2px;
        }
        *::-webkit-scrollbar { width: 4px; height: 4px; }
        *::-webkit-scrollbar-thumb { background: ${NVIS.borderSolid}; border-radius: 2px; }
        *::-webkit-scrollbar-track { background: transparent; }
      `}</style>

      {/* Tab bar */}
      <nav aria-label="Main navigation" style={{ flexShrink: 0 }}>
        <div
          role="tablist"
          aria-label="Datalake views"
          style={{ backgroundColor: NVIS.surface, borderBottom: `1px solid ${NVIS.borderSolid}`, display: 'flex', gap: 0 }}
        >
          <span style={{ padding: '10px 16px', fontSize: 13, fontWeight: 700, color: NVIS.accent, letterSpacing: 1, flexShrink: 0 }}>
            DATALAKE
          </span>
          {TABS.map((tab) => {
            const isActive = tab === activeTab
            return (
              <button
                key={tab}
                role="tab"
                aria-selected={isActive}
                aria-controls={`tabpanel-${tab.toLowerCase()}`}
                id={`tab-${tab.toLowerCase()}`}
                onClick={() => switchTab(tab)}
                style={{
                  padding: '10px 20px',
                  background: 'none',
                  border: 'none',
                  borderBottom: isActive ? `2px solid ${NVIS.accent}` : '2px solid transparent',
                  color: isActive ? NVIS.accent : NVIS.dim,
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontFamily: 'monospace',
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {tab}
              </button>
            )
          })}
        </div>
      </nav>

      {/* Tab content — grows to fill space between tab bar and monitor strip */}
      <main
        role="tabpanel"
        id={`tabpanel-${activeTab.toLowerCase()}`}
        aria-labelledby={`tab-${activeTab.toLowerCase()}`}
        style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}
      >
        {activeTab !== 'Requirements' && activeTab !== 'Threats' && activeTab !== 'Lemmas' && activeTab !== 'Monitor' && (
          <div style={{ padding: '24px' }}>
            {activeTab === 'Supervisor' && <SupervisorView />}
            {activeTab === 'Corpus' && <CorpusView />}
            {activeTab === 'Quarantine' && <QuarantineView />}
            {activeTab === 'Providers' && <ProvidersView />}
            {activeTab === 'Cascade' && <CascadeView />}
            {activeTab === 'Quality' && <QualityView />}
          </div>
        )}
        {activeTab === 'Requirements' && <RequirementsView />}
        {activeTab === 'Threats' && <ThreatMatrixView />}
        {activeTab === 'Lemmas' && <LemmaGraphView />}
        {activeTab === 'Monitor' && <MonitorView />}
      </main>

      {/* Monitor strip — anchored at bottom of the viewport column */}
      <MonitorStrip onNavigate={handleMonitorNavigate} />

      {/* Chat FAB — fixed overlay above monitor strip */}
      <ChatFAB
        currentView={activeTab}
        selectedDocId={undefined}
        selectedSection={undefined}
      />
    </div>
  )
}
