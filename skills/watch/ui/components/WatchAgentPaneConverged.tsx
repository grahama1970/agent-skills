import React, { ReactNode } from 'react'
import SharedChatShell from '../shared-chat/SharedChatShell'
import type { WatchChatAdapterOptions, WatchSceneRow } from '../shared-chat/memory-turn'

export interface WatchAgentPaneConvergedProps {
  reportPath: string
  answerModel: string
  sceneContext?: WatchChatAdapterOptions['sceneContext']
  onMatchedRows?: (rows: WatchSceneRow[]) => void
  onAnnotationTab?: () => void
  greeting?: string
  sceneChrome?: ReactNode
  modelChrome?: ReactNode
}

export function WatchAgentPaneConverged({
  reportPath,
  answerModel,
  sceneContext,
  onMatchedRows,
  onAnnotationTab,
  greeting = 'Hello, Graham',
  sceneChrome,
  modelChrome,
}: WatchAgentPaneConvergedProps): JSX.Element {
  return (
    <section data-qid="watch:chat:shell-wrap" style={{ height: '100%', minHeight: 0, display: 'grid', gridTemplateRows: 'auto 1fr', gap: 12 }}>
      <div data-qid="watch:chat:chrome" style={{ display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <div style={{ color: '#eef5ff', fontWeight: 760 }}>{greeting}</div>
            <div style={{ color: '#8e9aab', fontSize: 12, marginTop: 2 }}>Ask about the selected report or scene context.</div>
          </div>
          {modelChrome}
        </div>
        {sceneChrome}
      </div>

      <SharedChatShell
        surface="watch"
        shellQid="watch:chat:shell"
        hideHeader
        showModeToggle={false}
        defaultMode="compliance"
        adapterOptions={{
          watch: {
            projectLabel: 'Watch',
            reportPath,
            answerModel,
            sceneContext,
            onMatchedRows,
            onAnnotationTab,
          },
        }}
        emptyTitle={greeting}
        emptyDescription="Ask about the current film report, matched rows, or selected timecode."
        placeholder="Ask Watch about this report…"
        starterChips={[
          { label: 'What happened here?', prompt: 'What happened in the selected scene?', dataQid: 'watch:chat:chip:what-happened' },
          { label: 'Find similar beats', prompt: 'Find similar emotional beats in this report', dataQid: 'watch:chat:chip:similar' },
          { label: 'Explain the evidence', prompt: 'Explain the evidence behind the current annotation', dataQid: 'watch:chat:chip:evidence' },
        ]}
      />
    </section>
  )
}

export default WatchAgentPaneConverged
