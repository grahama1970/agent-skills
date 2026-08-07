/**
 * ResearchPane, extracted from DreamWorkspace.tsx.
 */
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from '../lib/memory'
import { authorStyleGuide, groupResearchContext, personaText, personaThumbnailUrl, productionTechniquePackage, roleFitCandidates, rolePrompt } from '../lib/persona'
import { nvis } from '../styles'

export function ResearchPane({ research, ideaSeed }: { research: ResearchMemoryResult[]; ideaSeed: string }) {
  const groupedResearch = groupResearchContext(research)
  return (
    <aside data-qid="research-pane" style={nvis.researchPane}>
      <div style={nvis.researchPaneHeader}>
        <h4 style={nvis.researchPaneTitle}>Research Context</h4>
        <span style={nvis.researchPaneBadge}>Brave Search</span>
      </div>
      <div style={{ color: '#64748b', fontSize: 10, letterSpacing: '0.04em', marginBottom: 12 }}>
        Seed: <span style={{ color: '#e2e8f0' }}>"{ideaSeed.slice(0, 60)}{ideaSeed.length > 60 ? '...' : ''}"</span>
      </div>
      <div style={nvis.researchList}>
        {groupedResearch.map((group) => (
          <details key={group.label} style={nvis.researchAccordion}>
            <summary style={nvis.researchAccordionSummary}>
              <span>{group.label} ({group.items.length})</span>
            </summary>
            <div style={nvis.researchAccordionContent}>
              {group.items.map((r, itemIndex) => (
                <div key={`${r.url ?? r.memoryKey ?? group.label}-${itemIndex}`} style={nvis.researchCard}>
                  <a href={r.url} target="_blank" rel="noreferrer" style={nvis.researchLink}>{readableMemoryText(r.title || r.memoryKey || 'Memory residue')}</a>
                  <p style={nvis.researchSnippet}>{readableMemoryText(r.snippet || r.title || '')}</p>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    </aside>
  )
}
