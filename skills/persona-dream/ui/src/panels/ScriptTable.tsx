/**
 * ScriptTable, extracted from DreamWorkspace.tsx.
 */
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import { coverageNoteForScriptRow, distinctAssetDescription, hasLiveDescriptionReceipt, scriptContractFromDraft, scriptCoverageStatusForRow, scriptCoverageStatusTitle, scriptEntityRows, scriptGlossaryFromContract, scriptStringFromContract, splitScriptIntoRows, storyAssetDescriptionFromMemoryDocument, storyAssetDescriptionFromResult } from '../lib/script'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from '../lib/story'
import { nvis } from '../styles'
import { ScriptCoverageTable } from './ScriptCoverageTable'

export function ScriptTable({
  draft,
  storyContract,
  durationSeconds,
}: {
  draft: string
  storyContract: ReturnType<typeof storyContractSummaryFromDraft>
  durationSeconds: number
}) {
  const contract = scriptContractFromDraft(draft)
  const script = scriptStringFromContract(contract, draft)
  const rows = splitScriptIntoRows(script)
  const coverageRows = scriptEntityRows(contract, storyContract)
  const glossary = scriptGlossaryFromContract(contract, storyContract)

  if (!script) {
    return <span style={nvis.directorStoryPlaceholder}>Generate the Phase 06 screenplay script here.</span>
  }

  const rowDuration = rows.length > 0 ? durationSeconds / rows.length : durationSeconds
  const durationLabel = (index: number) => {
    const start = index * rowDuration
    const end = Math.min(durationSeconds, (index + 1) * rowDuration)
    return `${start.toFixed(1)}-${end.toFixed(1)}s`
  }

  return (
    <div data-qid="dream:script:structured-table" style={nvis.scriptTableShell}>
      {rows.map((row, index) => {
        const status = scriptCoverageStatusForRow(index, coverageRows)
        const statusStyle = status === 'verified'
          ? nvis.scriptStatusNodeVerified
          : status === 'failed'
            ? nvis.scriptStatusNodeFailed
            : nvis.scriptStatusNodePending
        return (
          <div
            key={`${row.element}-${index}`}
            style={{
              ...nvis.scriptTableRow,
              ...(status === 'failed' ? nvis.scriptTableRowFailed : null),
            }}
          >
            <span
              data-qid={`dream:script:status-node:${index}`}
              data-status={status}
              title={scriptCoverageStatusTitle(status, index, coverageRows)}
              style={{ ...nvis.scriptStatusNodeBase, ...statusStyle }}
            />
            <div style={nvis.scriptBeatHeader}>
              <span style={nvis.scriptElementTag}>{row.element}</span>
              <span style={nvis.scriptDurationTag}>{durationLabel(index)}</span>
            </div>
            <div style={nvis.scriptContentBlock}>{highlightWithGlossary(row.content, glossary)}</div>
            <div style={nvis.scriptNotesCell}>{coverageNoteForScriptRow(index, coverageRows)}</div>
          </div>
        )
      })}
      <ScriptCoverageTable rows={coverageRows} />
    </div>
  )
}
