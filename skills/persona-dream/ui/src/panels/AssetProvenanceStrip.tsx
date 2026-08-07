/**
 * AssetProvenanceStrip, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { useRegisterAction } from '../useRegisterAction'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { coverageNoteForScriptRow, distinctAssetDescription, hasLiveDescriptionReceipt, scriptContractFromDraft, scriptCoverageStatusForRow, scriptCoverageStatusTitle, scriptEntityRows, scriptGlossaryFromContract, scriptStringFromContract, splitScriptIntoRows, storyAssetDescriptionFromMemoryDocument, storyAssetDescriptionFromResult } from '../lib/script'
import { nvis } from '../styles'
import { AssetProvenancePreview } from './AssetProvenancePreview'
import { Images } from 'lucide-react'

export function AssetProvenanceStrip({ assets }: { assets: LinkedStoryAsset[] }) {
  useRegisterAction('dream:story:asset-preview', {
    app: 'ux-lab',
    action: 'DREAM_STORY_ASSET_PREVIEW',
    label: 'Preview linked visual asset',
    description: 'Open the linked visual asset that grounds a Phase 02 story beat',
  })

  return (
    <section data-qid="dream:story:asset-provenance" style={nvis.assetStrip}>
      <h3 style={nvis.assetStripTitle}><Images size={12} /> Linked Visual Assets</h3>
      {assets.length === 0 ? (
        <div style={nvis.assetStripEmpty}>No linked visual assets yet. Recalled media from Phase 01 appears here after memory extraction.</div>
      ) : (
        <table style={nvis.assetTable}>
          <thead>
            <tr style={nvis.assetTableHeaderRow}>
              <th style={nvis.assetTableTh}>Image</th>
              <th style={nvis.assetTableTh}>Description</th>
              <th style={nvis.assetTableTh}>Source</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => {
              const description = distinctAssetDescription(asset)
              return <tr key={asset.id} style={nvis.assetTableRow}>
                <td style={nvis.assetTableThumbCell}>
                  <button
                    type="button"
                    data-qid={`dream:story:asset:${asset.id}`}
                    data-qs-action="DREAM_STORY_ASSET_PREVIEW"
                    title={`Preview linked asset: ${asset.title}`}
                    onClick={() => window.open(asset.url, '_blank', 'noopener,noreferrer')}
                    style={nvis.assetThumbButton}
                  >
                    <AssetProvenancePreview asset={asset} />
                  </button>
                </td>
                <td style={nvis.assetTableDescription}>
                  <span style={nvis.assetTableTitle}>{asset.title}</span>
                  {description && <span style={nvis.assetTableCaption}>{description}</span>}
                </td>
                <td style={nvis.assetTableSource}>{asset.memoryKey || asset.source || asset.id}</td>
              </tr>
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
