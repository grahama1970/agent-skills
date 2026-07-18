import { useState, useEffect, useMemo, useCallback } from 'react'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, FileText, Eye, Pencil, Save, RotateCcw, Trash2, Focus, PanelRightOpen, Navigation } from 'lucide-react'
import PdfCanvas from '../datalake-explorer/PdfCanvas'
import type { BboxBlock } from '../datalake-explorer/types'
import { BLOCK_TYPE_COLORS, BLOCK_TYPE_LABELS } from '../datalake-explorer/BboxWorkspace'
import BboxEditor from '../datalake-explorer/BboxEditor'
import { LeftPane, LeftPaneSection, useLeftPaneSearch } from '../common/LeftPane'
import { ContextMenu, type ContextMenuItem } from '../common/ContextMenu'
import { SharedRightPane } from '../common/SharedRightPane'
import { EMBRY } from '../common/EmbryStyle'
import { ReviewBundleButton } from '../common/ReviewBundleButton'
import { SurgicalTriageFixture } from './SurgicalTriageFixture'
import { TauLoopView } from './TauLoopView'
import { SurgicalTriageCleanRoom } from './SurgicalTriageCleanRoom'
import { SurgicalTriageStaticProof } from './SurgicalTriageStaticProof'
import { PdfLabProductionWorkflow } from './PdfLabProductionWorkflow'
import { PdfLabEvidenceQA } from './PdfLabEvidenceQA'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import './PdfLabView.css'

interface PdfLabViewProps {
  pdfUrl?: string
  extractionUrl?: string
  initialSubpath?: string
}

interface ExtractionData {
  pdfUrl: string
  pageCount: number
  blocks: BboxBlock[]
  reviewMode?: 'raw' | 'reviewed'
  reviewSummary?: {
    reviewedPageCount: number
    totalPages: number
    totalFindings: number
    verdictCounts: {
      accept: number
      needs_human_review: number
    }
    pages: Array<{
      page: number
      pageNumber: number
      verdict: 'accept' | 'needs_human_review' | 'unreviewed'
      totalFindings: number
      missedRegions: number
    }>
  } | null
  humanEdits?: {
    updatedAt: string
    updatedBlocks: number
    deletedBlocks: number
    editCount: number
  } | null
}

interface PdfLabWorkflowPhase {
  id: string
  label: string
  status: 'complete' | 'passed' | 'ready' | 'empty' | 'artifact_gap' | string
  summary: string
  details?: Record<string, unknown>
}

interface PdfLabWorkflowCandidatePage {
  page: number
  element_count: number
  element_types: Record<string, number>
  task_count: number
  task_kinds: Record<string, number>
  severity: string
  gate_status: 'pass' | 'review' | string
  inferred_match_score?: number | null
  source: string
}

interface PdfLabWorkflowManifest {
  schema_version: string
  source_pdf: string
  document_family_preset: string
  page_count: number
  phases: PdfLabWorkflowPhase[]
  element_summary: {
    total_elements: number
    types: Record<string, number>
    high_signal_pages: Array<{ page: number; element_count: number; types: Record<string, number> }>
  }
  candidate_inventory: {
    candidate_page_count: number
    candidate_pages: PdfLabWorkflowCandidatePage[]
    source: string
  }
  gate: PdfLabWorkflowPhase
  human_triage: {
    task_count: number
    summary: {
      tasks_by_kind?: Record<string, number>
      tasks_by_severity?: Record<string, number>
      pages_with_tasks?: number
    }
    page_groups: Array<{ page: number; task_count: number; tasks: string[] }>
  }
  artifact_gaps: Array<{ status: string; missing_field: string; reason: string }>
  evidence_elements_by_page?: Record<string, PdfLabFullExtractionElement[]>
}

interface PdfLabFullExtractionElement {
  id: string
  page: number
  type: string
  bbox: [number, number, number, number]
  text?: string
  confidence?: number
  source?: string
  raw?: Record<string, unknown>
  preset_applied?: string
}

interface PdfLabFullExtraction {
  schema_version: string
  source_pdf: string
  page_count: number
  document_family_preset: string
  elements: PdfLabFullExtractionElement[]
}

interface PdfLabHumanTriageTask {
  task_id: string
  page: number
  kind: string
  severity: string
  target_id: string
  target_bbox?: [number, number, number, number]
  human_question: string
  agent_reasoning: string
  preview?: {
    type?: string
    text?: string
  }
  suggested_fix?: {
    action?: string
    fallback_actions?: string[]
  }
  proposed_json_delta?: Record<string, unknown>
}

interface PdfLabHumanTriageQueue {
  schema_version: string
  source_pdf: string
  page_count: number
  task_count: number
  summary: PdfLabWorkflowManifest['human_triage']['summary']
  page_groups: PdfLabWorkflowManifest['human_triage']['page_groups']
  human_triage_queue: PdfLabHumanTriageTask[]
}

interface PdfFile {
  id: string
  name: string
  pdfUrl: string
  extractionUrl: string
}

interface ReviewQueuePage {
  page: number
  count: number
  tasks: PdfLabTask[]
}

interface VerificationToast {
  action: string
  block: BboxBlock
  previousActiveTaskBlockId: string | null
  previousSelectedBlockId: string | null
}

type PdfLabTaskKind =
  | 'missing_object'
  | 'existing_object'
  | 'bbox_uncertain'
  | 'type_uncertain'
  | 'table_uncertain'
  | 'false_positive'

type PdfLabTaskActionType =
  | 'ADD'
  | 'VERIFY'
  | 'IGNORE'
  | 'DELETE'
  | 'KEEP'
  | 'RECLASSIFY'
  | 'FIX_BBOX'
  | 'CONFIRM_FIX'
  | 'PREVIEW_GRID'

interface PdfLabTaskAction {
  label: string
  type: PdfLabTaskActionType
}

interface PdfLabTask {
  id: string
  block: BboxBlock
  kind: PdfLabTaskKind
  humanQuestion: string
  calloutLabel: string
  inspectorSummary: string
  primaryAction: PdfLabTaskAction
  secondaryActions: PdfLabTaskAction[]
}

type PdfLabQueueMode = 'calibration' | 'review'

interface PdfLabQueueModeInfo {
  mode: PdfLabQueueMode
  title: string
  progressTitle: string
  pageSectionTitle: string
  controlTitle: string
  activeQuestionLabel: string
  currentPageTitle: string
  unresolvedLabel: string
  description: string
}

interface TableRegionReextractResult {
  ok: boolean
  flavor_used: string
  bbox_norm_tlbr: [number, number, number, number]
  rows: number
  cols: number
  accuracy: number
  whitespace: number
  text: string
  data: string[][]
  error?: string
}

// Available PDF files for testing
const PDF_FILES: PdfFile[] = [
  { id: 'nist-sp-800-53r5-429-463-final', name: 'NIST SP 800-53 Rev 5 Pages 429-463 (Final VLM Reviewed)', pdfUrl: '/nist-sp-800-53r5-429-463.pdf', extractionUrl: '/nist-sp-800-53r5-429-463-final-extraction.json' },
  { id: 'nist-sp-800-53r5-429-463-reviewed', name: 'NIST SP 800-53 Rev 5 Pages 429-463 (Reviewed v2)', pdfUrl: '/nist-sp-800-53r5-429-463.pdf', extractionUrl: '/nist-sp-800-53r5-429-463-reviewed-extraction.json' },
  { id: 'nist-sp-800-53r5-429-463-raw', name: 'NIST SP 800-53 Rev 5 Pages 429-463 (Raw v2)', pdfUrl: '/nist-sp-800-53r5-429-463.pdf', extractionUrl: '/nist-sp-800-53r5-429-463-raw-extraction.json' },
  { id: 'nist-like-full-page-reviewed', name: 'NIST-like Full Page (Reviewed v2)', pdfUrl: '/nist_like_full_page.pdf', extractionUrl: '/nist-like-full-page-reviewed-extraction.json' },
  { id: 'nist-like-full-page-raw', name: 'NIST-like Full Page (Raw v2)', pdfUrl: '/nist_like_full_page.pdf', extractionUrl: '/nist-like-full-page-raw-extraction.json' },
  { id: 'nist-v6-loop', name: 'NIST v6 Loop Output (49 pages)', pdfUrl: '/artifacts/pdf-lab/NIST_SP_800-53r5.pdf', extractionUrl: '/nist-v6-loop-extraction.json' },
  { id: 'nist-800-53', name: 'NIST SP 800-53 Rev 5 (Real)', pdfUrl: '/artifacts/pdf-lab/NIST_SP_800-53r5.pdf', extractionUrl: '/nist-800-53-extraction.json' },
  { id: 'nist-real', name: 'NIST Clone (Real Sections)', pdfUrl: '/nist_clone_real.pdf', extractionUrl: '/nist-real-extraction.json' },
  { id: 'nist-full', name: 'NIST Clone (Full)', pdfUrl: '/nist_clone_full.pdf', extractionUrl: '/nist-clone-extraction.json' },
  { id: 'test-clone', name: 'Test Clone', pdfUrl: '/test-clone.pdf', extractionUrl: '/test-clone-extraction.json' },
]

const EDITABLE_BLOCK_TYPES: Array<BboxBlock['blockType']> = [
  'table',
  'header',
  'figure',
  'text',
  'equation',
  'list_item',
  'caption',
  'page_number',
  'boilerplate',
]

const PDF_LAB_WORKFLOW_DATA_VERSION = '20260426c'
const PDF_LAB_ARTIFACT_BASE_URL = '/artifacts/pdf-lab'
const PDF_LAB_WORKFLOW_MANIFEST_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-workflow-manifest.json?pdfLabWorkflow=${PDF_LAB_WORKFLOW_DATA_VERSION}`
const PDF_LAB_HUMAN_TRIAGE_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-human-triage-queue.json?pdfLabWorkflow=${PDF_LAB_WORKFLOW_DATA_VERSION}`
const PDF_LAB_REAL_NIST_PDF_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/NIST_SP_800-53r5.pdf`

type PdfLabProductionStage = 'initial-sweep' | 'parity-audit' | 'surgical-triage' | 'evidence-qa' | 'coverage' | 'labeling'

function resolveProductionStage(subpath: string | undefined): PdfLabProductionStage | undefined {
  const stage = subpath?.split('/')[0]
  if (stage === 'initial-sweep') return 'initial-sweep'
  if (stage === 'parity-audit') return 'parity-audit'
  if (stage === 'surgical-triage' || stage === 'triage') return 'surgical-triage'
  if (stage === 'evidence-qa' || stage === 'nico-qa') return 'evidence-qa'
  if (stage === 'coverage' || stage === 'status') return 'coverage'
  if (stage === 'labeling' || stage === 'annotate') return 'labeling'
  return undefined
}

async function fetchPdfLabJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed ${url}: ${response.status}`)
  }
  const text = await response.text()
  try {
    return JSON.parse(text) as T
  } catch (error) {
    const snippet = text.trim().slice(0, 80).replace(/\s+/g, ' ')
    throw new Error(`Failed JSON parse for ${url}: ${snippet}`)
  }
}

function getQueueModeInfo(mode: PdfLabQueueMode): PdfLabQueueModeInfo {
  if (mode === 'calibration') {
    return {
      mode,
      title: 'Calibration Queue',
      progressTitle: 'Calibration progress',
      pageSectionTitle: 'Clarification pages',
      controlTitle: 'Calibration control center',
      activeQuestionLabel: 'Clarification for human',
      currentPageTitle: 'Current page clarifications',
      unresolvedLabel: 'signals',
      description: 'High-volume items are extractor calibration signals. Answer the active question; repeated patterns should become preset fixes, not reviewer toil.',
    }
  }

  return {
    mode,
    title: 'Verification Queue',
    progressTitle: 'Verification progress',
    pageSectionTitle: 'Agent-selected pages',
    controlTitle: 'Review control center',
    activeQuestionLabel: 'Human question',
    currentPageTitle: 'Current page queue',
    unresolvedLabel: 'unresolved',
    description: 'Production review should show only high-value human decisions after calibration has reduced systematic extraction errors.',
  }
}

function PdfLeftPane({
  selectedFile,
  queuePages,
  currentPage,
  progressLabel,
  progressPercent,
  queueModeInfo,
  onSelectFile,
  onSelectTask,
  onTeleportNext,
}: {
  selectedFile: PdfFile
  queuePages: ReviewQueuePage[]
  currentPage: number
  progressLabel: string
  progressPercent: number
  queueModeInfo: PdfLabQueueModeInfo
  onSelectFile: (file: PdfFile) => void
  onSelectTask: (block: BboxBlock) => void
  onTeleportNext: () => void
}) {
  const search = useLeftPaneSearch().toLowerCase()
  const filteredQueuePages = queuePages.filter(({ page, tasks }) => (
    !search ||
    `page ${page + 1}`.includes(search) ||
    tasks.some(task => `${task.calloutLabel} ${task.humanQuestion}`.toLowerCase().includes(search))
  ))

  return (
    <LeftPane title={queueModeInfo.title} searchable searchTestId="pdf-lab:search" width={260}>
      <LeftPaneSection title={queueModeInfo.progressTitle}>
        <div style={burndownCardStyle}>
          <div style={burndownTrackStyle}>
            <div style={{ ...burndownFillStyle, width: `${progressPercent}%` }} />
          </div>
          <div style={burndownLabelStyle}>{progressLabel}</div>
          <div data-qid="pdf-lab:queue:mode-notice" style={queueModeNoticeStyle}>
            <span style={{
              ...queueModeBadgeStyle,
              color: queueModeInfo.mode === 'calibration' ? EMBRY.amber : EMBRY.green,
              borderColor: queueModeInfo.mode === 'calibration' ? `${EMBRY.amber}88` : `${EMBRY.green}88`,
            }}>
              {queueModeInfo.mode === 'calibration' ? 'Calibration' : 'Review'}
            </span>
            <span style={{ color: EMBRY.dim }}>{queueModeInfo.description}</span>
          </div>
          <button
            className="pdf-lab-btn"
            data-qid="pdf-lab:queue:teleport-next"
            data-qs-action="PDF_LAB_TELEPORT_NEXT_FLAG"
            title="Teleport to the next unresolved agent task"
            onClick={onTeleportNext}
            style={teleportButtonStyle}
          >
            Teleport to Next Flag
          </button>
        </div>
      </LeftPaneSection>

      <LeftPaneSection title={`${queueModeInfo.pageSectionTitle} (${filteredQueuePages.length})`}>
        {filteredQueuePages.length > 0 ? filteredQueuePages.map(({ page, tasks }) => (
          <div key={page} style={queuePageGroupStyle}>
            <div style={queuePageHeaderStyle}>
              <span style={{ color: page === currentPage ? EMBRY.white : EMBRY.dim, fontWeight: 800 }}>
                Page {page + 1}
              </span>
              <span style={{ color: EMBRY.dim }}>{tasks.length} task{tasks.length === 1 ? '' : 's'}</span>
            </div>
            <div style={queueTaskListStyle}>
              {tasks.map(task => (
                <button
                  key={task.id}
                  data-qid={`pdf-lab:queue-task:${task.id}`}
                  data-qs-action="PDF_LAB_SELECT_QUEUE_TASK"
                  title={task.humanQuestion}
                  className="pdf-lab-btn"
                  onClick={() => onSelectTask(task.block)}
                  style={queueTaskButtonStyle}
                >
                  <span style={queueTaskDotStyle} />
                  <span style={{ minWidth: 0 }}>
                    <span style={queueTaskTitleStyle}>{task.calloutLabel}</span>
                    <span style={queueTaskSubtitleStyle}>{task.inspectorSummary}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        )) : (
          <div style={{ padding: '8px 16px', color: EMBRY.dim, fontSize: 11 }}>
            No unresolved tasks remain.
          </div>
        )}
      </LeftPaneSection>

      <LeftPaneSection title="Library">
        <details style={pdfDatasetDetailsStyle}>
          <summary
            data-qid="pdf-lab:dataset:switcher"
            data-qs-action="PDF_LAB_TOGGLE_DATASET_SWITCHER"
            title="Show available PDF Lab extractions"
            style={pdfDatasetSummaryToggleStyle}
          >
            Back to Library · {selectedFile.name}
          </summary>
          <div style={{ marginTop: 8 }}>
            {PDF_FILES.map(file => (
              <button
                key={file.id}
                data-qid={`pdf-lab:file:${file.id}`}
                data-qs-action="PDF_LAB_SELECT_DATASET"
                data-selected={file.id === selectedFile.id ? 'true' : 'false'}
                title={file.pdfUrl}
                className="pdf-lab-pane-item"
                onClick={() => onSelectFile(file)}
                style={{ minHeight: 44 }}
              >
                <FileText size={14} color={file.id === selectedFile.id ? EMBRY.accent : EMBRY.dim} />
                <span style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flex: 1,
                }}>
                  {file.name}
                </span>
              </button>
            ))}
          </div>
        </details>
      </LeftPaneSection>
    </LeftPane>
  )
}

function formatSemanticTypeLabel(semanticType?: string | null): string | null {
  if (!semanticType) return null
  if (semanticType === 'definition_list') return 'Definition List'
  if (semanticType === 'key_value_table') return 'Key/Value Table'
  return semanticType
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function getBlockDisplayLabel(block: Pick<BboxBlock, 'blockType' | 'semanticType'>): string {
  const semanticLabel = formatSemanticTypeLabel(block.semanticType)
  if (block.blockType === 'table' && semanticLabel && semanticLabel !== 'Table') return semanticLabel
  return BLOCK_TYPE_LABELS[block.blockType] || block.blockType
}

function getBlockSemanticSummary(block: Pick<BboxBlock, 'blockType' | 'semanticType'>): string {
  const semanticLabel = formatSemanticTypeLabel(block.semanticType)
  if (block.blockType === 'table' && semanticLabel === 'Definition List') return 'Two-column term/definition structure'
  if (semanticLabel) return semanticLabel
  return 'Needs review'
}

function isResolvedReviewBlock(block: BboxBlock): boolean {
  return block.reviewStatus === 'verified' || block.reviewStatus === 'rejected' || block.reviewStatus === 'ignored'
}

function humanizeMissedObjectType(block: BboxBlock): string {
  const missedType = block.id.startsWith('review:missed_')
    ? block.id.replace(/^review:missed_/, '').replace(/_\d+$/, '')
    : ''
  if (missedType.includes('header') || block.blockType === 'header') return 'Header'
  if (missedType.includes('boilerplate') || missedType.includes('footer') || block.blockType === 'boilerplate' || block.blockType === 'page_number') return 'Boilerplate'
  if (missedType.includes('definition_list') || block.semanticType === 'definition_list') return 'Definition List'
  if (missedType.includes('table') || block.blockType === 'table') return 'Table'
  if (missedType.includes('figure') || block.blockType === 'figure') return 'Figure'
  return getBlockDisplayLabel(block)
}

function buildPdfLabTask(block: BboxBlock, kind: PdfLabTaskKind, config: {
  humanQuestion: string
  calloutLabel: string
  inspectorSummary: string
  primaryAction: PdfLabTaskAction
  secondaryActions?: PdfLabTaskAction[]
}): PdfLabTask {
  return {
    id: block.id,
    block,
    kind,
    humanQuestion: config.humanQuestion,
    calloutLabel: config.calloutLabel,
    inspectorSummary: config.inspectorSummary,
    primaryAction: config.primaryAction,
    secondaryActions: config.secondaryActions ?? [],
  }
}

function getPdfLabTask(block: BboxBlock): PdfLabTask | null {
  if (isResolvedReviewBlock(block)) return null
  const notes = (block.reviewNotes || []).join(' ').toLowerCase()
  const semantic = (block.semanticType || '').toLowerCase()
  const label = getBlockDisplayLabel(block)

  if (block.id.startsWith('review:missed_')) {
    const objectLabel = humanizeMissedObjectType(block)
    const lowerLabel = objectLabel.toLowerCase()
    return buildPdfLabTask(block, 'missing_object', {
      humanQuestion: `Should this missing ${lowerLabel} be added?`,
      calloutLabel: `Add missing ${lowerLabel}`,
      inspectorSummary: `Agent detected a missing ${lowerLabel} in this region.`,
      primaryAction: { type: 'ADD', label: `Add ${objectLabel}` },
      secondaryActions: [{ type: 'IGNORE', label: 'Ignore' }],
    })
  }

  if (notes.includes('false positive')) {
    return buildPdfLabTask(block, 'false_positive', {
      humanQuestion: `Should this ${label.toLowerCase()} be deleted?`,
      calloutLabel: `Check false positive ${label.toLowerCase()}`,
      inspectorSummary: 'Agent thinks this extracted object is likely wrong.',
      primaryAction: { type: 'DELETE', label: 'Delete' },
      secondaryActions: [{ type: 'KEEP', label: 'Keep' }],
    })
  }

  if (block.blockType === 'table' || semantic.includes('definition_list') || semantic.includes('table')) {
    return buildPdfLabTask(block, 'table_uncertain', {
      humanQuestion: `Is this ${label.toLowerCase()} structure correct?`,
      calloutLabel: label === 'Definition List' ? 'Verify definition list' : 'Verify this table',
      inspectorSummary: 'Verify structure and bbox against the PDF. Cell edits belong in Audit Mode.',
      primaryAction: { type: 'VERIFY', label: label === 'Definition List' ? 'Verify Definition List' : 'Verify Table' },
      secondaryActions: [{ type: 'PREVIEW_GRID', label: 'Preview Grid' }, { type: 'FIX_BBOX', label: 'Fix Bbox' }],
    })
  }

  if (notes.includes('bbox should') || notes.includes('bbox includes')) {
    return buildPdfLabTask(block, 'bbox_uncertain', {
      humanQuestion: `Does this ${label.toLowerCase()} bbox capture the right region?`,
      calloutLabel: `Fix ${label.toLowerCase()} bbox`,
      inspectorSummary: 'Agent is uncertain about the region boundary.',
      primaryAction: { type: 'FIX_BBOX', label: 'Fix Bbox' },
      secondaryActions: [{ type: 'VERIFY', label: 'Accept Bbox' }],
    })
  }

  if (notes.includes('table header') || notes.includes('table column') || notes.includes('not a document title')) {
    return buildPdfLabTask(block, 'type_uncertain', {
      humanQuestion: `Is this ${label.toLowerCase()} classification correct?`,
      calloutLabel: `Check ${label.toLowerCase()} type`,
      inspectorSummary: 'Agent is uncertain about the semantic classification.',
      primaryAction: { type: 'VERIFY', label: 'Confirm Type' },
      secondaryActions: [{ type: 'RECLASSIFY', label: 'Reclassify' }],
    })
  }

  if (block.flagged || block.hasOpenComments || notes.includes('review status: confirm') || notes.includes('review status: refine')) {
    return buildPdfLabTask(block, 'existing_object', {
      humanQuestion: `Is this ${label.toLowerCase()} correct?`,
      calloutLabel: `Verify ${label.toLowerCase()}`,
      inspectorSummary: summarizeReviewNote(block),
      primaryAction: { type: 'VERIFY', label: 'Verify' },
      secondaryActions: [{ type: 'DELETE', label: 'Reject' }],
    })
  }

  return null
}

function getRuntimePdfLabTask(block: BboxBlock, isFixingBbox: boolean): PdfLabTask | null {
  const task = getPdfLabTask(block)
  if (!task || !isFixingBbox) return task
  return {
    ...task,
    humanQuestion: `Confirm the corrected bbox for this ${getBlockDisplayLabel(block).toLowerCase()}?`,
    calloutLabel: 'Confirm bbox fix',
    inspectorSummary: 'BBox was adjusted. Confirm the fix to resolve this task, or keep editing the region.',
    primaryAction: { type: 'CONFIRM_FIX', label: 'Confirm Fix' },
    secondaryActions: [{ type: 'FIX_BBOX', label: 'Keep Editing' }],
  }
}

function normalizeWorkflowBlockType(type: string | undefined): BboxBlock['blockType'] {
  const normalized = (type || '').toLowerCase()
  if (normalized.includes('table') || normalized.includes('definition')) return 'table'
  if (normalized.includes('header') || normalized.includes('title')) return 'header'
  if (normalized.includes('figure') || normalized.includes('image')) return 'figure'
  if (normalized.includes('equation')) return 'equation'
  if (normalized.includes('list')) return 'list_item'
  if (normalized.includes('caption')) return 'caption'
  if (normalized.includes('page_number')) return 'page_number'
  if (normalized.includes('boilerplate') || normalized.includes('footer')) return 'boilerplate'
  return 'text'
}

function workflowElementToBlock(element: PdfLabFullExtractionElement): BboxBlock {
  const blockType = normalizeWorkflowBlockType(element.type)
  return {
    id: element.id,
    page: Math.max(0, element.page - 1),
    bbox: element.bbox,
    blockType,
    semanticType: element.type,
    text: element.text || '',
    confidence: element.confidence ?? 1,
    reviewStatus: 'verified',
  }
}

function triageTaskToBlock(task: PdfLabHumanTriageTask): BboxBlock | null {
  if (!task.target_bbox) return null
  const previewType = task.preview?.type || task.kind
  return {
    id: task.target_id || task.task_id,
    page: Math.max(0, task.page - 1),
    bbox: task.target_bbox,
    blockType: normalizeWorkflowBlockType(previewType),
    semanticType: previewType,
    text: task.preview?.text || task.human_question,
    confidence: task.severity === 'high' ? 0.42 : 0.74,
    reviewNotes: [task.agent_reasoning],
    flagged: true,
    hasOpenComments: true,
    reviewStatus: 'active',
  }
}

function formatCount(value: number | undefined): string {
  return typeof value === 'number' ? value.toLocaleString() : '—'
}

export function PdfLabView({ pdfUrl: propPdfUrl, extractionUrl: propExtractionUrl, initialSubpath }: PdfLabViewProps) {
  useRegisterAction('pdf-lab:workflow:diagnostics', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_DIAGNOSTICS',
    label: 'Open workflow diagnostics',
    description: 'Open hidden extraction workflow diagnostics for the PDF Lab triage surface',
  })
  useRegisterAction('pdf-lab:workflow:audit-repair', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_AUDIT_REPAIR',
    label: 'Open audit repair',
    description: 'Leave surgical triage and open the detailed audit and repair surface',
  })
  useRegisterAction('pdf-lab:workflow:intent', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_INTENT',
    label: 'Enter intent correction',
    description: 'Type an intent-based correction for the active PDF ambiguity',
  })
  useRegisterAction('pdf-lab:workflow:accept', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_ACCEPT',
    label: 'Accept active card',
    description: 'Accept the active PDF Lab human triage card and advance to the next card',
  })
  useRegisterAction('pdf-lab:workflow:reject', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_REJECT',
    label: 'Reject active card',
    description: 'Reject the active PDF Lab human triage card and advance to the next card',
  })
  useRegisterAction('pdf-lab:workflow:skip', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_SKIP',
    label: 'Skip active card',
    description: 'Skip the active PDF Lab human triage card and advance to the next card',
  })
  useRegisterAction('pdf-lab:workflow:previous', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_PREVIOUS',
    label: 'Previous ambiguity card',
    description: 'Move to the previous PDF Lab ambiguity card',
  })
  useRegisterAction('pdf-lab:workflow:next', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_NEXT',
    label: 'Next ambiguity card',
    description: 'Move to the next PDF Lab ambiguity card',
  })
  useRegisterAction('pdf-lab:workflow:agent-read', {
    app: 'pdf-lab',
    action: 'PDF_LAB_WORKFLOW_AGENT_READ',
    label: 'Toggle agent read',
    description: 'Show or hide the compact extracted-text support line for the active card',
  })
  const resolveSelectedFile = useCallback((pdfUrl: string | null | undefined, extractionUrl: string | null | undefined): PdfFile => (
    PDF_FILES.find(
      f => f.pdfUrl === pdfUrl && (!extractionUrl || f.extractionUrl === extractionUrl)
    ) ||
    PDF_FILES.find(f => f.pdfUrl === pdfUrl) ||
    PDF_FILES[0]
  ), [])

  const [selectedFile, setSelectedFile] = useState<PdfFile>(() => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '')
    return resolveSelectedFile(propPdfUrl || params.get('pdf'), propExtractionUrl || params.get('extraction'))
  })
  const [extraction, setExtraction] = useState<ExtractionData | null>(null)
  const [baselineExtraction, setBaselineExtraction] = useState<ExtractionData | null>(null)
  const [rawCompareExtraction, setRawCompareExtraction] = useState<ExtractionData | null>(null)
  const [currentPage, setCurrentPage] = useState(0)
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null)
  const [activeTaskBlockId, setActiveTaskBlockId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(0.5)
  const [viewMode, setViewMode] = useState<'fit-page' | 'manual'>('fit-page')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveNotice, setSaveNotice] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [showRawCompare, setShowRawCompare] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reextractingArea, setReextractingArea] = useState(false)
  const [, setVerificationToast] = useState<VerificationToast | null>(null)
  const [dirtyBlockIds, setDirtyBlockIds] = useState<Set<string>>(new Set())
  const [deletedBlockIds, setDeletedBlockIds] = useState<Set<string>>(new Set())
  const [newBlockType, setNewBlockType] = useState<BboxBlock['blockType']>('text')
  const [selectionMode, setSelectionMode] = useState<'draw-block' | 'select-area'>('draw-block')
  const [selectedAreaBBox, setSelectedAreaBBox] = useState<[number, number, number, number] | null>(null)
  const [selectedAreaBlockIds, setSelectedAreaBlockIds] = useState<Set<string>>(new Set())
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set(['table', 'header', 'figure', 'text', 'caption', 'page_number', 'boilerplate']))
  const [contextMenu, setContextMenu] = useState<{ blockId: string; x: number; y: number } | null>(null)
  const [showAuditPane, setShowAuditPane] = useState(true)
  const [auditTab, setAuditTab] = useState<'selected' | 'queue' | 'filters'>('queue')
  const [showGhostQueueItems, setShowGhostQueueItems] = useState(false)
  const [reviewNavMode, setReviewNavMode] = useState(false)
  const [bboxFixTaskIds, setBboxFixTaskIds] = useState<Set<string>>(new Set())
  const [, setPreviewGridBlockId] = useState<string | null>(null)
  const [workflowShellEnabled, setWorkflowShellEnabled] = useState(initialSubpath === 'legacy-workflow')
  const [workflowStageId, setWorkflowStageId] = useState('agent_scan')
  const [workflowManifest, setWorkflowManifest] = useState<PdfLabWorkflowManifest | null>(null)
  const [workflowExtraction, setWorkflowExtraction] = useState<PdfLabFullExtraction | null>(null)
  const [workflowTriage, setWorkflowTriage] = useState<PdfLabHumanTriageQueue | null>(null)
  const [workflowLoading, setWorkflowLoading] = useState(true)
  const [workflowError, setWorkflowError] = useState<string | null>(null)
  const [workflowTaskIndex, setWorkflowTaskIndex] = useState(0)
  const [intentDraft, setIntentDraft] = useState('')

  useEffect(() => {
    let cancelled = false
    setWorkflowLoading(true)
    setWorkflowError(null)

    if (!workflowShellEnabled) {
      setWorkflowLoading(false)
      return () => { cancelled = true }
    }

    Promise.all([
      fetchPdfLabJson<PdfLabWorkflowManifest>(PDF_LAB_WORKFLOW_MANIFEST_URL),
      fetchPdfLabJson<PdfLabHumanTriageQueue>(PDF_LAB_HUMAN_TRIAGE_URL),
    ])
      .then(([manifest, triage]) => {
        if (cancelled) return
        const compactEvidence = Object.values(manifest.evidence_elements_by_page || {}).flat()
        const fullExtraction: PdfLabFullExtraction = {
          schema_version: 'pdf_lab_compact_evidence.v1',
          source_pdf: manifest.source_pdf,
          page_count: manifest.page_count,
          document_family_preset: manifest.document_family_preset,
          elements: compactEvidence,
        }
        setWorkflowManifest(manifest)
        setWorkflowExtraction(fullExtraction)
        setWorkflowTriage(triage)
        const firstTask = triage.human_triage_queue[0]
        if (firstTask) {
          setCurrentPage(Math.max(0, firstTask.page - 1))
          setWorkflowTaskIndex(0)
        }
        setWorkflowLoading(false)
      })
      .catch((err: Error) => {
        if (cancelled) return
        setWorkflowError(err.message)
        setWorkflowLoading(false)
      })

    return () => { cancelled = true }
  }, [workflowShellEnabled, PDF_LAB_WORKFLOW_DATA_VERSION])

  useEffect(() => {
    const syncSelectedFile = () => {
      const params = new URLSearchParams(window.location.hash.split('?')[1] || '')
      const nextFile = resolveSelectedFile(propPdfUrl || params.get('pdf'), propExtractionUrl || params.get('extraction'))
      setSelectedFile(prev => prev.id === nextFile.id ? prev : nextFile)
    }

    syncSelectedFile()
    window.addEventListener('hashchange', syncSelectedFile)
    return () => window.removeEventListener('hashchange', syncSelectedFile)
  }, [propExtractionUrl, propPdfUrl, resolveSelectedFile])

  const pdfUrl = selectedFile.pdfUrl
  const extractionUrl = selectedFile.extractionUrl

  // Load extraction data when file changes
  useEffect(() => {
    if (workflowShellEnabled) return
    setLoading(true)
    setError(null)
    setSaveError(null)
    setSaveNotice(null)
    setRawCompareExtraction(null)
    setCurrentPage(0)
    setSelectedBlockId(null)
    setActiveTaskBlockId(null)
    setEditMode(false)
    setShowRawCompare(false)
    setViewMode('fit-page')
    setSelectionMode('draw-block')
    setSelectedAreaBBox(null)
    setSelectedAreaBlockIds(new Set())
    setDirtyBlockIds(new Set())
    setDeletedBlockIds(new Set())
    setVerificationToast(null)
    setContextMenu(null)
    setReextractingArea(false)
    setShowAuditPane(true)
    setAuditTab('queue')
    setShowGhostQueueItems(false)
    setBboxFixTaskIds(new Set())
    setPreviewGridBlockId(null)

    fetch(extractionUrl)
      .then(r => {
        if (!r.ok) throw new Error(`Failed to load: ${r.status}`)
        return r.json()
      })
      .then((data: ExtractionData) => {
        const firstQueuedBlock = findFirstPdfLabTaskBlock(data)
        setExtraction(data)
        setBaselineExtraction(cloneExtractionData(data))
        setCurrentPage(firstQueuedBlock?.page ?? 0)
        setSelectedBlockId(firstQueuedBlock?.id ?? null)
        setActiveTaskBlockId(firstQueuedBlock?.id ?? null)
        setEditMode(data.reviewMode === 'reviewed' && !extractionUrl.includes('-raw-extraction.json'))
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [extractionUrl, workflowShellEnabled])

  // Auto-activate Review Mode on reviewed datasets
  useEffect(() => {
    if (extraction?.reviewMode === 'reviewed' && !extractionUrl.includes('-raw-extraction.json')) {
      setReviewNavMode(true)
    } else {
      setReviewNavMode(false)
    }
  }, [extraction?.reviewMode, extractionUrl])

  useEffect(() => {
    const compareFile = findRawCompareFile(selectedFile)
    if (!compareFile) {
      setRawCompareExtraction(null)
      return
    }

    let cancelled = false
    fetch(compareFile.extractionUrl)
      .then(r => {
        if (!r.ok) throw new Error(`Failed to load raw compare: ${r.status}`)
        return r.json()
      })
      .then((data: ExtractionData) => {
        if (!cancelled) setRawCompareExtraction(data)
      })
      .catch(() => {
        if (!cancelled) setRawCompareExtraction(null)
      })

    return () => { cancelled = true }
  }, [selectedFile])

  // Filter blocks for current page and selected types
  const visibleBlocks = extraction?.blocks.filter(
    b => b.page === currentPage && typeFilters.has(b.blockType) && b.reviewStatus !== 'rejected' && b.reviewStatus !== 'ignored'
  ) || []
  const rawCompareBlocks = useMemo(() => {
    if (!showRawCompare || !rawCompareExtraction || !extraction) return []
    return rawCompareExtraction.blocks.filter(block => {
      if (block.page !== currentPage || !typeFilters.has(block.blockType)) return false
      const reviewedBlock = extraction.blocks.find(candidate => candidate.id === block.id)
      if (!reviewedBlock) return true
      return reviewedBlock.blockType !== block.blockType || !sameBBox(reviewedBlock.bbox, block.bbox)
    })
  }, [showRawCompare, rawCompareExtraction, extraction, currentPage, typeFilters])

  const selectedBlock = extraction?.blocks.find(b => b.id === selectedBlockId)
  const contextMenuBlock = contextMenu ? extraction?.blocks.find(block => block.id === contextMenu.blockId) ?? null : null
  const currentPageReview = extraction?.reviewSummary?.pages.find(page => page.page === currentPage)
  const isReviewedView = extraction?.reviewMode === 'reviewed'
  const canEditExtraction = isReviewedView && !selectedFile.extractionUrl.includes('-raw-extraction.json')
  const dirtyCount = dirtyBlockIds.size + deletedBlockIds.size
  const displayTitle = splitDisplayName(selectedFile.name)
  const classifyReviewBand = useCallback((block: BboxBlock): 'low' | 'medium' | 'ghost' => {
    if (block.flagged || block.confidence < 0.6) return 'low'
    if (block.hasOpenComments || (block.reviewNotes && block.reviewNotes.length > 0) || block.confidence < 0.9) return 'medium'
    return 'ghost'
  }, [])
  const reviewTaskPriority = useCallback((block: BboxBlock): number => {
    const notes = (block.reviewNotes || []).join(' ').toLowerCase()
    const semantic = (block.semanticType || '').toLowerCase()

    if (block.id.startsWith('review:missed_table')) return 0
    if (block.id.startsWith('review:missed_figure') || block.id.startsWith('review:missed_equation')) return 1
    if (semantic === 'definition_list') return 2
    if (block.blockType === 'table') return 3
    if (block.id.startsWith('review:') && (semantic.includes('table') || notes.includes('table') || semantic.includes('definition'))) return 4
    if (block.blockType === 'header' || block.blockType === 'caption') return 5
    if (block.id.startsWith('review:')) return 6
    if (block.blockType === 'figure' || block.blockType === 'equation') return 7
    if (block.blockType === 'list_item') return 8
    if (block.blockType === 'page_number' || block.blockType === 'boilerplate') return 9
    if (block.blockType === 'text') return 10
    return 11
  }, [])
  const isUnresolvedBlock = useCallback((block: BboxBlock) => getPdfLabTask(block) !== null, [])
  const unresolvedBlocks = useMemo(() => {
    const all = extraction?.blocks.filter(isUnresolvedBlock) ?? []
    const weighted = [...all].sort((a, b) => {
      const bandWeight = { low: 0, medium: 1, ghost: 2 } as const
      const aBand = bandWeight[classifyReviewBand(a)]
      const bBand = bandWeight[classifyReviewBand(b)]
      if (aBand !== bBand) return aBand - bBand
      const aPriority = reviewTaskPriority(a)
      const bPriority = reviewTaskPriority(b)
      if (aPriority !== bPriority) return aPriority - bPriority
      if (a.page !== b.page) return a.page - b.page
      return a.id.localeCompare(b.id)
    })
    return showGhostQueueItems ? weighted : weighted.filter(block => classifyReviewBand(block) !== 'ghost')
  }, [classifyReviewBand, extraction, isUnresolvedBlock, reviewTaskPriority, showGhostQueueItems])
  const unresolvedBlocksOnCurrentPage = useMemo(
    () => unresolvedBlocks.filter(block => block.page === currentPage),
    [unresolvedBlocks, currentPage]
  )
	  const activeTaskBlock = useMemo(() => {
	    if (!extraction) return null
	    if (activeTaskBlockId) {
	      const direct = extraction.blocks.find(block => block.id === activeTaskBlockId)
	      if (direct && isUnresolvedBlock(direct)) return direct
	    }
	    return unresolvedBlocksOnCurrentPage[0] ?? unresolvedBlocks[0] ?? null
	  }, [activeTaskBlockId, extraction, isUnresolvedBlock, unresolvedBlocks, unresolvedBlocksOnCurrentPage])
  const activeTask = activeTaskBlock ? getRuntimePdfLabTask(activeTaskBlock, bboxFixTaskIds.has(activeTaskBlock.id)) : null
  const currentPageOtherTasks = useMemo(
    () => unresolvedBlocksOnCurrentPage.filter(block => block.id !== activeTaskBlock?.id),
    [activeTaskBlock?.id, unresolvedBlocksOnCurrentPage]
  )
  const selectedBlockIsUnresolved = useMemo(
    () => selectedBlock ? isUnresolvedBlock(selectedBlock) : false,
    [isUnresolvedBlock, selectedBlock]
  )
  const selectedBlockMatchesActiveTask = Boolean(selectedBlock && activeTaskBlock && selectedBlock.id === activeTaskBlock.id)
  const unresolvedPages = useMemo(() => {
    const counts = new Map<number, number>()
    for (const block of unresolvedBlocks) counts.set(block.page, (counts.get(block.page) ?? 0) + 1)
    return [...counts.entries()]
      .map(([page, count]) => ({ page, count }))
      .sort((a, b) => a.page - b.page)
  }, [unresolvedBlocks])
  const activeTaskIndexOnPage = activeTaskBlock ? unresolvedBlocksOnCurrentPage.findIndex(block => block.id === activeTaskBlock.id) : -1
  const pageFocusProgress = activeTaskIndexOnPage >= 0 && unresolvedBlocksOnCurrentPage.length > 0
    ? (activeTaskIndexOnPage + 1) / unresolvedBlocksOnCurrentPage.length
    : 0
  const upcomingUnresolvedPages = useMemo(
    () => unresolvedPages.filter(entry => entry.page !== currentPage),
    [currentPage, unresolvedPages]
  )
  const flaggedPageList = useMemo(() => {
    const pages = new Set(unresolvedBlocks.map(b => b.page))
    return [...pages].sort((a, b) => a - b)
  }, [unresolvedBlocks])
  const currentFlaggedIndex = flaggedPageList.indexOf(currentPage)
  const prevFlaggedPage = flaggedPageList[currentFlaggedIndex - 1] ?? null
  const nextFlaggedPage = flaggedPageList[currentFlaggedIndex + 1] ?? null
  const isOnFlaggedPage = currentFlaggedIndex >= 0
  const nextUnresolvedBlock = unresolvedBlocks.find(block => block.page > currentPage)
    ?? unresolvedBlocksOnCurrentPage.find(block => block.id !== activeTaskBlock?.id)
    ?? unresolvedBlocks[0]
  const totalReviewPages = extraction?.reviewSummary?.totalPages ?? extraction?.pageCount ?? 0
  const completedReviewPages = Math.max(0, totalReviewPages - unresolvedPages.length)
  const progressLabel = `Progress: ${completedReviewPages} / ${totalReviewPages} Pages`
  const progressPercent = Math.round((completedReviewPages / Math.max(1, totalReviewPages)) * 100)
  const queueMode: PdfLabQueueMode = unresolvedBlocks.length > Math.max(30, Math.ceil(totalReviewPages * 0.25))
    ? 'calibration'
    : 'review'
  const queueModeInfo = useMemo(() => getQueueModeInfo(queueMode), [queueMode])
  const reviewQueuePages = useMemo<ReviewQueuePage[]>(() => (
    unresolvedPages.map(({ page, count }) => ({
      page,
      count,
      tasks: unresolvedBlocks
        .filter(block => block.page === page)
        .map(block => getRuntimePdfLabTask(block, bboxFixTaskIds.has(block.id)))
        .filter((task): task is PdfLabTask => Boolean(task)),
    }))
  ), [bboxFixTaskIds, unresolvedBlocks, unresolvedPages])
  const agentNotes = useMemo(() => (
    unresolvedBlocksOnCurrentPage.slice(0, 8)
      .map(block => getRuntimePdfLabTask(block, bboxFixTaskIds.has(block.id)))
      .filter((task): task is PdfLabTask => Boolean(task))
      .map(task => ({
        id: task.id,
        blockId: task.block.id,
        bbox: task.block.bbox,
        title: task.calloutLabel,
        body: task.inspectorSummary,
        severity: task.kind === 'missing_object' || task.kind === 'false_positive' ? 'high' as const : 'medium' as const,
        primaryActionLabel: task.primaryAction.label,
        secondaryActionLabel: task.secondaryActions[0]?.label,
      }))
  ), [bboxFixTaskIds, unresolvedBlocksOnCurrentPage])

  const workflowTasks = workflowTriage?.human_triage_queue ?? []
  const activeWorkflowTask = workflowTasks[workflowTaskIndex] ?? null
  const activeWorkflowTaskBlock = activeWorkflowTask ? triageTaskToBlock(activeWorkflowTask) : null
  const workflowEvidencePage = activeWorkflowTask ? Math.max(0, activeWorkflowTask.page - 1) : currentPage
  const intentHint = intentDraft.trim().toLowerCase()
  const intentMode = intentHint.startsWith('t') || intentHint.includes('table')
    ? 'table'
    : intentHint.includes('up') || intentHint.includes('down') || intentHint.includes('bbox') || intentHint.includes('box')
      ? 'bbox'
      : intentHint.includes('skip')
        ? 'skip'
        : null
  const workflowPageElements = useMemo(() => {
    if (!workflowExtraction) return []
    return workflowExtraction.elements
      .filter(element => Math.max(0, element.page - 1) === workflowEvidencePage)
      .slice(0, 120)
      .map(workflowElementToBlock)
  }, [workflowEvidencePage, workflowExtraction])
  const workflowEvidenceLines = useMemo(() => {
    if (!activeWorkflowTaskBlock) return []
    const [x1, y1, x2, y2] = activeWorkflowTaskBlock.bbox
    return workflowPageElements
      .filter(block => {
        if (block.id === activeWorkflowTaskBlock.id) return false
        if (!block.text || block.text.trim().length < 8) return false
        if (block.blockType === 'page_number' || block.blockType === 'boilerplate') return false
        if (block.semanticType === 'running_header' || block.semanticType === 'running_footer') return false
        const [bx1, by1, bx2, by2] = block.bbox
        return bx2 >= x1 && bx1 <= x2 && by2 >= y1 && by1 <= y2
      })
      .sort((a, b) => a.bbox[1] - b.bbox[1])
      .slice(0, 9)
  }, [activeWorkflowTaskBlock, workflowPageElements])
  const workflowAttentionBBox = useMemo<[number, number, number, number] | null>(() => {
    if (!activeWorkflowTaskBlock) return null
    const [x1, y1, x2, y2] = activeWorkflowTaskBlock.bbox
    const width = x2 - x1
    const height = y2 - y1
    if (width <= 0.55 && width * height <= 0.28 && height <= 0.68) return activeWorkflowTaskBlock.bbox

    const visualWideCrop: [number, number, number, number] = [
      x1,
      y1,
      Math.min(1, x1 + width * 0.62),
      y2,
    ]

    const overlappingText = workflowEvidenceLines.slice(0, 8)
    if (overlappingText.length === 0) return visualWideCrop

    const focus = overlappingText.reduce<[number, number, number, number]>(
      (acc, block) => [
        Math.min(acc[0], block.bbox[0]),
        Math.min(acc[1], block.bbox[1]),
        Math.max(acc[2], block.bbox[2]),
        Math.max(acc[3], block.bbox[3]),
      ],
      [1, 1, 0, 0]
    )
    return [
      Math.max(0, focus[0] - 0.025),
      Math.max(0, focus[1] - 0.025),
      Math.min(visualWideCrop[2], focus[2] + 0.025),
      Math.min(1, focus[3] + 0.045),
    ]
  }, [activeWorkflowTaskBlock, workflowEvidenceLines])
  const workflowCanvasBlocks = useMemo(() => {
    const blocks = activeWorkflowTaskBlock
      ? [activeWorkflowTaskBlock, ...workflowPageElements.filter(block => block.id !== activeWorkflowTaskBlock.id)]
      : workflowPageElements
    return blocks.slice(0, 121)
  }, [activeWorkflowTaskBlock, workflowPageElements])
  const workflowAgentNotes = useMemo(() => (
    activeWorkflowTaskBlock && activeWorkflowTask
      ? [{
          id: activeWorkflowTask.task_id,
          blockId: undefined,
          bbox: activeWorkflowTaskBlock.bbox,
          title: 'Agent Doubts',
          body: activeWorkflowTask.agent_reasoning,
          severity: activeWorkflowTask.severity === 'high' ? 'high' as const : 'medium' as const,
          primaryActionLabel: 'Accept',
          secondaryActionLabel: 'Skip',
        }]
      : []
  ), [activeWorkflowTask, activeWorkflowTaskBlock])
  const selectedWorkflowStage = workflowManifest?.phases.find(phase => phase.id === workflowStageId) ?? workflowManifest?.phases[0] ?? null
  const topWorkflowCandidates = workflowManifest?.candidate_inventory.candidate_pages.slice(0, 8) ?? []

  const dirtyBlocks = useMemo(() => {
    if (!extraction) return []
    return extraction.blocks.filter(block => dirtyBlockIds.has(block.id))
  }, [dirtyBlockIds, extraction])

  const toggleTypeFilter = (type: string) => {
    setTypeFilters(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  useEffect(() => {
    if (selectedBlockId && extraction && !extraction.blocks.some(block => block.id === selectedBlockId)) {
      setSelectedBlockId(null)
    }
  }, [selectedBlockId, extraction])

  useEffect(() => {
    if (activeTaskBlockId && extraction && !extraction.blocks.some(block => block.id === activeTaskBlockId)) {
      setActiveTaskBlockId(null)
    }
  }, [activeTaskBlockId, extraction])

  useEffect(() => {
    if (contextMenu && extraction && !extraction.blocks.some(block => block.id === contextMenu.blockId)) {
      setContextMenu(null)
    }
  }, [contextMenu, extraction])

  useEffect(() => {
    if (!workflowShellEnabled) return
    const handleWorkflowKeydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const isTyping = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable
      if (isTyping || event.metaKey || event.ctrlKey || event.altKey) return
      const key = event.key.toLowerCase()
      if (key === 'a' || key === 'r' || key === 's') {
        event.preventDefault()
        setWorkflowTaskIndex(index => Math.min((workflowTriage?.human_triage_queue.length ?? 1) - 1, index + 1))
        setIntentDraft('')
      }
    }
    window.addEventListener('keydown', handleWorkflowKeydown)
    return () => window.removeEventListener('keydown', handleWorkflowKeydown)
  }, [workflowShellEnabled, workflowTriage?.human_triage_queue.length])

  const markBlockDirty = (blockId: string) => {
    setDirtyBlockIds(prev => {
      const next = new Set(prev)
      next.add(blockId)
      return next
    })
  }

  const clearAreaSelection = useCallback(() => {
    setSelectedAreaBBox(null)
    setSelectedAreaBlockIds(new Set())
  }, [])

  const applyHumanEditMetadata = (block: BboxBlock, note: string): BboxBlock => {
    const reviewNotes = new Set(block.reviewNotes || [])
    reviewNotes.add(note)
    return {
      ...block,
      humanEdited: true,
      humanEditedAt: new Date().toISOString(),
      reviewNotes: [...reviewNotes],
    }
  }

  const updateBlock = useCallback((blockId: string, updater: (block: BboxBlock) => BboxBlock) => {
    setExtraction(prev => {
      if (!prev) return prev
      return {
        ...prev,
        blocks: prev.blocks.map(block => block.id === blockId ? updater(block) : block),
      }
    })
    markBlockDirty(blockId)
    setDeletedBlockIds(prev => {
      const next = new Set(prev)
      next.delete(blockId)
      return next
    })
    setSaveError(null)
    setSaveNotice(null)
  }, [])

  const handleBlockBBoxChange = useCallback((blockId: string, bbox: [number, number, number, number]) => {
    updateBlock(blockId, (block) => {
      if (sameBBox(block.bbox, bbox)) return block
      return applyHumanEditMetadata({ ...block, bbox }, 'Human adjusted bbox in pdf-lab')
    })
  }, [updateBlock])

  const reclassifyBlock = useCallback((blockId: string, newType: BboxBlock['blockType']) => {
    updateBlock(blockId, (block) => {
      if (block.blockType === newType) return block
      return applyHumanEditMetadata({
        ...block,
        blockType: newType,
      }, 'Human reclassified block in pdf-lab')
    })
  }, [updateBlock])

  const handleReclassify = (newType: BboxBlock['blockType']) => {
    if (!selectedBlockId) return
    reclassifyBlock(selectedBlockId, newType)
  }

  const deleteBlock = (blockId: string) => {
    setExtraction(prev => {
      if (!prev) return prev
      return {
        ...prev,
        blocks: prev.blocks.filter(block => block.id !== blockId),
      }
    })
    setDeletedBlockIds(prev => {
      const next = new Set(prev)
      next.add(blockId)
      return next
    })
    setDirtyBlockIds(prev => {
      const next = new Set(prev)
      next.delete(blockId)
      return next
    })
    setSelectedBlockId(prev => prev === blockId ? null : prev)
    setActiveTaskBlockId(prev => prev === blockId ? null : prev)
    setContextMenu(prev => prev?.blockId === blockId ? null : prev)
    setSaveError(null)
    setSaveNotice(null)
  }

  const deleteBlocks = useCallback((blockIds: string[]) => {
    if (blockIds.length === 0) return
    setExtraction(prev => {
      if (!prev) return prev
      const idSet = new Set(blockIds)
      return {
        ...prev,
        blocks: prev.blocks.filter(block => !idSet.has(block.id)),
      }
    })
    setDeletedBlockIds(prev => {
      const next = new Set(prev)
      blockIds.forEach((blockId) => next.add(blockId))
      return next
    })
    setDirtyBlockIds(prev => {
      const next = new Set(prev)
      blockIds.forEach((blockId) => next.delete(blockId))
      return next
    })
    setSelectedBlockId(prev => (prev && blockIds.includes(prev) ? null : prev))
    setActiveTaskBlockId(prev => (prev && blockIds.includes(prev) ? null : prev))
    setContextMenu(prev => (prev && blockIds.includes(prev.blockId) ? null : prev))
    setSaveError(null)
    setSaveNotice(null)
  }, [])

  const handleDeleteSelected = useCallback(() => {
    if (!selectedBlockId) return
    deleteBlock(selectedBlockId)
  }, [selectedBlockId])

  const nudgeSelectedBlock = useCallback((dx: number, dy: number) => {
    if (!selectedBlockId || !selectedBlock) return
    const [x1, y1, x2, y2] = selectedBlock.bbox
    const width = x2 - x1
    const height = y2 - y1
    const nextX1 = clampNormalized(x1 + dx, 0, 1 - width)
    const nextY1 = clampNormalized(y1 + dy, 0, 1 - height)
    const nextBBox: [number, number, number, number] = [
      nextX1,
      nextY1,
      nextX1 + width,
      nextY1 + height,
    ]
    handleBlockBBoxChange(selectedBlockId, nextBBox)
  }, [handleBlockBBoxChange, selectedBlockId, selectedBlock])

  const createBlockFromBBox = useCallback((
    bbox: [number, number, number, number],
    blockType: BboxBlock['blockType'],
    note: string,
    overrides: Partial<BboxBlock> = {},
  ) => {
    const blockId = `human:p${currentPage}:${Date.now()}`
    const createdAt = new Date().toISOString()
    const newBlock: BboxBlock = {
      id: blockId,
      page: currentPage,
      bbox,
      blockType,
      semanticType: toSemanticType(blockType),
      text: '',
      confidence: 1,
      humanEdited: true,
      humanEditedAt: createdAt,
      cascadeTrail: [{
        tier: 'T2',
        tierName: 'Human',
        disposition: 'accept',
        confidence: 1,
      }],
      ...overrides,
      reviewNotes: dedupeNotes([note, ...(overrides.reviewNotes || [])]),
    }
    setExtraction(prev => {
      if (!prev) return prev
      return {
        ...prev,
        blocks: [...prev.blocks, newBlock],
      }
    })
    setTypeFilters(prev => {
      const next = new Set(prev)
      next.add(newBlock.blockType)
      return next
    })
    markBlockDirty(blockId)
    setSelectedBlockId(blockId)
    setActiveTaskBlockId(blockId)
    setSaveError(null)
    setSaveNotice(null)
    clearAreaSelection()
  }, [clearAreaSelection, currentPage])

  const handleCreateBlock = useCallback((bbox: [number, number, number, number]) => {
    createBlockFromBBox(bbox, newBlockType, 'Human created block in pdf-lab')
  }, [createBlockFromBBox, newBlockType])

  const handleAreaSelect = useCallback((bbox: [number, number, number, number], blockIds: string[]) => {
    setSelectedAreaBBox(bbox)
    setSelectedAreaBlockIds(new Set(blockIds))
    setSelectedBlockId(null)
    setContextMenu(null)
  }, [])

  const handleDeleteSelectedArea = useCallback(() => {
    const blockIds = [...selectedAreaBlockIds]
    if (blockIds.length === 0) return
    deleteBlocks(blockIds)
    clearAreaSelection()
    setSaveNotice(`Deleted ${blockIds.length} blocks from selected area`)
  }, [clearAreaSelection, deleteBlocks, selectedAreaBlockIds])

  const handleReplaceAreaWithTable = useCallback(() => {
    if (!selectedAreaBBox) return
    const blockIds = [...selectedAreaBlockIds]
    if (blockIds.length > 0) deleteBlocks(blockIds)
    createBlockFromBBox(selectedAreaBBox, 'table', 'Human promoted selected area to table in pdf-lab')
    setSelectionMode('draw-block')
    setSaveNotice(blockIds.length > 0
      ? `Replaced ${blockIds.length} blocks with a table region`
      : 'Created table region from selected area')
  }, [createBlockFromBBox, deleteBlocks, selectedAreaBBox, selectedAreaBlockIds])

  const handleReextractSelectedArea = useCallback(async () => {
    if (!selectedAreaBBox) return
    setReextractingArea(true)
    setSaveError(null)
    setSaveNotice(null)
    try {
      const response = await fetch('/api/pdf-lab/reextract-table-region', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdfUrl,
          pageNumber: currentPage,
          bbox: selectedAreaBBox,
          flavor: 'stream',
        }),
      })
      const payload = await response.json() as TableRegionReextractResult
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || `Region table extraction failed (${response.status})`)
      }

      const blockIds = [...selectedAreaBlockIds]
      if (blockIds.length > 0) deleteBlocks(blockIds)
      createBlockFromBBox(
        payload.bbox_norm_tlbr,
        'table',
        `Human triggered region table re-extract (${payload.flavor_used}) in pdf-lab`,
        {
          text: payload.text,
          confidence: 1,
          semanticType: payload.rows > 0 && payload.cols > 0
            ? `Table ${payload.rows}x${payload.cols}`
            : 'Table',
          reviewNotes: [
            `Region table re-extract succeeded via ${payload.flavor_used}`,
            `rows=${payload.rows} cols=${payload.cols} accuracy=${Number(payload.accuracy || 0).toFixed(3)}`,
          ],
        },
      )
      setSelectionMode('draw-block')
      setSaveNotice(
        blockIds.length > 0
          ? `Re-extracted table from selected area and replaced ${blockIds.length} blocks`
          : `Re-extracted table from selected area (${payload.rows}×${payload.cols})`,
      )
    } catch (reextractErr) {
      setSaveError(reextractErr instanceof Error ? reextractErr.message : String(reextractErr))
    } finally {
      setReextractingArea(false)
    }
  }, [createBlockFromBBox, currentPage, deleteBlocks, pdfUrl, selectedAreaBBox, selectedAreaBlockIds])

  const handleRevert = () => {
    if (!baselineExtraction) return
    setExtraction(cloneExtractionData(baselineExtraction))
    setDirtyBlockIds(new Set())
    setDeletedBlockIds(new Set())
    clearAreaSelection()
    setSelectedBlockId(null)
    setContextMenu(null)
    setSaveError(null)
    setSaveNotice(null)
  }

  const handleSave = async () => {
    if (!extraction || !canEditExtraction || dirtyCount === 0) return
    setSaving(true)
    setSaveError(null)
    setSaveNotice(null)
    try {
      const response = await fetch('/api/pdf-lab/review-save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdfUrl,
          extractionUrl,
          updatedBlocks: dirtyBlocks,
          deletedBlockIds: [...deletedBlockIds],
          reviewMode: extraction.reviewMode ?? 'reviewed',
          reviewSummary: extraction.reviewSummary ?? null,
          fileId: selectedFile.id,
          fileName: selectedFile.name,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || payload.detail || `Save failed (${response.status})`)
      setExtraction(payload.extraction)
      setBaselineExtraction(cloneExtractionData(payload.extraction))
      setDirtyBlockIds(new Set())
      setDeletedBlockIds(new Set())
      clearAreaSelection()
      setContextMenu(null)
      setSaveNotice(`Saved ${payload.updatedBlocks} block edits and ${payload.deletedBlocks} deletions`)
      setEditMode(false)
    } catch (saveErr) {
      setSaveError(saveErr instanceof Error ? saveErr.message : String(saveErr))
    } finally {
      setSaving(false)
    }
  }

  const showQueueView = useCallback((page?: number) => {
    if (typeof page === 'number') setCurrentPage(page)
    setSelectedBlockId(null)
    setActiveTaskBlockId(null)
    setContextMenu(null)
    clearAreaSelection()
    setShowAuditPane(true)
    setAuditTab('queue')
  }, [clearAreaSelection])

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (editMode && canEditExtraction && !selectedBlockId && selectedAreaBlockIds.size > 0 && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (e.key === 'Backspace' || e.key === 'Delete') {
          e.preventDefault()
          handleDeleteSelectedArea()
          return
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          clearAreaSelection()
          return
        }
      }

      if (editMode && canEditExtraction && selectedBlockId && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const step = e.shiftKey ? 0.005 : 0.001
        if (e.key === 'ArrowRight') {
          e.preventDefault()
          nudgeSelectedBlock(step, 0)
          return
        }
        if (e.key === 'ArrowLeft') {
          e.preventDefault()
          nudgeSelectedBlock(-step, 0)
          return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          nudgeSelectedBlock(0, -step)
          return
        }
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          nudgeSelectedBlock(0, step)
          return
        }
        if (e.key === 'Backspace' || e.key === 'Delete') {
          e.preventDefault()
          handleDeleteSelected()
          return
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          setSelectedBlockId(null)
          setContextMenu(null)
          return
        }
      }

      if (e.key === 'ArrowRight' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault()
        if (reviewNavMode && nextFlaggedPage !== null) {
          showQueueView(nextFlaggedPage)
        } else if (!reviewNavMode && extraction && currentPage < extraction.pageCount - 1) {
          setCurrentPage(p => p + 1)
        }
      }
      if (e.key === 'ArrowLeft' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault()
        if (reviewNavMode && prevFlaggedPage !== null) {
          showQueueView(prevFlaggedPage)
        } else if (!reviewNavMode && currentPage > 0) {
          setCurrentPage(p => p - 1)
        }
      }
      if (e.shiftKey && e.key === 'ArrowRight' && extraction && currentPage < extraction.pageCount - 1) {
        setCurrentPage(p => p + 1)
      }
      if (e.shiftKey && e.key === 'ArrowLeft' && currentPage > 0) {
        setCurrentPage(p => p - 1)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [canEditExtraction, clearAreaSelection, currentPage, editMode, extraction, handleDeleteSelected, handleDeleteSelectedArea, nextFlaggedPage, nudgeSelectedBlock, prevFlaggedPage, reviewNavMode, selectedAreaBlockIds.size, selectedBlockId, showQueueView])

  const handleSelectFile = (file: PdfFile) => {
    setSelectedFile(file)
    // Update URL without reload
    const newHash = `#pdf-lab?pdf=${encodeURIComponent(file.pdfUrl)}&extraction=${encodeURIComponent(file.extractionUrl)}`
    window.history.replaceState(null, '', newHash)
  }

  const inspectBlock = useCallback((block: BboxBlock, options?: {
    jumpToPage?: boolean
    syncActiveTask?: boolean
  }) => {
    if (options?.jumpToPage) setCurrentPage(block.page)
    setSelectedBlockId(block.id)
    if (options?.syncActiveTask) {
      setActiveTaskBlockId(isUnresolvedBlock(block) ? block.id : null)
    }
    setContextMenu(null)
    clearAreaSelection()
    setShowAuditPane(true)
    setAuditTab('selected')
    setTypeFilters(prev => {
      const next = new Set(prev)
      next.add(block.blockType)
      return next
    })
  }, [clearAreaSelection, isUnresolvedBlock])

  const focusQueueBlock = useCallback((block: BboxBlock) => {
    setCurrentPage(block.page)
    setSelectedBlockId(block.id)
    setActiveTaskBlockId(block.id)
    setContextMenu(null)
    clearAreaSelection()
    setShowAuditPane(true)
    setAuditTab('queue')
    setTypeFilters(prev => {
      const next = new Set(prev)
      next.add(block.blockType)
      return next
    })
  }, [clearAreaSelection])

  const jumpToPage = useCallback((page: number) => {
    showQueueView(page)
  }, [showQueueView])

  const findNextDecisionBlock = useCallback((block: BboxBlock): BboxBlock | null => {
    const remainingBlocks = unresolvedBlocks.filter(candidate => candidate.id !== block.id)
    const samePageBlock = remainingBlocks.find(candidate => candidate.page === block.page)
    if (samePageBlock) return samePageBlock

    const remainingPages = [...new Set(remainingBlocks.map(candidate => candidate.page))].sort((a, b) => a - b)
    const nextPage = remainingPages.find(page => page > block.page) ?? remainingPages[0]
    if (typeof nextPage !== 'number') return null
    return remainingBlocks.find(candidate => candidate.page === nextPage) ?? null
  }, [unresolvedBlocks])

  const completeTaskWithStatus = useCallback((block: BboxBlock, reviewStatus: NonNullable<BboxBlock['reviewStatus']>, action: string, note: string) => {
    if (!canEditExtraction) return
    const nextBlock = findNextDecisionBlock(block)

    setVerificationToast({
      action,
      block,
      previousActiveTaskBlockId: activeTaskBlockId,
      previousSelectedBlockId: selectedBlockId,
    })

    updateBlock(block.id, current => applyHumanEditMetadata({
      ...current,
      reviewStatus,
      confidence: 1,
      flagged: false,
      hasOpenComments: false,
    }, note))

    setBboxFixTaskIds(prev => {
      const next = new Set(prev)
      next.delete(block.id)
      return next
    })
    setPreviewGridBlockId(prev => prev === block.id ? null : prev)

    if (nextBlock) {
      focusQueueBlock(nextBlock)
    } else {
      setSelectedBlockId(null)
      setActiveTaskBlockId(null)
    }
    setSaveNotice(`${action}. Save to persist.`)
  }, [activeTaskBlockId, canEditExtraction, findNextDecisionBlock, focusQueueBlock, selectedBlockId, updateBlock])

  const handleTaskAction = useCallback((task: PdfLabTask, action: PdfLabTaskAction) => {
    const block = task.block
    switch (action.type) {
      case 'ADD':
        completeTaskWithStatus(block, 'verified', `${humanizeMissedObjectType(block)} Added`, 'Human added missing object proposed by agent in pdf-lab')
        return
      case 'VERIFY':
      case 'CONFIRM_FIX':
        completeTaskWithStatus(block, 'verified', action.type === 'CONFIRM_FIX' ? 'Fix Confirmed' : 'Verified', 'Human verified agent proposal in pdf-lab')
        return
      case 'IGNORE':
        completeTaskWithStatus(block, 'ignored', 'Ignored', 'Human ignored agent proposal in pdf-lab')
        return
      case 'DELETE':
        completeTaskWithStatus(block, 'rejected', 'Rejected', 'Human rejected agent proposal in pdf-lab')
        return
      case 'KEEP':
        completeTaskWithStatus(block, 'verified', 'Kept', 'Human kept agent-flagged block in pdf-lab')
        return
      case 'FIX_BBOX':
        setBboxFixTaskIds(prev => new Set(prev).add(block.id))
        setEditMode(true)
        setSelectionMode('draw-block')
        focusQueueBlock(block)
        return
      case 'PREVIEW_GRID':
        setPreviewGridBlockId(prev => prev === block.id ? null : block.id)
        focusQueueBlock(block)
        return
      case 'RECLASSIFY':
        reclassifyBlock(block.id, block.blockType === 'table' ? 'text' : 'table')
        setBboxFixTaskIds(prev => new Set(prev).add(block.id))
        focusQueueBlock(block)
        return
    }
  }, [completeTaskWithStatus, focusQueueBlock, reclassifyBlock])


  const blockContextMenuItems = useMemo<ContextMenuItem[]>(() => {
    if (!contextMenuBlock) return []
    const items: ContextMenuItem[] = [
      {
        label: 'Inspect block',
        icon: <Focus size={12} />,
        shortcut: 'Enter',
        onClick: () => inspectBlock(contextMenuBlock),
        'data-qid': 'pdf-lab:context:select',
        'data-qs-action': 'PDF_LAB_CONTEXT_SELECT',
      },
    ]

    if (canEditExtraction) {
      items.push(
        { separator: true, onClick: () => {} },
        {
          label: 'Delete block',
          icon: <Trash2 size={12} />,
          shortcut: 'Del',
          danger: true,
          onClick: () => deleteBlock(contextMenuBlock.id),
          'data-qid': 'pdf-lab:context:delete',
          'data-qs-action': 'PDF_LAB_CONTEXT_DELETE',
        },
        { separator: true, onClick: () => {} },
        { label: 'Reclassify', header: true, onClick: () => {} },
        ...EDITABLE_BLOCK_TYPES.map((type) => ({
          label: `Set as ${BLOCK_TYPE_LABELS[type]}`,
          disabled: contextMenuBlock.blockType === type,
          onClick: () => reclassifyBlock(contextMenuBlock.id, type),
          'data-qid': `pdf-lab:context:type:${type}`,
          'data-qs-action': `PDF_LAB_CONTEXT_TYPE_${type.toUpperCase()}`,
        }))
      )
    }

    return items
  }, [contextMenuBlock, canEditExtraction, inspectBlock, reclassifyBlock])

  const selectedAreaToolbar = selectedAreaBBox && canEditExtraction ? (
    <div style={contextualHudStyle}>
      <button
        data-qid="pdf-lab:context:extract-area-table"
        title="Run pdf_oxide table extraction inside the selected area"
        onClick={handleReextractSelectedArea}
        disabled={!selectedAreaBBox || reextractingArea}
        style={{ ...contextualBtnStyle, opacity: selectedAreaBBox && !reextractingArea ? 1 : 0.45, color: EMBRY.green }}
      >
        <FileText size={13} />
        {reextractingArea ? 'Extracting…' : 'Extract Table'}
      </button>
      <button
        data-qid="pdf-lab:context:area-to-table"
        title="Replace the selected area with a table block"
        onClick={handleReplaceAreaWithTable}
        disabled={!selectedAreaBBox}
        style={{ ...contextualBtnStyle, opacity: selectedAreaBBox ? 1 : 0.45 }}
      >
        <Focus size={13} />
        Area → Table
      </button>
      <button
        data-qid="pdf-lab:context:delete-area"
        title="Delete all blocks in the selected area"
        onClick={handleDeleteSelectedArea}
        disabled={selectedAreaBlockIds.size === 0}
        style={{ ...contextualBtnStyle, opacity: selectedAreaBlockIds.size > 0 ? 1 : 0.45, color: EMBRY.amber }}
      >
        <Trash2 size={13} />
        Delete
      </button>
    </div>
  ) : null

  if (initialSubpath === 'loop' || initialSubpath === 'tau-loop') {
    return <TauLoopView />
  }
  if (initialSubpath === 'surgical-fixture') {
    return <SurgicalTriageFixture />
  }

  if (initialSubpath === 'static-proof') {
    return <SurgicalTriageStaticProof />
  }

  if (initialSubpath === 'evidence-qa' || initialSubpath === 'nico-qa') {
    return <PdfLabEvidenceQA />
  }

  if (initialSubpath === 'surgical-clean-room') {
    if (workflowTasks.length === 0) {
      return <PdfLabEvidenceQA />
    }

    return (
      <SurgicalTriageCleanRoom
        pdfUrl={PDF_LAB_REAL_NIST_PDF_URL}
        pageNumber={11}
        taskIndex={0}
        taskCount={96}
        task={{
          id: 'clean-room-p12-table-uncertain',
          question: 'Is this a real table, and are the extracted table bounds correct?',
          reasoning: 'pdf_oxide emitted a table object. In Zen Mode, the reviewer should confirm table/not-table and bbox only; cell editing belongs in Audit Mode.',
          path: 'NIST › APPX A › GLOSSARY',
          severity: 'high',
          bbox: [0.158, 0.103, 0.54, 0.291],
        }}
        intentDraft={intentDraft}
        onIntentChange={setIntentDraft}
        onAccept={() => undefined}
        onReject={() => undefined}
        onSkip={() => undefined}
        onPrevious={() => undefined}
        onNext={() => undefined}
        onOpenAudit={() => undefined}
        onOpenQueue={() => undefined}
      />
    )
  }

  if (initialSubpath !== 'legacy-workflow') {
    return <PdfLabProductionWorkflow initialStage={resolveProductionStage(initialSubpath)} />
  }

  if (workflowShellEnabled) {
    if (workflowLoading) {
      return (
        <div style={workflowLoadingStyle}>
          <div style={workflowLoadingCardStyle}>
            <div style={workflowEyebrowStyle}>PDF Lab · Real NIST workflow</div>
            <h1 style={workflowLoadingTitleStyle}>Loading agentic extraction artifacts…</h1>
            <p style={workflowMutedTextStyle}>Fetching full extraction, workflow manifest, and human triage queue from real NIST data.</p>
          </div>
        </div>
      )
    }

    if (workflowError || !workflowManifest || !workflowExtraction || !workflowTriage) {
      return (
        <div style={workflowLoadingStyle}>
          <div style={workflowLoadingCardStyle}>
            <div style={workflowEyebrowStyle}>PDF Lab · Artifact contract blocked</div>
            <h1 style={workflowLoadingTitleStyle}>Cannot load real workflow data</h1>
            <p style={{ ...workflowMutedTextStyle, color: EMBRY.red }}>{workflowError || 'Missing workflow artifacts'}</p>
            <button className="pdf-lab-btn" style={workflowSecondaryButtonStyle} onClick={() => setWorkflowShellEnabled(false)}>
              Open legacy audit surface
            </button>
          </div>
        </div>
      )
    }

    const goToWorkflowTask = (index: number) => {
      const boundedIndex = Math.max(0, Math.min(workflowTasks.length - 1, index))
      const task = workflowTasks[boundedIndex]
      setWorkflowTaskIndex(boundedIndex)
      if (task) setCurrentPage(Math.max(0, task.page - 1))
      setWorkflowStageId('human_triage')
      setIntentDraft('')
    }

    const currentGateAccuracy = typeof workflowManifest.gate.details?.known_validation_accuracy === 'number'
      ? workflowManifest.gate.details.known_validation_accuracy
      : null
    const activeWorkflowTaskPage = activeWorkflowTask?.page ?? currentPage + 1
    const activeWorkflowTaskKind = activeWorkflowTask?.kind.replace(/_/g, ' ') ?? 'triage'
    const nextWorkflowTask = workflowTasks[workflowTaskIndex + 1]
    const workflowQueueStart = Math.max(0, workflowTaskIndex - 2)
    const workflowQueueTasks = workflowTasks.slice(workflowQueueStart, workflowQueueStart + 10)
    const triageProgressPercent = workflowTasks.length > 0
      ? Math.round((workflowTaskIndex / workflowTasks.length) * 100)
      : 100
    const highSeverityCount = workflowTriage.summary.tasks_by_severity?.high ?? 0
    const mediumSeverityCount = workflowTriage.summary.tasks_by_severity?.medium ?? 0
    const surgicalTask = activeWorkflowTask
      ? {
          id: activeWorkflowTask.task_id,
          pageNumber: activeWorkflowTask.page,
          question: activeWorkflowTask.human_question,
          reasoning: activeWorkflowTask.agent_reasoning,
          confidence: activeWorkflowTaskBlock?.confidence ?? 0.68,
          path: 'NIST › APPX A › GLOSSARY',
          severity: activeWorkflowTask.severity,
          bbox: workflowAttentionBBox ?? activeWorkflowTask.target_bbox ?? activeWorkflowTaskBlock?.bbox ?? [0, 0, 1, 1] as [number, number, number, number],
        }
      : null

    return (
      <SurgicalTriageCleanRoom
        pdfUrl={PDF_LAB_REAL_NIST_PDF_URL}
        pageNumber={workflowEvidencePage}
        taskIndex={workflowTaskIndex}
        taskCount={workflowTasks.length}
        task={surgicalTask}
        intentDraft={intentDraft}
        onIntentChange={setIntentDraft}
        onAccept={() => goToWorkflowTask(workflowTaskIndex + 1)}
        onReject={() => goToWorkflowTask(workflowTaskIndex + 1)}
        onSkip={() => goToWorkflowTask(workflowTaskIndex + 1)}
        onPrevious={() => goToWorkflowTask(workflowTaskIndex - 1)}
        onNext={() => goToWorkflowTask(workflowTaskIndex + 1)}
        onOpenAudit={() => setWorkflowShellEnabled(false)}
        onOpenQueue={() => setWorkflowStageId('human_triage')}
      />
    )

    return (
      <div data-qid="pdf-lab:agentic-workflow" style={workflowRootStyle}>
        <header style={workflowHeaderStyle}>
          <div style={workflowHeaderProgressStyle}>
            <div style={workflowHeaderProgressTrackStyle}>
              <div style={{ ...workflowHeaderProgressFillStyle, width: `${triageProgressPercent}%` }} />
            </div>
            <span style={workflowHeaderProgressLabelStyle}>
              Card {workflowTaskIndex + 1} / {workflowTasks.length} · {workflowTriage!.summary.pages_with_tasks ?? 0} pages with final ambiguities
            </span>
          </div>
          <div style={workflowHeaderTitleStyle}>
            NIST SP 800-53 Rev. 5 · Surgical Triage
          </div>
          <div style={workflowHeaderActionsStyle}>
            <ReviewBundleButton
              app="pdf-lab"
              endpoint="/api/pdf-lab/gemini-review-bundle"
              actionId="pdf-lab:workflow:gemini-review-bundle"
              action="PDF_LAB_WORKFLOW_GEMINI_REVIEW_BUNDLE"
              label="Gemini Bundle"
              title="Generate a complete Gemini review/fix request bundle and copy it with xclip"
              description="Generate a Gemini review/fix request with current PDF Lab code, workflow context, screenshots, and known design failures"
              className="pdf-lab-btn"
              requestBody={{
                surface: 'pdf-lab',
                route: 'http://localhost:3002/#pdf-lab',
                activeTaskId: activeWorkflowTask.task_id,
                activePage: activeWorkflowTask.page,
                workflowTaskIndex,
              }}
              style={workflowReviewBundleButtonStyle}
            />
            <span style={{ ...workflowStatusPillStyle, color: EMBRY.green, borderColor: `${EMBRY.green}55` }}>
              {currentGateAccuracy !== null ? `${(currentGateAccuracy! * 100).toFixed(1)}% gate` : 'gate passed'}
            </span>
            <span style={workflowStatusPillStyle}>
              {highSeverityCount} high · {mediumSeverityCount} medium
            </span>
            <details style={workflowDiagnosticsDetailsStyle}>
              <summary
                data-qid="pdf-lab:workflow:diagnostics"
                data-qs-action="PDF_LAB_WORKFLOW_DIAGNOSTICS"
                title="Open workflow diagnostics"
                style={workflowDiagnosticsSummaryStyle}
              >
                i
              </summary>
              <div style={workflowDiagnosticsPopoverStyle}>
                <div style={workflowPanelHeaderStyle}>
                  <span>Workflow diagnostics</span>
                  <span style={workflowPanelMetaStyle}>hidden during triage</span>
                </div>
                <div style={workflowDiagnosticsGridStyle}>
                  <span>Elements</span><strong>{formatCount(workflowManifest!.element_summary.total_elements)}</strong>
                  <span>Candidate pages</span><strong>{workflowManifest!.candidate_inventory.candidate_page_count}</strong>
                  <span>95% gate</span><strong>{currentGateAccuracy !== null ? `${(currentGateAccuracy! * 100).toFixed(2)}%` : 'passed'}</strong>
                  <span>Artifact gaps</span><strong>{workflowManifest!.artifact_gaps.length}</strong>
                </div>
                <div style={workflowDiagnosticsPhaseListStyle}>
                  {workflowManifest!.phases.map(phase => (
                    <button
                      key={phase.id}
                      className="pdf-lab-btn"
                      data-qid={`pdf-lab:workflow:phase:${phase.id}`}
                      data-qs-action="PDF_LAB_WORKFLOW_PHASE"
                      title={`Inspect workflow phase: ${phase.label}`}
                      onClick={() => setWorkflowStageId(phase.id)}
                      style={{
                        ...workflowDiagnosticsPhaseButtonStyle,
                        color: phase.status === 'artifact_gap' ? EMBRY.amber : phase.status === 'passed' || phase.status === 'complete' ? EMBRY.green : EMBRY.white,
                      }}
                    >
                      <span>{phase.label}</span>
                      <span>{phase.status}</span>
                    </button>
                  ))}
                </div>
              </div>
            </details>
            <button
              className="pdf-lab-btn"
              data-qid="pdf-lab:workflow:audit-repair"
              data-qs-action="PDF_LAB_WORKFLOW_AUDIT_REPAIR"
              title="Open detailed audit and repair surface"
              style={workflowSecondaryButtonStyle}
              onClick={() => setWorkflowShellEnabled(false)}
            >
              Audit / Repair
            </button>
          </div>
        </header>

        <main style={workflowMainStyle}>
          <section style={workflowEvidenceShellStyle}>
            <div style={workflowQueuePaneFrameStyle}>
              <LeftPane title="Ambiguities" width={220} defaultCollapsed>
                <LeftPaneSection title={`${workflowTasks.length} cards`}>
                  <div style={workflowQueueListStyle}>
                    {workflowQueueTasks.map((task, offset) => {
                      const absoluteIndex = workflowQueueStart + offset
                      const selected = absoluteIndex === workflowTaskIndex
                      return (
                        <button
                          key={task.task_id}
                          className="pdf-lab-btn"
                          data-qid={`pdf-lab:workflow:queue-card:${task.task_id}`}
                          data-qs-action="PDF_LAB_WORKFLOW_QUEUE_CARD"
                          title={`Open ambiguity ${absoluteIndex + 1} on page ${task.page}`}
                          onClick={() => goToWorkflowTask(absoluteIndex)}
                          style={{
                            ...workflowQueueCardStyle,
                            ...(selected ? workflowQueueCardActiveStyle : null),
                          }}
                        >
                          <span style={workflowQueueCardPageStyle}>p{task.page}</span>
                          <span style={workflowQueueCardBodyStyle}>
                            <span style={workflowQueueCardKindStyle}>{task.kind.replace(/_/g, ' ')}</span>
                            <span style={workflowQueueCardMetaStyle}>{absoluteIndex + 1}/{workflowTasks.length} · {task.severity}</span>
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </LeftPaneSection>
              </LeftPane>
            </div>
            <div style={workflowEvidenceHeaderStyle}>
              <span>Evidence viewport · page {workflowEvidencePage + 1}</span>
              <span>{workflowCanvasBlocks.length} real extraction overlays · next {nextWorkflowTask ? `p${nextWorkflowTask.page}` : 'complete'}</span>
            </div>
            <div style={workflowEvidenceBodyStyle}>
              <div style={workflowCanvasStageStyle}>
                <PdfCanvas
                  pdfUrl={PDF_LAB_REAL_NIST_PDF_URL}
                  pageNumber={workflowEvidencePage}
                  bboxOverlays={workflowCanvasBlocks}
                  agentNotes={workflowAgentNotes}
                  selectedBlockId={activeWorkflowTaskBlock?.id ?? null}
                  activeTaskBlockId={activeWorkflowTaskBlock?.id ?? null}
                  onBlockClick={(blockId) => setSelectedBlockId(blockId)}
                  onCanvasClick={() => setSelectedBlockId(null)}
                  onAgentNoteClick={() => setWorkflowStageId('human_triage')}
                  zoom={1}
                  fitMode="page"
                  editMode={false}
                  autoFrameBBox={workflowAttentionBBox}
                  surgicalFocusBlockId={activeWorkflowTaskBlock?.id ?? null}
                  surgicalFocusBBox={workflowAttentionBBox}
                  surgicalCameraEnabled
                />
              </div>
            </div>
            <footer style={workflowHudBandStyle}>
              {activeWorkflowTask ? (
                <section style={workflowDockedHudStyle}>
                  <div style={workflowHudCopyStyle}>
                    <div style={workflowTriageSeverityRowStyle}>
                      <span style={{
                        color: EMBRY.accent,
                        fontSize: 10,
                        fontWeight: 900,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        fontFamily: '"JetBrains Mono", monospace',
                      }}>
                        Path: NIST › Appx A › Glossary
                      </span>
                      <span style={{
                        color: EMBRY.dim,
                        fontSize: 10,
                        fontWeight: 800,
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                        fontFamily: '"JetBrains Mono", monospace',
                        fontVariantNumeric: 'tabular-nums',
                      }}>
                        CARD {workflowTaskIndex + 1}/{workflowTasks.length} · PAGE {activeWorkflowTask.page} · {activeWorkflowTask.severity.toUpperCase()}
                      </span>
                    </div>
                    <h2 style={workflowTriageQuestionStyle}>{activeWorkflowTask.human_question}</h2>
                    <p style={workflowMutedTextStyle}>{activeWorkflowTask.agent_reasoning}</p>
                  </div>
                  <div style={workflowHudControlsStyle}>
                    <div style={workflowIntentBoxStyle}>
                      <input
                        data-qid="pdf-lab:workflow:intent"
                        data-qs-action="PDF_LAB_WORKFLOW_INTENT"
                        title="Type an intent correction for the active ambiguity"
                        value={intentDraft}
                        onChange={event => setIntentDraft(event.target.value)}
                        placeholder="Type intent correction: table, move box up, split row 2…"
                        style={workflowIntentInputStyle}
                      />
                      {intentMode && (
                        <span style={{
                          ...workflowIntentModeStyle,
                          color: intentMode === 'table' ? EMBRY.green : intentMode === 'bbox' ? EMBRY.amber : EMBRY.accent,
                          borderColor: intentMode === 'table' ? `${EMBRY.green}66` : intentMode === 'bbox' ? `${EMBRY.amber}66` : `${EMBRY.accent}66`,
                        }}>
                          {intentMode === 'table' ? 'CLASSIFY: TABLE' : intentMode === 'bbox' ? 'INTENT: BBOX' : 'QUEUE: SKIP'}
                        </span>
                      )}
                    </div>
                    <div style={workflowTriageActionsStyle}>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:workflow:reject"
                        data-qs-action="PDF_LAB_WORKFLOW_REJECT"
                        title="Reject this ambiguity card and advance"
                        style={{ ...workflowActionButtonStyle, borderColor: `${EMBRY.red}66`, color: EMBRY.red }}
                      onClick={() => goToWorkflowTask(workflowTaskIndex + 1)}
                    >
                      Reject (R)
                    </button>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:workflow:skip"
                        data-qs-action="PDF_LAB_WORKFLOW_SKIP"
                        title="Skip this ambiguity card and advance"
                        style={workflowActionButtonStyle}
                      onClick={() => goToWorkflowTask(workflowTaskIndex + 1)}
                    >
                      Skip (S)
                    </button>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:workflow:accept"
                        data-qs-action="PDF_LAB_WORKFLOW_ACCEPT"
                        title="Accept this ambiguity card and advance"
                        style={{ ...workflowActionButtonStyle, ...workflowAcceptButtonStyle }}
                      onClick={() => goToWorkflowTask(workflowTaskIndex + 1)}
                    >
                      Confirm (A)
                    </button>
                    </div>
                  </div>
                </section>
              ) : (
                <section style={workflowDockedHudStyle}>
                  <h2 style={workflowTriageQuestionStyle}>Triage complete</h2>
                  <p style={workflowMutedTextStyle}>No remaining human ambiguity cards are available in the real queue.</p>
                </section>
              )}
            </footer>
            <div style={workflowHotkeyHintStyle}>
              USE <kbd style={workflowKbdStyle}>A</kbd> ACCEPT · <kbd style={workflowKbdStyle}>R</kbd> REJECT · <kbd style={workflowKbdStyle}>S</kbd> SKIP
            </div>
            <footer style={workflowFooterStyle}>
              <div style={workflowFooterNavStyle}>
                <button
                  className="pdf-lab-btn"
                  data-qid="pdf-lab:workflow:previous"
                  data-qs-action="PDF_LAB_WORKFLOW_PREVIOUS"
                  title="Previous ambiguity card"
                  style={workflowFooterButtonStyle}
                  onClick={() => goToWorkflowTask(workflowTaskIndex - 1)}
                >
                  ←
                </button>
                <button
                  className="pdf-lab-btn"
                  data-qid="pdf-lab:workflow:next"
                  data-qs-action="PDF_LAB_WORKFLOW_NEXT"
                  title="Next ambiguity card"
                  style={workflowFooterButtonStyle}
                  onClick={() => goToWorkflowTask(workflowTaskIndex + 1)}
                >
                  →
                </button>
                <span>Page {activeWorkflowTaskPage} · {activeWorkflowTaskKind}</span>
              </div>
              <div aria-hidden="true" />
              <div style={{ minWidth: 230, textAlign: 'right' }}>Zen Mode Active</div>
            </footer>
          </section>
        </main>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <PdfLeftPane
        selectedFile={selectedFile}
        queuePages={reviewQueuePages}
        currentPage={currentPage}
        progressLabel={progressLabel}
        progressPercent={progressPercent}
        queueModeInfo={queueModeInfo}
        onSelectFile={handleSelectFile}
        onSelectTask={focusQueueBlock}
        onTeleportNext={() => nextUnresolvedBlock && focusQueueBlock(nextUnresolvedBlock)}
      />

      {/* Main Content */}
      <div style={mainContentStyle}>
        {/* Header */}
        <div data-qid="pdf-lab:header" style={headerStyle}>
          <div style={headerPrimaryRowStyle}>
            <div style={headerIdentityStyle}>
              <div style={headerTitleRowStyle}>
                <Eye size={18} color={EMBRY.accent} />
                <div style={headerTitleTextStyle}>{displayTitle.title}</div>
                <span style={{
                  ...statusBadgeStyle,
                  color: isReviewedView ? EMBRY.green : EMBRY.dim,
                  borderColor: isReviewedView ? EMBRY.green : EMBRY.border,
                }}>
                  {isReviewedView ? 'FINAL · VLM reviewed' : 'RAW · baseline'}
                </span>
                {extraction?.reviewSummary && (
                  <>
                    <span style={{ ...metricBadgeStyle, color: EMBRY.green, borderColor: `${EMBRY.green}55` }}>
                      <strong style={metricValueStyle}>{extraction.reviewSummary.verdictCounts.accept}</strong>
                      accept
                    </span>
                    <span style={{ ...metricBadgeStyle, color: EMBRY.amber, borderColor: `${EMBRY.amber}55` }}>
                      <strong style={metricValueStyle}>{extraction.reviewSummary.verdictCounts.needs_human_review}</strong>
                      flagged
                    </span>
                    <span style={metricBadgeStyle}>
                      <strong style={metricValueStyle}>{extraction.reviewSummary.totalFindings}</strong>
                      findings
                    </span>
                  </>
                )}
              </div>
            </div>

            <div style={toolbarShellStyle}>
              <div style={toolbarGroupStyle}>
                <button
                  className="pdf-lab-btn"
                  data-qid="pdf-lab:toolbar:toggle-edit"
                  data-qs-action="PDF_LAB_TOGGLE_EDIT_MODE"
                  title={canEditExtraction ? 'Toggle bbox edit mode' : 'Raw extraction is read-only'}
                  onClick={() => setEditMode(mode => !mode)}
                  disabled={!canEditExtraction}
                  style={{
                    ...actionBtnStyle,
                    opacity: canEditExtraction ? 1 : 0.45,
                    backgroundColor: editMode ? 'rgba(35, 199, 217, 0.14)' : 'transparent',
                    borderColor: editMode ? `${EMBRY.accent}66` : EMBRY.border,
                    color: editMode ? EMBRY.accent : EMBRY.white,
                  }}
                >
                  <Pencil size={14} />
                  {editMode ? 'Editing On' : 'Enable Edit'}
                </button>
                {isReviewedView && (
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:toggle-review-nav"
                    data-qs-action="PDF_LAB_TOGGLE_REVIEW_NAV"
                    title={reviewNavMode ? 'Switch to browse mode (free-form page scrolling)' : 'Switch to review mode (jump between flagged pages only)'}
                    onClick={() => setReviewNavMode(mode => !mode)}
                    style={{
                      ...actionBtnStyle,
                      backgroundColor: reviewNavMode ? 'rgba(124, 58, 237, 0.14)' : 'transparent',
                      borderColor: reviewNavMode ? `${EMBRY.accent}66` : EMBRY.border,
                      color: reviewNavMode ? EMBRY.accent : EMBRY.white,
                    }}
                  >
                    <Navigation size={14} />
                    {reviewNavMode ? 'Review Mode' : 'Browse Mode'}
                  </button>
                )}
              </div>

              <div style={toolbarGroupStyle}>
                {dirtyCount > 0 && (
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:revert"
                    data-qs-action="PDF_LAB_REVERT_CHANGES"
                    title="Discard reviewed changes on this extraction"
                    onClick={handleRevert}
                    disabled={!canEditExtraction}
                    style={{ ...actionBtnStyle, opacity: canEditExtraction ? 1 : 0.45 }}
                  >
                    <RotateCcw size={14} />
                    Revert
                  </button>
                )}
                {(dirtyCount > 0 || saving) && (
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:save"
                    data-qs-action="PDF_LAB_SAVE_CHANGES"
                    title="Persist reviewed changes to disk and memory"
                    onClick={handleSave}
                    disabled={dirtyCount === 0 || saving || !canEditExtraction}
                    style={{ ...actionBtnStyle, opacity: dirtyCount > 0 && canEditExtraction ? 1 : 0.45 }}
                  >
                    <Save size={14} />
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Content Area */}
        {loading ? (
          <div style={centerStyle}>
            <span style={{ color: EMBRY.dim }}>Loading extraction data...</span>
          </div>
        ) : error ? (
          <div style={centerStyle}>
            <span style={{ color: EMBRY.red }}>Error: {error}</span>
          </div>
        ) : (
          <div style={contentAreaStyle}>
            {/* PDF Canvas */}
            <div style={canvasContainerStyle}>
              {canEditExtraction && (
                <div data-qid="pdf-lab:tool-dock" style={toolDockRowStyle}>
                  <div style={toolDockStyle}>
                    <button
                      className="pdf-lab-btn"
                      data-qid="pdf-lab:toolbar:compare-raw"
                      data-qs-action="PDF_LAB_COMPARE_RAW"
                      onClick={() => setShowRawCompare(value => !value)}
                      disabled={!rawCompareExtraction}
                      style={{ ...dockBtnStyle, opacity: rawCompareExtraction ? 1 : 0.45 }}
                      title={rawCompareExtraction ? 'Overlay changed raw blocks for comparison' : 'No raw comparison extraction available'}
                    >
                      <Eye size={14} />
                      {showRawCompare ? 'Hide Raw' : 'Compare Raw'}
                    </button>
                    <button
                      className="pdf-lab-btn"
                      data-qid="pdf-lab:toolbar:select-area"
                      data-qs-action="PDF_LAB_SELECT_AREA"
                      title={selectionMode === 'select-area' ? 'Switch back to draw-block mode' : 'Drag to select an area of existing boxes'}
                      onClick={() => {
                        setSelectionMode(mode => mode === 'select-area' ? 'draw-block' : 'select-area')
                        setSelectedBlockId(null)
                        setContextMenu(null)
                      }}
                      style={{
                        ...dockBtnStyle,
                        color: selectionMode === 'select-area' ? EMBRY.amber : EMBRY.white,
                        borderColor: selectionMode === 'select-area' ? `${EMBRY.amber}66` : EMBRY.border,
                        backgroundColor: selectionMode === 'select-area' ? `${EMBRY.amber}12` : 'rgba(8, 11, 16, 0.88)',
                      }}
                    >
                      <Trash2 size={14} />
                      {selectionMode === 'select-area' ? 'Area Select' : 'Select Area'}
                    </button>
                    {editMode && (
                      <select
                        data-qid="pdf-lab:toolbar:new-block-type"
                        data-qs-action="PDF_LAB_SET_NEW_BLOCK_TYPE"
                        value={newBlockType}
                        onChange={(event) => setNewBlockType(event.target.value as BboxBlock['blockType'])}
                        style={dockSelectStyle}
                        title="Default type for new blocks drawn on the page"
                      >
                        {EDITABLE_BLOCK_TYPES.map(type => (
                          <option key={type} value={type}>{BLOCK_TYPE_LABELS[type]}</option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
              )}
              <div style={{
                ...canvasStageStyle,
                border: reviewNavMode ? '1px solid rgba(124, 58, 237, 0.25)' : '1px solid transparent',
                boxShadow: reviewNavMode ? 'inset 0 0 24px rgba(124, 58, 237, 0.06)' : 'none',
                transition: 'border-color 0.2s, box-shadow 0.2s',
              }}>
                <PdfCanvas
                  pdfUrl={pdfUrl}
	                  pageNumber={currentPage}
	                  bboxOverlays={visibleBlocks}
	                  compareOverlays={rawCompareBlocks}
                    agentNotes={agentNotes}
	                  selectedBlockId={selectedBlockId}
	                  activeTaskBlockId={activeTaskBlockId}
                  onBlockClick={(blockId) => {
                    const block = extraction?.blocks.find(candidate => candidate.id === blockId)
                    if (!block) return
                    inspectBlock(block)
                  }}
                  onBlockContextMenu={(blockId, x, y) => {
                    const block = extraction?.blocks.find(candidate => candidate.id === blockId)
	                    if (block) inspectBlock(block)
	                    setContextMenu({ blockId, x, y })
	                  }}
                    onAgentNoteClick={(_, blockId) => {
                      const block = extraction?.blocks.find(candidate => candidate.id === blockId)
                      if (block) focusQueueBlock(block)
                    }}
                    onAgentNoteAccept={(_, blockId) => {
                      const block = extraction?.blocks.find(candidate => candidate.id === blockId)
                      if (!block) return
                      const task = getRuntimePdfLabTask(block, bboxFixTaskIds.has(block.id))
                      if (task) handleTaskAction(task, task.primaryAction)
                    }}
                    onAgentNoteSecondary={(_, blockId) => {
                      const block = extraction?.blocks.find(candidate => candidate.id === blockId)
                      if (!block) return
                      const task = getRuntimePdfLabTask(block, bboxFixTaskIds.has(block.id))
                      const secondaryAction = task?.secondaryActions[0]
                      if (task && secondaryAction) handleTaskAction(task, secondaryAction)
                    }}
	                  zoom={zoom}
                  fitMode={viewMode === 'fit-page' ? 'page' : 'manual'}
                  editMode={editMode && canEditExtraction}
                  interactionMode={selectionMode}
                  selectedAreaBBox={selectedAreaBBox}
                  selectedAreaBlockIds={[...selectedAreaBlockIds]}
                  onBlockBBoxChange={editMode && canEditExtraction ? handleBlockBBoxChange : undefined}
                  onCanvasClick={() => {
                    setSelectedBlockId(null)
                    setContextMenu(null)
                    clearAreaSelection()
                  }}
                  onCreateBlock={editMode && canEditExtraction ? handleCreateBlock : undefined}
                  onSelectArea={editMode && canEditExtraction ? handleAreaSelect : undefined}
                  selectedAreaToolbar={editMode && canEditExtraction ? selectedAreaToolbar : null}
                />
              </div>
              <div data-qid="pdf-lab:viewport-hud-row" style={viewportHudRowStyle}>
                {(isReviewedView || saveNotice || saveError || (dirtyCount > 0 && canEditExtraction) || reextractingArea) ? (
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    {dirtyCount > 0 && canEditExtraction && (
                      <span style={{ ...statusBadgeStyle, color: EMBRY.amber, borderColor: `${EMBRY.amber}66` }}>
                        {dirtyCount} unsaved
                      </span>
                    )}
                    {reextractingArea && (
                      <span
                        data-qid="pdf-lab:status:reextracting"
                        style={{ ...statusBadgeStyle, color: EMBRY.green, borderColor: EMBRY.green }}
                      >
                        extracting table…
                      </span>
                    )}
                    {isReviewedView && !editMode && !showAuditPane && !saveNotice && !saveError && !reviewNavMode && (
                      <span style={{ fontSize: 11, color: EMBRY.dim }}>
                        Click a block to inspect. Enable Edit to move, resize, delete, or draw.
                      </span>
                    )}
                    {reviewNavMode && isOnFlaggedPage && (
                      <span style={{ fontSize: 11, color: EMBRY.accent, fontWeight: 600 }}>
                        Flagged {currentFlaggedIndex + 1} of {flaggedPageList.length}
                      </span>
                    )}
                    {reviewNavMode && !isOnFlaggedPage && (
                      <span style={{ fontSize: 11, color: EMBRY.dim }}>
                        Page {currentPage + 1} of {extraction?.pageCount || '?'} · no flagged issues
                      </span>
                    )}
                    {saveNotice && <span data-qid="pdf-lab:status:notice" style={{ fontSize: 11, color: EMBRY.green }}>{saveNotice}</span>}
                    {saveError && <span data-qid="pdf-lab:status:error" style={{ fontSize: 11, color: EMBRY.red }}>{saveError}</span>}
                  </div>
                ) : <div style={{ flex: 1 }} />}
                <div data-qid="pdf-lab:viewport-hud" style={viewportHudStyle}>
                  {reviewNavMode && (
                    <>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:toolbar:prev-flagged"
                        data-qs-action="PDF_LAB_PREV_FLAGGED_PAGE"
                        onClick={() => prevFlaggedPage !== null && jumpToPage(prevFlaggedPage)}
                        disabled={prevFlaggedPage === null}
                        style={{
                          ...viewportBtnStyle,
                          opacity: prevFlaggedPage === null ? 0.3 : 1,
                          color: EMBRY.accent,
                          borderColor: `${EMBRY.accent}44`,
                          backgroundColor: 'rgba(124, 58, 237, 0.08)',
                        }}
                        title="Previous flagged page"
                      >
                        <ChevronLeft size={15} />
                        <span style={{ fontSize: 10 }}>Prev</span>
                      </button>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:toolbar:page-prev"
                        data-qs-action="PDF_LAB_PREVIOUS_PAGE_RAW"
                        onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                        disabled={currentPage === 0}
                        style={{ ...viewportBtnStyle, opacity: currentPage === 0 ? 0.3 : 1 }}
                        title="Previous page (raw)"
                      >
                        <ChevronLeft size={12} />
                      </button>
                    </>
                  )}
                  {!reviewNavMode && (
                    <button
                      className="pdf-lab-btn"
                      data-qid="pdf-lab:toolbar:page-prev"
                      data-qs-action="PDF_LAB_PREVIOUS_PAGE"
                      onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                      disabled={currentPage === 0}
                      style={{ ...viewportBtnStyle, opacity: currentPage === 0 ? 0.3 : 1 }}
                      title="Previous page"
                    >
                      <ChevronLeft size={15} />
                    </button>
                  )}
                  <span
                    data-qid="pdf-lab:status:page-indicator"
                    title="Current page indicator"
                    style={{ fontSize: 11, color: EMBRY.white, minWidth: reviewNavMode ? 110 : 92, textAlign: 'center' }}
                  >
                    {reviewNavMode && isOnFlaggedPage
                      ? `Flagged ${currentFlaggedIndex + 1} of ${flaggedPageList.length}`
                      : `Page ${currentPage + 1} of ${extraction?.pageCount || '?'}`}
                  </span>
                  {reviewNavMode && (
                    <>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:toolbar:page-next"
                        data-qs-action="PDF_LAB_NEXT_PAGE_RAW"
                        onClick={() => setCurrentPage(p => Math.min((extraction?.pageCount || 1) - 1, p + 1))}
                        disabled={currentPage >= (extraction?.pageCount || 1) - 1}
                        style={{ ...viewportBtnStyle, opacity: currentPage >= (extraction?.pageCount || 1) - 1 ? 0.3 : 1 }}
                        title="Next page (raw)"
                      >
                        <ChevronRight size={12} />
                      </button>
                      <button
                        className="pdf-lab-btn"
                        data-qid="pdf-lab:toolbar:next-flagged"
                        data-qs-action="PDF_LAB_NEXT_FLAGGED_PAGE"
                        onClick={() => nextFlaggedPage !== null && jumpToPage(nextFlaggedPage)}
                        disabled={nextFlaggedPage === null}
                        style={{
                          ...viewportBtnStyle,
                          opacity: nextFlaggedPage === null ? 0.3 : 1,
                          color: EMBRY.accent,
                          borderColor: `${EMBRY.accent}44`,
                          backgroundColor: 'rgba(124, 58, 237, 0.08)',
                        }}
                        title="Next flagged page"
                      >
                        <span style={{ fontSize: 10 }}>Next</span>
                        <ChevronRight size={15} />
                      </button>
                    </>
                  )}
                  {!reviewNavMode && (
                    <button
                      className="pdf-lab-btn"
                      data-qid="pdf-lab:toolbar:page-next"
                      data-qs-action="PDF_LAB_NEXT_PAGE"
                      onClick={() => setCurrentPage(p => Math.min((extraction?.pageCount || 1) - 1, p + 1))}
                      disabled={currentPage >= (extraction?.pageCount || 1) - 1}
                      style={{ ...viewportBtnStyle, opacity: currentPage >= (extraction?.pageCount || 1) - 1 ? 0.3 : 1 }}
                      title="Next page"
                    >
                      <ChevronRight size={15} />
                    </button>
                  )}
                  <div style={viewportDividerStyle} />
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:zoom-out"
                    data-qs-action="PDF_LAB_ZOOM_OUT"
                    title="Zoom out"
                    onClick={() => {
                      setViewMode('manual')
                      setZoom(z => Math.max(0.25, z - 0.1))
                    }}
                    style={viewportBtnStyle}
                  >
                    <ZoomOut size={15} />
                  </button>
                  <span style={{ fontSize: 11, minWidth: 42, textAlign: 'center', color: EMBRY.dim }}>
                    {viewMode === 'fit-page' ? 'FIT' : `${Math.round(zoom * 100)}%`}
                  </span>
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:zoom-in"
                    data-qs-action="PDF_LAB_ZOOM_IN"
                    title="Zoom in"
                    onClick={() => {
                      setViewMode('manual')
                      setZoom(z => Math.min(2, z + 0.1))
                    }}
                    style={viewportBtnStyle}
                  >
                    <ZoomIn size={15} />
                  </button>
                  <button
                    className="pdf-lab-btn"
                    data-qid="pdf-lab:toolbar:fit-page"
                    data-qs-action="PDF_LAB_FIT_PAGE"
                    title={viewMode === 'fit-page' ? 'Switch to manual zoom controls' : 'Fit the full page in view'}
                    onClick={() => setViewMode(mode => mode === 'fit-page' ? 'manual' : 'fit-page')}
                    style={{
                      ...viewportBtnStyle,
                      color: viewMode === 'fit-page' ? EMBRY.accent : EMBRY.white,
                      borderColor: viewMode === 'fit-page' ? `${EMBRY.accent}55` : 'transparent',
                    }}
                  >
                    <Focus size={15} />
                    Fit
                  </button>
                </div>
              </div>

            </div>

            {showAuditPane && (
	              <SharedRightPane
	                title="Triage Station"
	                subtitle={activeTask
	                  ? `Page ${activeTask.block.page + 1} · ${getBlockDisplayLabel(activeTask.block)}`
	                  : currentPageReview
	                    ? `Page ${currentPage + 1} · ${currentPageReview.verdict} · ${currentPageReview.totalFindings} findings`
	                    : `Page ${currentPage + 1}`}
	                mode="docked"
	                width={280}
	                tabs={[
	                  { id: 'queue', label: 'TASK' },
	                ]}
	                activeTab="queue"
	                onTabChange={() => setAuditTab('queue')}
	                onClose={() => setShowAuditPane(false)}
	              >
                {auditTab === 'selected' ? (
                  <div key="selected" className="pdf-lab-tab-panel">
                  {selectedBlock ? (
                    <div style={{ fontSize: 11 }}>
                      <div style={inspectorModeCardStyle}>
                        <div style={sidebarSectionTitleStyle}>Element inspector</div>
                        <div style={inspectorModeCopyStyle}>
                          {selectedBlockIsUnresolved
                            ? 'This block is also in the review queue. Inspecting it here does not change the queue order.'
                            : 'This block was not flagged for review. You are inspecting it manually without changing the unresolved queue.'}
                        </div>
                        <div style={inspectorModeActionsStyle}>
                          <button
                            className="pdf-lab-btn"
                            data-qid="pdf-lab:selected:back-to-queue"
                            title="Return to the review queue"
                            onClick={() => showQueueView(selectedBlockMatchesActiveTask ? undefined : activeTaskBlock?.page ?? currentPage)}
                            style={queueActionStyle}
                          >
                            Back to Queue
                          </button>
                          {selectedBlockIsUnresolved && !selectedBlockMatchesActiveTask && (
                            <button
                              className="pdf-lab-btn"
                              data-qid={`pdf-lab:selected:make-active:${selectedBlock.id}`}
                              title="Promote this inspected block into the active review task"
                              onClick={() => focusQueueBlock(selectedBlock)}
                              style={{ ...queueActionStyle, marginTop: 0, backgroundColor: EMBRY.bgDeep, borderColor: EMBRY.border }}
                            >
                              Make current task
                            </button>
                          )}
                        </div>
                      </div>
                      {!editMode && canEditExtraction && (
                        <div style={{ marginBottom: 12, padding: 10, backgroundColor: EMBRY.bgDeep, borderRadius: 6, border: `1px solid ${EMBRY.border}` }}>
                          <div style={{ color: EMBRY.white, fontWeight: 600, marginBottom: 4 }}>Read only</div>
                          <div style={{ color: EMBRY.dim, lineHeight: 1.5 }}>
                            This block is selected for inspection. Turn on edit mode to move, resize, delete, or draw replacements.
                          </div>
                        </div>
                      )}
                      {editMode && canEditExtraction && (
                        <div style={{ marginBottom: 12, padding: 8, backgroundColor: EMBRY.bgDeep, borderRadius: 4 }}>
                          <div style={{ ...labelStyle, marginBottom: 6 }}>Edit selected block</div>
                          <BboxEditor
                            block={selectedBlock}
                            onReclassify={handleReclassify}
                            onBboxChange={(bbox) => handleBlockBBoxChange(selectedBlock.id, bbox)}
                            onDelete={handleDeleteSelected}
                          />
                        </div>
                      )}
                      <div style={fieldStyle}>
                        <span style={labelStyle}>Type:</span>
                        <span data-qid="pdf-lab:inspector:type" style={{ color: BLOCK_TYPE_COLORS[selectedBlock.blockType] || EMBRY.white }}>
                          {getBlockDisplayLabel(selectedBlock)}
                        </span>
                      </div>
                      {selectedBlock.semanticType && (
                        <div style={fieldStyle}>
                          <span style={labelStyle}>Semantic:</span>
                          <span data-qid="pdf-lab:inspector:semantic" style={{ color: EMBRY.white }}>{formatSemanticTypeLabel(selectedBlock.semanticType)}</span>
                        </div>
                      )}
                      <div style={fieldStyle}>
                        <span style={labelStyle}>Page:</span>
                        <span style={{ color: EMBRY.white }}>{selectedBlock.page + 1}</span>
                      </div>
                      <div style={fieldStyle}>
                        <span style={labelStyle}>Confidence:</span>
                        <span style={{ color: EMBRY.white }}>{(selectedBlock.confidence * 100).toFixed(0)}%</span>
                      </div>
                      {selectedBlockIsUnresolved && (
                        <div style={fieldStyle}>
                          <span style={labelStyle}>Queue reason:</span>
                          <span style={{ color: EMBRY.amber }}>{describeReviewReason(selectedBlock)}</span>
                        </div>
                      )}
                      {selectedBlock.humanEdited && (
                        <div style={fieldStyle}>
                          <span style={labelStyle}>Human:</span>
                          <span style={{ color: EMBRY.accent }}>
                            edited{selectedBlock.humanEditedAt ? ` · ${selectedBlock.humanEditedAt}` : ''}
                          </span>
                        </div>
                      )}
                      <div style={{ marginTop: 12 }}>
                        <span style={labelStyle}>Text preview:</span>
                        <div data-qid="pdf-lab:inspector:text" style={textPreviewStyle}>{selectedBlock.text || '(empty)'}</div>
                      </div>

                      {selectedBlock.reviewNotes && selectedBlock.reviewNotes.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                          <span style={labelStyle}>Review notes:</span>
                          <div style={qidListStyle}>
                            {selectedBlock.reviewNotes.map((note, i) => (
                              <div key={i} style={qidItemStyle}>{note}</div>
                            ))}
                          </div>
                        </div>
                      )}

                      <details style={{ marginTop: 14 }}>
                        <summary style={{ ...labelStyle, cursor: 'pointer' }}>Technical details</summary>
                        <div style={{ marginTop: 8, display: 'grid', gap: 10 }}>
                          <div>
                            <div style={labelStyle}>BBox</div>
                            <div style={{ fontSize: 9, fontFamily: 'monospace', color: EMBRY.dim, marginTop: 4 }}>
                              [{selectedBlock.bbox.map(n => n.toFixed(3)).join(', ')}]
                            </div>
                          </div>
                          {selectedBlock.tocEntries && selectedBlock.tocEntries.length > 0 && (
                            <div>
                              <div style={labelStyle}>TOC entries</div>
                              <div style={tocListStyle}>
                                {selectedBlock.tocEntries.map((entry, i) => (
                                  <button
                                    key={i}
                                    className="pdf-lab-toc-entry"
                                    onClick={() => setCurrentPage(entry.page - 1)}
                                    title={`Go to page ${entry.page}${entry.qid ? ` | ${entry.qid}` : ''}`}
                                  >
                                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {entry.title}
                                    </span>
                                    <span style={{ color: EMBRY.accent, fontWeight: 600, marginLeft: 8 }}>
                                      {entry.page}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                          {selectedBlock.qids && selectedBlock.qids.length > 0 && (
                            <div>
                              <div style={labelStyle}>QIDs</div>
                              <div style={qidListStyle}>
                                {selectedBlock.qids.map((qid, i) => (
                                  <div key={i} style={qidItemStyle}>{qid}</div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </details>
                    </div>
                  ) : (
                    <div style={{ color: EMBRY.dim, fontSize: 11 }}>
                      Click a block on the page to inspect it here. Queue and Filters stay separate so this pane only describes the selected element.
                    </div>
                  )}
                  </div>
                ) : auditTab === 'queue' ? (
                  <div key="queue" className="pdf-lab-tab-panel">
                    <div style={reviewQueueSectionStyle}>
                      <div style={sidebarSectionTitleStyle}>{queueModeInfo.controlTitle}</div>
                      <div style={queueMetaRowStyle}>
                        <span style={{ color: EMBRY.dim }}>{unresolvedPages.length} pages</span>
                        <span style={{ color: EMBRY.dim }}>{unresolvedBlocks.length} {queueModeInfo.unresolvedLabel}</span>
                      </div>
                      <div data-qid="pdf-lab:inspector:queue-mode" style={inspectorQueueModeStyle}>
                        <span style={{
                          ...queueModeBadgeStyle,
                          color: queueModeInfo.mode === 'calibration' ? EMBRY.amber : EMBRY.green,
                          borderColor: queueModeInfo.mode === 'calibration' ? `${EMBRY.amber}88` : `${EMBRY.green}88`,
                        }}>
                          {queueModeInfo.mode === 'calibration' ? 'Calibration' : 'Review'}
                        </span>
                        <span>{queueModeInfo.description}</span>
                      </div>
                      <div style={{ ...queueMetaRowStyle, marginTop: 8 }}>
                        <button
                          className="pdf-lab-btn"
                          data-qid="pdf-lab:queue:toggle-ghost"
                          data-qs-action="PDF_LAB_TOGGLE_GHOST_QUEUE"
                          title={showGhostQueueItems ? 'Hide high-confidence ghost items' : 'Show all unresolved including ghost items'}
                          onClick={() => setShowGhostQueueItems(value => !value)}
                          style={{
                            ...pageChipStyle,
                            padding: '6px 10px',
                            borderColor: showGhostQueueItems ? EMBRY.accent : EMBRY.border,
                            color: showGhostQueueItems ? EMBRY.white : EMBRY.dim,
                            backgroundColor: showGhostQueueItems ? 'rgba(74, 158, 255, 0.12)' : EMBRY.bgDeep,
                          }}
                        >
                          {showGhostQueueItems ? 'Show low confidence only' : 'Show all confidence bands'}
                        </button>
                      </div>
                    </div>

	                    {activeTaskBlock && activeTask ? (
	                      <div style={{ ...reviewQueueSectionStyle, ...heroTaskSectionStyle }}>
	                        <div style={sidebarSubsectionLabelStyle}>{queueModeInfo.activeQuestionLabel}</div>
	                        <div
	                          key={activeTaskBlock.id}
	                          className="pdf-lab-hero-enter"
	                          data-qid={`pdf-lab:queue:hero:${activeTaskBlock.id}`}
	                          style={heroTaskCardStyle}
                        >
                          <div style={heroTaskHeaderStyle}>
	                            <span
	                              style={{
	                                ...heroTaskBandStyle,
                                color: classifyReviewBand(activeTaskBlock) === 'low' ? '#FF4D4D' : classifyReviewBand(activeTaskBlock) === 'medium' ? '#FFC107' : EMBRY.dim,
                                borderColor: classifyReviewBand(activeTaskBlock) === 'low' ? '#FF4D4D66' : classifyReviewBand(activeTaskBlock) === 'medium' ? '#FFC10766' : EMBRY.border,
                                backgroundColor: classifyReviewBand(activeTaskBlock) === 'low'
                                  ? 'rgba(255, 77, 77, 0.12)'
                                  : classifyReviewBand(activeTaskBlock) === 'medium'
                                    ? 'rgba(255, 193, 7, 0.12)'
                                    : EMBRY.bgDeep,
	                              }}
	                            >
	                              {activeTask.primaryAction.label}
	                            </span>
	                            <span style={{ color: EMBRY.dim, fontSize: 11 }}>
	                              {describeReviewReason(activeTaskBlock)}
	                            </span>
	                          </div>
	                          <div style={heroTaskTitleStyle}>
	                            {activeTask.humanQuestion}
	                            <span style={{ color: EMBRY.dim, fontWeight: 500 }}>
	                              p{activeTaskBlock.page + 1} · {getBlockSemanticSummary(activeTaskBlock)}
	                            </span>
	                          </div>
	                          <div style={heroTaskNoteStyle}>{activeTask.inspectorSummary}</div>
                            <div style={{ marginTop: 12 }}>
                              <div style={sidebarSubsectionLabelStyle}>Preview</div>
                              <div data-qid="pdf-lab:task:preview" style={textPreviewStyle}>
                                {activeTaskBlock.blockType === 'table'
                                  ? `${parseTableRows(activeTaskBlock.text).length || '?'} rows detected · ${getBlockSemanticSummary(activeTaskBlock)}`
                                  : activeTaskBlock.text || '(empty)'}
                              </div>
                            </div>
	                          <div style={heroTaskActionsStyle}>
                              {[activeTask.primaryAction, ...activeTask.secondaryActions].map((action, index) => (
                                <button
                                  key={`${activeTask.id}:${action.type}`}
                                  className="pdf-lab-btn"
                                  data-qid={`pdf-lab:task-action:${action.type.toLowerCase()}:${activeTask.id}`}
                                  data-qs-action={`PDF_LAB_${action.type}_ACTIVE_TASK`}
                                  title={action.label}
                                  onClick={() => handleTaskAction(activeTask, action)}
                                  disabled={!canEditExtraction && action.type !== 'PREVIEW_GRID'}
                                  style={{
                                    ...queueActionStyle,
                                    marginTop: index === 0 ? 0 : 6,
                                    minHeight: index === 0 ? 48 : 44,
                                    backgroundColor: index === 0 ? 'rgba(0, 255, 136, 0.15)' : EMBRY.bgDeep,
                                    borderColor: index === 0 ? `${EMBRY.green}88` : EMBRY.border,
                                  }}
                                >
                                  {action.label}
                                </button>
                              ))}
	                          </div>
	                        </div>
	                      </div>
                    ) : (
                      <div style={reviewQueueSectionStyle}>
                        <div style={sidebarSectionTitleStyle}>Active task</div>
                        <span style={emptyQueueTextStyle}>No unresolved issues remain.</span>
                      </div>
                    )}

                    <div style={reviewQueueSectionStyle}>
                      <div style={sidebarSectionTitleStyle}>Page focus</div>
                      {currentPageReview && (
                        <div style={{ marginBottom: 10 }}>
                          <span
                            data-qid="pdf-lab:status:page-review"
                            style={{
                              ...statusBadgeStyle,
                              color: currentPageReview.verdict === 'accept' ? EMBRY.green : EMBRY.amber,
                              borderColor: currentPageReview.verdict === 'accept' ? EMBRY.green : EMBRY.amber,
                            }}
                          >
                            page {currentPageReview.verdict === 'accept' ? 'accept' : 'needs review'} · {currentPageReview.totalFindings} findings
                          </span>
                        </div>
                      )}
                      <div style={queueMetaRowStyle}>
                        <span style={{ color: EMBRY.white }}>Page {currentPage + 1}</span>
                        <span style={{ color: EMBRY.dim }}>{unresolvedBlocksOnCurrentPage.length} {queueModeInfo.unresolvedLabel}</span>
                      </div>
                      <div style={pageFocusMeterTrackStyle}>
                        <div
                          style={{
                            ...pageFocusMeterFillStyle,
                            width: `${Math.max(pageFocusProgress * 100, unresolvedBlocksOnCurrentPage.length > 0 ? 8 : 0)}%`,
                          }}
                        />
                      </div>
                      <div style={{ ...queueMetaRowStyle, marginTop: 6 }}>
                        <span style={{ color: EMBRY.dim }}>
                          {activeTaskIndexOnPage >= 0 ? `Task ${activeTaskIndexOnPage + 1} of ${unresolvedBlocksOnCurrentPage.length}` : 'No active page task'}
                        </span>
                        {nextUnresolvedBlock && (
                          <button
                            className="pdf-lab-btn"
                            data-qid="pdf-lab:queue:next-flagged"
                            data-qs-action="PDF_LAB_NEXT_UNRESOLVED"
                            title={`Jump to next unresolved issue on page ${nextUnresolvedBlock.page + 1}`}
                            onClick={() => focusQueueBlock(nextUnresolvedBlock)}
                            style={inlineQueueLinkStyle}
                          >
                            Next unresolved
                          </button>
                        )}
                      </div>

                      <div style={{ marginTop: 14 }}>
                        <div style={sidebarSubsectionLabelStyle}>{queueModeInfo.currentPageTitle}</div>
                        <div style={queueListStyle}>
                          {currentPageOtherTasks.length > 0 ? currentPageOtherTasks.slice(0, 8).map(block => (
                            <button
                              className="pdf-lab-btn"
                              key={block.id}
                              data-qid={`pdf-lab:queue:block:${block.id}`}
                              data-qs-action="PDF_LAB_SELECT_PAGE_QUEUE_BLOCK"
                              title={`Select ${BLOCK_TYPE_LABELS[block.blockType] || block.blockType}`}
                              onClick={() => focusQueueBlock(block)}
                              style={{
                                ...queueBlockItemStyle,
                                borderColor: classifyReviewBand(block) === 'low' ? '#FF4D4D66' : classifyReviewBand(block) === 'medium' ? '#FFC10766' : EMBRY.border,
                                backgroundColor: EMBRY.bgDeep,
                              }}
                            >
                              <span style={{ color: classifyReviewBand(block) === 'low' ? '#FF4D4D' : classifyReviewBand(block) === 'medium' ? '#FFC107' : (BLOCK_TYPE_COLORS[block.blockType] || EMBRY.white), fontWeight: 600 }}>
                                {getBlockDisplayLabel(block)}
                              </span>
                              <span style={{ color: EMBRY.white }}>p{block.page + 1} · {getBlockSemanticSummary(block)}</span>
                              <span style={queueBlockNoteStyle}>{classifyReviewBand(block) === 'low' ? 'Action required' : classifyReviewBand(block) === 'medium' ? 'Verify classification' : summarizeReviewNote(block)}</span>
                            </button>
                          )) : (
                            <span style={emptyQueueTextStyle}>No additional unresolved issues on this page.</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div style={reviewQueueSectionStyle}>
                      <div style={sidebarSectionTitleStyle}>Upcoming pages</div>
                      {upcomingUnresolvedPages.length > 0 ? (
                        <details>
                          <summary style={collapsedQueueSummaryStyle}>
                            <span>{upcomingUnresolvedPages.length} more pages with unresolved issues</span>
                            <span style={{ color: EMBRY.dim }}>
                              Next: p{upcomingUnresolvedPages[0].page + 1} · {upcomingUnresolvedPages[0].count}
                            </span>
                          </summary>
                          <div style={{ ...upcomingPageListStyle, marginTop: 10 }}>
                            {upcomingUnresolvedPages.map(({ page, count }) => (
                              <button
                                className="pdf-lab-btn"
                                key={page}
                                data-qid={`pdf-lab:queue:page:${page + 1}`}
                                data-qs-action="PDF_LAB_JUMP_QUEUE_PAGE"
                                title={`Jump to page ${page + 1}`}
                                onClick={() => jumpToPage(page)}
                                style={upcomingPageRowStyle}
                              >
                                <span style={{ color: EMBRY.white, fontWeight: 600 }}>Page {page + 1}</span>
                                <span style={{ color: EMBRY.dim }}>{count} tasks</span>
                              </button>
                            ))}
                          </div>
                        </details>
                      ) : (
                        <span style={emptyQueueTextStyle}>No other pages have unresolved issues.</span>
                      )}
                    </div>
                  </div>
                ) : (
                  <div key="filters" className="pdf-lab-tab-panel">
                    <div style={reviewQueueSectionStyle}>
                      <div style={sidebarSectionTitleStyle}>Overlay filters</div>
                      <div style={filterChipGroupStyle}>
                        {(['table', 'header', 'text', 'figure', 'equation', 'caption'] as const).map(type => (
                          <button
                            className="pdf-lab-btn"
                            key={type}
                            data-qid={`pdf-lab:filter:${type}`}
                            data-qs-action="PDF_LAB_TOGGLE_TYPE_FILTER"
                            title={`Toggle ${BLOCK_TYPE_LABELS[type] || type} overlays`}
                            onClick={() => toggleTypeFilter(type)}
                            style={{
                              ...chipStyle,
                              backgroundColor: typeFilters.has(type) ? BLOCK_TYPE_COLORS[type] + '33' : EMBRY.bgDeep,
                              borderColor: typeFilters.has(type) ? BLOCK_TYPE_COLORS[type] : EMBRY.border,
                              color: typeFilters.has(type) ? BLOCK_TYPE_COLORS[type] : EMBRY.dim,
                            }}
                          >
                            {BLOCK_TYPE_LABELS[type] || type}
                          </button>
                        ))}
                      </div>
                      <div style={{ ...queueMetaRowStyle, marginTop: 10 }}>
                        <span data-qid="pdf-lab:status:page-blocks" style={{ color: EMBRY.dim }}>{visibleBlocks.length} blocks</span>
                        {selectedAreaBBox && <span data-qid="pdf-lab:status:area-selection" style={{ color: EMBRY.amber }}>area · {selectedAreaBlockIds.size}</span>}
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <button
                          className="pdf-lab-btn"
                          data-qid="pdf-lab:filter:queue-scope"
                          data-qs-action="PDF_LAB_TOGGLE_QUEUE_SCOPE"
                          title={showGhostQueueItems ? 'Hide ghost-confidence items from the unresolved queue' : 'Show all confidence bands in the unresolved queue'}
                          onClick={() => setShowGhostQueueItems(value => !value)}
                          style={{
                            ...pageChipStyle,
                            borderColor: showGhostQueueItems ? EMBRY.accent : EMBRY.border,
                            color: showGhostQueueItems ? EMBRY.white : EMBRY.dim,
                            backgroundColor: showGhostQueueItems ? 'rgba(74, 158, 255, 0.12)' : EMBRY.bgDeep,
                          }}
                        >
                          {showGhostQueueItems ? 'Queue: all confidence bands' : 'Queue: red + yellow only'}
                        </button>
                      </div>
                      {showRawCompare && rawCompareBlocks.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          <span style={{ ...statusBadgeStyle, color: EMBRY.amber, borderColor: EMBRY.amber }}>
                            raw compare · {rawCompareBlocks.length} changed
                          </span>
                        </div>
                      )}
                      {editMode && (
                        <div style={{ marginTop: 8, fontSize: 10, color: EMBRY.dim, lineHeight: 1.45 }}>
                          {selectionMode === 'select-area'
                            ? 'Drag to select an area of boxes. Del removes it. Extract Table runs pdf_oxide in that region.'
                            : `Click to select. Drag to move. Handles resize. Draw adds ${BLOCK_TYPE_LABELS[newBlockType]}.`}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </SharedRightPane>
            )}
            {!showAuditPane && (
              <div style={{ ...collapsedPaneRailStyle, borderRight: 'none', borderLeft: `1px solid ${EMBRY.border}` }}>
                <button
                  className="pdf-lab-btn"
                  data-qid="pdf-lab:toolbar:toggle-audit"
                  title="Expand audit pane"
                  onClick={() => setShowAuditPane(true)}
                  style={collapsedPaneButtonStyle}
                >
                  <PanelRightOpen size={18} />
                </button>
              </div>
            )}
          </div>
        )}

        {contextMenu && contextMenuBlock && (
          <ContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            title={`${BLOCK_TYPE_LABELS[contextMenuBlock.blockType] || contextMenuBlock.blockType} · page ${contextMenuBlock.page + 1}`}
            items={blockContextMenuItems}
            onClose={() => setContextMenu(null)}
          />
        )}
      </div>
    </div>
  )
}

function cloneExtractionData(data: ExtractionData): ExtractionData {
  return JSON.parse(JSON.stringify(data)) as ExtractionData
}

function sameBBox(a: [number, number, number, number], b: [number, number, number, number]): boolean {
  return a.every((value, index) => Math.abs(value - b[index]) < 0.000001)
}

function clampNormalized(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function dedupeNotes(notes: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const note of notes) {
    const normalized = note.trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    out.push(normalized)
  }
  return out
}

function findRawCompareFile(file: PdfFile): PdfFile | null {
  if (file.extractionUrl.includes('-raw-extraction.json')) return null
  return PDF_FILES.find(candidate =>
    candidate.pdfUrl === file.pdfUrl && candidate.extractionUrl.includes('-raw-extraction.json')
  ) || null
}

function findFirstPdfLabTaskBlock(data: ExtractionData): BboxBlock | null {
  return data.blocks
    .filter(block => getPdfLabTask(block) !== null)
    .sort((leftBlock, rightBlock) => {
      const priorityDelta = reviewBlockPriority(leftBlock) - reviewBlockPriority(rightBlock)
      if (priorityDelta !== 0) return priorityDelta
      if (leftBlock.page !== rightBlock.page) return leftBlock.page - rightBlock.page
      const vertical = leftBlock.bbox[1] - rightBlock.bbox[1]
      if (Math.abs(vertical) > 0.01) return vertical
      return leftBlock.bbox[0] - rightBlock.bbox[0]
    })[0] ?? null
}

function reviewBlockPriority(block: BboxBlock): number {
  const notes = (block.reviewNotes || []).join(' ').toLowerCase()
  const semantic = (block.semanticType || '').toLowerCase()
  if (block.id.startsWith('review:missed_table')) return 0
  if (semantic === 'definition_list') return 1
  if (block.blockType === 'table') return 2
  if (block.id.startsWith('review:missed_')) return 3
  if (notes.includes('false positive')) return 4
  if (notes.includes('bbox should') || notes.includes('bbox includes')) return 5
  if (notes.includes('table header') || notes.includes('table column')) return 6
  return 9
}

function parseTableRows(text: string): string[][] {
  const tableText = text.replace(/^Table\s+\d+x\d+:\s*/i, '').trim()
  if (!tableText) return []
  return tableText
    .split(';')
    .map(row => row
      .split('|')
      .map(cell => cell.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    )
    .filter(row => row.length > 0)
}

function toSemanticType(blockType: BboxBlock['blockType']): string {
  switch (blockType) {
    case 'table':
      return 'Table'
    case 'header':
      return 'Header'
    case 'figure':
      return 'Figure'
    case 'text':
      return 'Body'
    case 'equation':
      return 'Equation'
    case 'list_item':
      return 'ListItem'
    case 'caption':
      return 'Caption'
    case 'page_number':
      return 'PageNumber'
    case 'boilerplate':
      return 'Boilerplate'
    default:
      return 'Body'
  }
}

function splitDisplayName(name: string): { title: string; qualifier: string | null } {
  const match = name.match(/^(.*?)(?:\s+\(([^)]+)\))?$/)
  if (!match) return { title: name, qualifier: null }
  return {
    title: match[1]?.trim() || name,
    qualifier: match[2]?.trim() || null,
  }
}

function summarizeReviewNote(block: BboxBlock): string {
  if (block.humanEdited) return 'Human edited'
  const note = block.reviewNotes?.[0]
  if (!note) return 'Reviewed'
  return note.length > 70 ? `${note.slice(0, 67)}...` : note
}

function describeReviewReason(block: BboxBlock): string {
  if (block.flagged) return 'flagged for review'
  if (block.hasOpenComments) return 'open review comments'
  if (block.reviewNotes && block.reviewNotes.length > 0) return 'review notes present'
  return `${Math.round((block.confidence ?? 0) * 100)}% confidence`
}

// Styles using EMBRY theme
const burndownCardStyle: React.CSSProperties = {
  padding: '8px 12px',
  display: 'grid',
  gap: 8,
}

const burndownTrackStyle: React.CSSProperties = {
  height: 5,
  borderRadius: 999,
  backgroundColor: 'rgba(255,255,255,0.12)',
  overflow: 'hidden',
}

const burndownFillStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #7c3aed, #23c7d9)',
}

const burndownLabelStyle: React.CSSProperties = {
  color: EMBRY.dim,
  fontSize: 11,
  fontVariantNumeric: 'tabular-nums',
}

const queueModeNoticeStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
  padding: '8px 10px',
  border: `1px solid rgba(255,255,255,0.08)`,
  borderRadius: 10,
  backgroundColor: 'rgba(14, 18, 24, 0.72)',
  fontSize: 11,
  lineHeight: 1.45,
}

const queueModeBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  width: 'fit-content',
  alignItems: 'center',
  border: '1px solid',
  borderRadius: 999,
  padding: '3px 8px',
  fontSize: 10,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
}

const teleportButtonStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 44,
  borderRadius: 10,
  border: `1px solid ${EMBRY.border}`,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
  cursor: 'pointer',
  fontSize: 12,
}

const queuePageGroupStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: `1px solid rgba(255,255,255,0.05)`,
}

const queuePageHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 7,
  fontSize: 11,
}

const queueTaskListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
}

const queueTaskButtonStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '8px 1fr',
  gap: 8,
  alignItems: 'start',
  width: '100%',
  minHeight: 44,
  padding: '7px 8px',
  borderRadius: 8,
  border: `1px solid ${EMBRY.border}`,
  backgroundColor: 'rgba(8, 11, 16, 0.72)',
  color: EMBRY.white,
  cursor: 'pointer',
  textAlign: 'left',
}

const queueTaskDotStyle: React.CSSProperties = {
  width: 7,
  height: 7,
  borderRadius: 999,
  backgroundColor: '#FF4D4D',
  marginTop: 4,
  boxShadow: '0 0 10px rgba(255,77,77,0.5)',
}

const queueTaskTitleStyle: React.CSSProperties = {
  display: 'block',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: 11,
  fontWeight: 800,
}

const queueTaskSubtitleStyle: React.CSSProperties = {
  display: 'block',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  marginTop: 2,
  color: EMBRY.dim,
  fontSize: 9,
}

const pdfDatasetDetailsStyle: React.CSSProperties = {
  padding: '0 8px',
}

const pdfDatasetSummaryToggleStyle: React.CSSProperties = {
  cursor: 'pointer',
  padding: '8px 10px',
  borderRadius: 10,
  border: `1px solid ${EMBRY.border}`,
  color: EMBRY.dim,
  fontSize: 10,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  height: '100%',
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
}

const mainContentStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  overflow: 'hidden',
}

const centerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flex: 1,
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  minHeight: 46,
  padding: '6px 12px',
  borderBottom: `1px solid ${EMBRY.border}`,
  backgroundColor: 'rgba(13, 16, 22, 0.96)',
  backdropFilter: 'blur(10px)',
}

const headerPrimaryRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 10,
  flex: 1,
  minWidth: 0,
}

const headerIdentityStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  minWidth: 0,
  flex: '1 1 420px',
}

const headerTitleRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  minWidth: 0,
}

const headerTitleTextStyle: React.CSSProperties = {
  fontSize: 14,
  lineHeight: 1.1,
  fontWeight: 700,
  color: EMBRY.white,
  letterSpacing: '-0.02em',
  textWrap: 'balance',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  maxWidth: 420,
}

const metricBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  padding: '4px 10px',
  fontSize: 11,
  border: '1px solid',
  borderRadius: 999,
  backgroundColor: EMBRY.bgDeep,
  fontFamily: '"JetBrains Mono", monospace',
  fontVariantNumeric: 'tabular-nums',
  color: EMBRY.white,
  borderColor: EMBRY.border,
}

const metricValueStyle: React.CSSProperties = {
  fontWeight: 700,
  color: EMBRY.white,
}

const toolbarShellStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 8,
  flexWrap: 'wrap',
  flex: '0 1 auto',
}

const toolbarGroupStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 6,
  flexWrap: 'wrap',
}

const filterChipGroupStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexWrap: 'wrap',
}

const chipStyle: React.CSSProperties = {
  padding: '3px 10px',
  fontSize: 11,
  border: '1px solid',
  borderRadius: 10,
  cursor: 'pointer',
  background: 'transparent',
  fontFamily: '"JetBrains Mono", monospace',
}

const statusBadgeStyle: React.CSSProperties = {
  padding: '4px 10px',
  fontSize: 11,
  border: '1px solid',
  borderRadius: 999,
  backgroundColor: EMBRY.bgDeep,
  fontFamily: '"JetBrains Mono", monospace',
  fontVariantNumeric: 'tabular-nums',
}

const contentAreaStyle: React.CSSProperties = {
  display: 'flex',
  flex: 1,
  overflow: 'hidden',
  minHeight: 0,
}

const collapsedPaneRailStyle: React.CSSProperties = {
  width: 44,
  flexShrink: 0,
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'center',
  paddingTop: 12,
  borderRight: `1px solid ${EMBRY.border}`,
  backgroundColor: EMBRY.bgPanel,
}

const collapsedPaneButtonStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 30,
  height: 30,
  padding: 0,
  borderRadius: 10,
  border: `1px solid ${EMBRY.border}`,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.dim,
  cursor: 'pointer',
}

const canvasContainerStyle: React.CSSProperties = {
  flex: 1,
  position: 'relative',
  overflow: 'hidden',
  backgroundColor: EMBRY.bgDeep,
  WebkitFontSmoothing: 'antialiased',
  MozOsxFontSmoothing: 'grayscale',
  display: 'flex',
  flexDirection: 'column',
  minWidth: 0,
  minHeight: 0,
}

const toolDockRowStyle: React.CSSProperties = {
  flexShrink: 0,
  display: 'flex',
  justifyContent: 'flex-start',
  padding: '10px 14px 0',
}

const canvasStageStyle: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  position: 'relative',
  overflow: 'hidden',
}

const toolDockStyle: React.CSSProperties = {
  position: 'relative',
  zIndex: 10,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: 6,
  borderRadius: 20,
  border: `1px solid rgba(255,255,255,0.08)`,
  backgroundColor: 'rgba(8, 11, 16, 0.82)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 10px 24px rgba(0, 0, 0, 0.26)',
}

const dockBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  justifyContent: 'flex-start',
  minHeight: 44,
  padding: '7px 10px',
  fontSize: 10,
  cursor: 'pointer',
  color: EMBRY.white,
  borderRadius: 10,
  border: `1px solid rgba(255,255,255,0.08)`,
  backgroundColor: 'rgba(8, 11, 16, 0.72)',
  fontVariantNumeric: 'tabular-nums',
}

const dockSelectStyle: React.CSSProperties = {
  backgroundColor: 'rgba(8, 11, 16, 0.72)',
  border: `1px solid rgba(255,255,255,0.08)`,
  color: EMBRY.white,
  fontSize: 10,
  padding: '7px 10px',
  outline: 'none',
  minWidth: 108,
  minHeight: 44,
  borderRadius: 12,
}

const viewportHudStyle: React.CSSProperties = {
  position: 'relative',
  zIndex: 10,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 8px',
  borderRadius: 16,
  border: `1px solid rgba(255,255,255,0.08)`,
  backgroundColor: 'rgba(8, 11, 16, 0.84)',
  backdropFilter: 'blur(14px)',
  boxShadow: '0 10px 24px rgba(0, 0, 0, 0.28)',
}

const viewportHudRowStyle: React.CSSProperties = {
  flexShrink: 0,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '0 14px 12px',
  gap: 12,
}

const viewportBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  minWidth: 44,
  minHeight: 44,
  padding: '7px 10px',
  cursor: 'pointer',
  border: `1px solid rgba(255,255,255,0.08)`,
  borderRadius: 10,
  color: EMBRY.white,
  backgroundColor: 'transparent',
}

const viewportDividerStyle: React.CSSProperties = {
  width: 1,
  alignSelf: 'stretch',
  backgroundColor: EMBRY.border,
  margin: '0 2px',
}



const contextualHudStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: 6,
  borderRadius: 16,
  border: `1px solid ${EMBRY.border}`,
  backgroundColor: 'rgba(8, 11, 16, 0.94)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 12px 24px rgba(0, 0, 0, 0.34)',
}

const contextualBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  padding: '6px 10px',
  fontSize: 10,
  cursor: 'pointer',
  color: EMBRY.white,
  borderRadius: 10,
  border: `1px solid ${EMBRY.border}`,
  backgroundColor: 'rgba(14, 18, 24, 0.92)',
}

const reviewQueueSectionStyle: React.CSSProperties = {
  marginBottom: 14,
  padding: 12,
  border: `1px solid rgba(255,255,255,0.07)`,
  backgroundColor: EMBRY.bgDeep,
  borderRadius: 16,
  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.18)',
}

const heroTaskSectionStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg, rgba(18, 24, 34, 0.98), rgba(10, 14, 20, 0.98))',
}

const inspectorModeCardStyle: React.CSSProperties = {
  marginBottom: 12,
  padding: 12,
  border: `1px solid rgba(255,255,255,0.07)`,
  background: 'linear-gradient(180deg, rgba(18, 24, 34, 0.98), rgba(10, 14, 20, 0.98))',
  borderRadius: 16,
  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.18)',
}

const inspectorModeCopyStyle: React.CSSProperties = {
  color: EMBRY.dim,
  fontSize: 11,
  lineHeight: 1.5,
}

const inspectorModeActionsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr',
  gap: 8,
  marginTop: 10,
}

const inspectorQueueModeStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  marginTop: 10,
  padding: '10px 12px',
  border: `1px solid rgba(255,255,255,0.08)`,
  borderRadius: 12,
  backgroundColor: 'rgba(255,255,255,0.025)',
  color: EMBRY.dim,
  fontSize: 11,
  lineHeight: 1.45,
}

const heroTaskCardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
}

const heroTaskHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
}

const heroTaskBandStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  border: '1px solid',
  borderRadius: 10,
  padding: '6px 10px',
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const heroTaskTitleStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  color: EMBRY.white,
  fontSize: 15,
  fontWeight: 700,
  lineHeight: 1.3,
  textWrap: 'balance',
}

const heroTaskNoteStyle: React.CSSProperties = {
  color: EMBRY.dim,
  fontSize: 12,
  lineHeight: 1.45,
}

const heroTaskActionsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 8,
}

const sidebarSectionTitleStyle: React.CSSProperties = {
  fontWeight: 700,
  color: EMBRY.white,
  fontSize: 12,
  marginBottom: 8,
}

const sidebarSubsectionLabelStyle: React.CSSProperties = {
  fontSize: 10,
  color: EMBRY.dim,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  marginBottom: 6,
}

const queueMetaRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 8,
  fontSize: 11,
}

const queueActionStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 44,
  marginTop: 8,
  backgroundColor: 'rgba(74, 158, 255, 0.14)',
  border: `1px solid ${EMBRY.blue}`,
  color: EMBRY.white,
  borderRadius: 10,
  padding: '10px 12px',
  fontSize: 11,
  cursor: 'pointer',
  textAlign: 'left',
  fontVariantNumeric: 'tabular-nums',
}

const inlineQueueLinkStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 8,
  background: EMBRY.bgDeep,
  color: EMBRY.accent,
  fontSize: 11,
  cursor: 'pointer',
  minHeight: 44,
  padding: '0 10px',
  fontWeight: 600,
}

const pageChipStyle: React.CSSProperties = {
  border: '1px solid',
  borderRadius: 999,
  padding: '6px 10px',
  minHeight: 44,
  fontSize: 11,
  cursor: 'pointer',
  fontFamily: '"JetBrains Mono", monospace',
  fontVariantNumeric: 'tabular-nums',
}

const queueListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
}

const queueBlockItemStyle: React.CSSProperties = {
  border: '1px solid',
  borderRadius: 10,
  minHeight: 44,
  padding: '9px 10px',
  textAlign: 'left',
  cursor: 'pointer',
  display: 'flex',
  flexDirection: 'column',
  gap: 3,
}

const queueBlockNoteStyle: React.CSSProperties = {
  fontSize: 10,
  color: EMBRY.dim,
  lineHeight: 1.35,
}

const emptyQueueTextStyle: React.CSSProperties = {
  fontSize: 11,
  color: EMBRY.dim,
}

const pageFocusMeterTrackStyle: React.CSSProperties = {
  width: '100%',
  height: 8,
  borderRadius: 999,
  marginTop: 10,
  overflow: 'hidden',
  backgroundColor: 'rgba(255,255,255,0.08)',
}

const pageFocusMeterFillStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 999,
  background: 'linear-gradient(90deg, rgba(124, 58, 237, 0.9), rgba(74, 158, 255, 0.9))',
}

const upcomingPageListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
}

const collapsedQueueSummaryStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 8,
  cursor: 'pointer',
  color: EMBRY.white,
  fontSize: 12,
  fontWeight: 600,
  listStyle: 'none',
}

const upcomingPageRowStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 10,
  minHeight: 44,
  padding: '10px 12px',
  backgroundColor: EMBRY.bgDeep,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  cursor: 'pointer',
  textAlign: 'left',
}

const btnStyle: React.CSSProperties = {
  background: 'transparent',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 4,
  padding: 4,
  cursor: 'pointer',
  color: EMBRY.dim,
  display: 'flex',
  alignItems: 'center',
}

const actionBtnStyle: React.CSSProperties = {
  ...btnStyle,
  minHeight: 44,
  padding: '5px 9px',
  gap: 5,
  color: EMBRY.white,
  fontSize: 10,
}

const fieldStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  padding: '4px 0',
  borderBottom: `1px solid ${EMBRY.border}`,
}

const labelStyle: React.CSSProperties = {
  color: EMBRY.dim,
}

const textPreviewStyle: React.CSSProperties = {
  marginTop: 4,
  padding: 8,
  backgroundColor: EMBRY.bgDeep,
  borderRadius: 4,
  fontSize: 10,
  maxHeight: 200,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  color: EMBRY.white,
  fontFamily: '"JetBrains Mono", monospace',
}

const qidListStyle: React.CSSProperties = {
  marginTop: 4,
  padding: 6,
  backgroundColor: EMBRY.bgDeep,
  borderRadius: 4,
  maxHeight: 80,
  overflow: 'auto',
}

const qidItemStyle: React.CSSProperties = {
  fontSize: 9,
  fontFamily: '"JetBrains Mono", monospace',
  color: EMBRY.accent,
  padding: '2px 0',
}

const tocListStyle: React.CSSProperties = {
  marginTop: 4,
  backgroundColor: EMBRY.bgDeep,
  borderRadius: 4,
  maxHeight: 300,
  overflow: 'auto',
}

const workflowRootStyle: React.CSSProperties = {
  height: '100vh',
  width: '100vw',
  overflow: 'hidden',
  display: 'grid',
  gridTemplateRows: '56px 1fr 48px',
  backgroundColor: '#000000',
  color: EMBRY.white,
  WebkitFontSmoothing: 'antialiased',
}

const workflowHeaderStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(260px, 1fr) auto minmax(260px, 1fr)',
  alignItems: 'center',
  gap: 12,
  padding: '0 20px',
  borderBottom: `1px solid ${EMBRY.border}`,
  background: 'rgba(15, 17, 23, 0.9)',
  position: 'relative',
  zIndex: 20,
}

const workflowHeaderProgressStyle: React.CSSProperties = {
  minWidth: 0,
  display: 'grid',
  gap: 3,
}

const workflowHeaderProgressTrackStyle: React.CSSProperties = {
  width: 286,
  maxWidth: '100%',
  height: 4,
  borderRadius: 999,
  backgroundColor: EMBRY.bgPanel,
  overflow: 'hidden',
  boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.06)',
}

const workflowHeaderProgressFillStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 999,
  background: `linear-gradient(90deg, ${EMBRY.accent}, ${EMBRY.blue})`,
  transitionProperty: 'width',
  transitionDuration: '180ms',
  transitionTimingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
}

const workflowHeaderProgressLabelStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: EMBRY.dim,
  fontSize: 10,
  fontVariantNumeric: 'tabular-nums',
}

const workflowHeaderTitleStyle: React.CSSProperties = {
  color: EMBRY.white,
  fontSize: 11,
  fontWeight: 800,
  textAlign: 'center',
  whiteSpace: 'nowrap',
}

const workflowHeaderActionsStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 6,
  minWidth: 0,
}

const workflowStatusPillStyle: React.CSSProperties = {
  minHeight: 24,
  display: 'inline-flex',
  alignItems: 'center',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 999,
  padding: '0 8px',
  color: EMBRY.dim,
  backgroundColor: EMBRY.bgDeep,
  fontSize: 10,
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
}

const workflowEyebrowStyle: React.CSSProperties = {
  color: EMBRY.accent,
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
}

const workflowTitleStyle: React.CSSProperties = {
  marginTop: 1,
  color: EMBRY.white,
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '-0.03em',
}

const workflowSubtitleStyle: React.CSSProperties = {
  marginTop: 3,
  color: EMBRY.dim,
  fontSize: 11,
}

const workflowMetricPillStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  minHeight: 44,
  padding: '0 12px',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 999,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
  fontSize: 11,
  fontVariantNumeric: 'tabular-nums',
}

const workflowSecondaryButtonStyle: React.CSSProperties = {
  minHeight: 36,
  padding: '0 12px',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 10,
  backgroundColor: 'rgba(7, 10, 15, 0.9)',
  color: EMBRY.white,
  fontSize: 10,
  cursor: 'pointer',
}

const workflowReviewBundleButtonStyle: React.CSSProperties = {
  minHeight: 32,
  padding: '0 10px',
  fontSize: 10,
  whiteSpace: 'nowrap',
}

const workflowMainStyle: React.CSSProperties = {
  minHeight: 0,
  display: 'block',
  padding: 0,
  overflow: 'hidden',
  position: 'relative',
}

const workflowLeftRailStyle: React.CSSProperties = {
  minHeight: 0,
  overflow: 'auto',
  display: 'grid',
  alignContent: 'start',
  gap: 12,
}

const workflowRightRailStyle: React.CSSProperties = {
  minHeight: 0,
  overflow: 'auto',
  display: 'grid',
  alignContent: 'start',
  gap: 12,
}

const workflowCenterStyle: React.CSSProperties = {
  minHeight: 0,
  overflow: 'hidden',
  display: 'grid',
  gridTemplateRows: 'auto 1fr',
  gap: 12,
}

const workflowPanelStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 18,
  backgroundColor: EMBRY.bgCard,
  padding: 12,
  boxShadow: '0 18px 38px rgba(0, 0, 0, 0.18)',
}

const workflowPanelHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 8,
  marginBottom: 10,
  color: EMBRY.white,
  fontSize: 12,
  fontWeight: 800,
}

const workflowPanelMetaStyle: React.CSSProperties = {
  color: EMBRY.dim,
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

const workflowPhaseListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
}

const workflowPhaseButtonStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '28px 1fr auto',
  alignItems: 'center',
  gap: 9,
  width: '100%',
  minHeight: 58,
  padding: 9,
  border: '1px solid',
  borderRadius: 14,
  color: EMBRY.white,
  cursor: 'pointer',
  textAlign: 'left',
}

const workflowPhaseIndexStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 999,
  backgroundColor: EMBRY.bgPanel,
  color: EMBRY.white,
  fontSize: 11,
  fontWeight: 800,
}

const workflowPhaseLabelStyle: React.CSSProperties = {
  display: 'block',
  color: EMBRY.white,
  fontSize: 12,
  fontWeight: 800,
}

const workflowPhaseSummaryStyle: React.CSSProperties = {
  display: 'block',
  marginTop: 2,
  color: EMBRY.dim,
  fontSize: 10,
  lineHeight: 1.3,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const workflowPhaseStatusStyle: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 800,
  textTransform: 'uppercase',
}

const workflowCandidateListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
}

const workflowCandidateButtonStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '42px 1fr auto',
  alignItems: 'center',
  gap: 9,
  minHeight: 54,
  width: '100%',
  padding: 9,
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 14,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
  cursor: 'pointer',
  textAlign: 'left',
}

const workflowCandidatePageStyle: React.CSSProperties = {
  width: 42,
  height: 36,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 12,
  backgroundColor: EMBRY.bgPanel,
  color: EMBRY.white,
  fontSize: 11,
  fontWeight: 800,
  fontVariantNumeric: 'tabular-nums',
}

const workflowCandidateTitleStyle: React.CSSProperties = {
  display: 'block',
  color: EMBRY.white,
  fontSize: 12,
  fontWeight: 800,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const workflowCandidateMetaStyle: React.CSSProperties = {
  display: 'block',
  marginTop: 2,
  color: EMBRY.dim,
  fontSize: 10,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const workflowGateBadgeStyle: React.CSSProperties = {
  border: '1px solid',
  borderRadius: 999,
  padding: '4px 8px',
  fontSize: 10,
  fontWeight: 800,
  textTransform: 'uppercase',
}

const workflowStageHeroStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) 170px 170px',
  gap: 10,
}

const workflowStageHeroCopyStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 18,
  backgroundColor: EMBRY.bgCard,
  padding: 14,
}

const workflowStageTitleStyle: React.CSSProperties = {
  margin: '4px 0 6px',
  color: EMBRY.white,
  fontSize: 22,
  lineHeight: 1.05,
  letterSpacing: '-0.04em',
}

const workflowMutedTextStyle: React.CSSProperties = {
  margin: 0,
  color: EMBRY.dim,
  fontSize: 11,
  lineHeight: 1.35,
}

const workflowGateCardStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.green}55`,
  borderRadius: 18,
  backgroundColor: EMBRY.bgCard,
  padding: 14,
  display: 'grid',
  gap: 6,
}

const workflowGapCardStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.amber}55`,
  borderRadius: 18,
  backgroundColor: EMBRY.bgCard,
  padding: 14,
  display: 'grid',
  gap: 6,
}

const workflowEvidenceShellStyle: React.CSSProperties = {
  minHeight: 0,
  overflow: 'hidden',
  height: '100%',
  border: 0,
  borderRadius: 0,
  backgroundColor: '#000000',
  display: 'grid',
  gridTemplateColumns: '1fr',
  gridTemplateRows: '1fr',
  position: 'relative',
}

const workflowEvidenceHeaderStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  display: 'none',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 8,
  padding: '0 18px',
  borderBottom: `1px solid rgba(255,255,255,0.05)`,
  backgroundColor: 'rgba(4, 6, 9, 0.72)',
  color: EMBRY.dim,
  fontSize: 10,
  position: 'relative',
  zIndex: 10,
}

const workflowCanvasStageStyle: React.CSSProperties = {
  minHeight: 0,
  height: '100%',
  width: '100%',
  position: 'relative',
  overflow: 'hidden',
  display: 'grid',
  placeItems: 'center',
  backgroundColor: '#000000',
}

const workflowEvidenceBodyStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  minHeight: 0,
  overflow: 'hidden',
}

const workflowQueuePaneFrameStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  display: 'none',
  minHeight: 0,
  height: '100%',
  overflow: 'hidden',
  borderRight: `1px solid ${EMBRY.border}`,
  backgroundColor: EMBRY.bgDeep,
}

const workflowQueueListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
  padding: '4px 8px 12px',
}

const workflowQueueCardStyle: React.CSSProperties = {
  width: '100%',
  display: 'grid',
  gridTemplateColumns: '42px minmax(0, 1fr)',
  gap: 8,
  alignItems: 'center',
  padding: '8px',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 12,
  backgroundColor: EMBRY.bgCard,
  color: EMBRY.dim,
  textAlign: 'left',
  cursor: 'pointer',
}

const workflowQueueCardActiveStyle: React.CSSProperties = {
  borderColor: `${EMBRY.accent}88`,
  backgroundColor: 'rgba(124, 58, 237, 0.16)',
  color: EMBRY.white,
}

const workflowQueueCardPageStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 10,
  padding: '7px 0',
  textAlign: 'center',
  color: EMBRY.white,
  fontSize: 10,
  fontWeight: 900,
  fontFamily: '"JetBrains Mono", monospace',
}

const workflowQueueCardBodyStyle: React.CSSProperties = {
  minWidth: 0,
  display: 'grid',
  gap: 2,
}

const workflowQueueCardKindStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: 'inherit',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'capitalize',
}

const workflowQueueCardMetaStyle: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: EMBRY.dim,
  fontSize: 9,
  fontFamily: '"JetBrains Mono", monospace',
  textTransform: 'uppercase',
}

const workflowHudBandStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  alignSelf: 'end',
  justifySelf: 'center',
  width: 'min(520px, calc(100% - 48px))',
  marginRight: 0,
  marginBottom: 40,
  display: 'grid',
  alignItems: 'stretch',
  justifyItems: 'stretch',
  position: 'relative',
  zIndex: 18,
  pointerEvents: 'none',
}

const workflowHotkeyHintStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  alignSelf: 'end',
  justifySelf: 'center',
  marginBottom: 12,
  position: 'relative',
  zIndex: 19,
  color: EMBRY.dim,
  fontSize: 10,
  letterSpacing: '0.08em',
  pointerEvents: 'none',
}

const workflowFooterStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  display: 'none',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
  padding: '0 24px',
  borderTop: `1px solid ${EMBRY.border}`,
  backgroundColor: 'rgba(10, 12, 16, 0.95)',
  color: EMBRY.dim,
  fontSize: 11,
  position: 'relative',
  zIndex: 18,
}

const workflowFooterNavStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  minWidth: 230,
}

const workflowFooterButtonStyle: React.CSSProperties = {
  width: 32,
  height: 32,
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 10,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
  cursor: 'pointer',
  fontSize: 14,
}

const workflowAgentDoubtCalloutStyle: React.CSSProperties = {
  gridColumn: 1,
  gridRow: 1,
  alignSelf: 'start',
  justifySelf: 'end',
  width: 360,
  marginTop: 142,
  marginRight: 294,
  position: 'relative',
  zIndex: 20,
  display: 'grid',
  gap: 2,
  color: '#f8e08e',
  fontSize: 11,
  lineHeight: 1.25,
  pointerEvents: 'none',
  fontFamily: '"JetBrains Mono", monospace',
}

const workflowAgentDoubtDotStyle: React.CSSProperties = {
  position: 'absolute',
  left: -86,
  top: 12,
  width: 8,
  height: 8,
  borderRadius: 999,
  backgroundColor: EMBRY.amber,
  boxShadow: `0 0 12px ${EMBRY.amber}`,
}

const workflowAgentDoubtLineStyle: React.CSSProperties = {
  position: 'absolute',
  left: -80,
  top: 15,
  width: 72,
  height: 1,
  backgroundColor: `${EMBRY.amber}99`,
}

const workflowAgentDoubtTitleStyle: React.CSSProperties = {
  color: '#fff1a8',
  fontSize: 11,
  fontWeight: 900,
}

const workflowAgentDoubtTextStyle: React.CSSProperties = {
  color: '#f8e08e',
  fontSize: 10,
}

const workflowKbdStyle: React.CSSProperties = {
  display: 'inline-grid',
  placeItems: 'center',
  minWidth: 18,
  height: 16,
  margin: '0 2px',
  borderRadius: 4,
  backgroundColor: EMBRY.bgPanel,
  color: EMBRY.white,
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: 9,
  fontWeight: 800,
}

const workflowDockedHudStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 0,
  display: 'grid',
  gridTemplateColumns: '1fr',
  gap: 14,
  padding: 20,
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 24,
  backgroundColor: 'rgba(18, 20, 27, 0.92)',
  boxShadow: '0 25px 50px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.05)',
  backdropFilter: 'blur(18px)',
  pointerEvents: 'auto',
}

const workflowHudCopyStyle: React.CSSProperties = {
  minWidth: 0,
  display: 'grid',
  alignContent: 'start',
  gap: 8,
}

const workflowHudControlsStyle: React.CSSProperties = {
  minWidth: 0,
  display: 'grid',
  alignContent: 'end',
  gap: 9,
}

const workflowAgentReadDetailsStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 12,
  backgroundColor: 'rgba(255,255,255,0.025)',
  overflow: 'hidden',
}

const workflowAgentReadSummaryStyle: React.CSSProperties = {
  cursor: 'pointer',
  padding: '6px 9px',
  color: EMBRY.dim,
  fontSize: 10,
  fontWeight: 900,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  fontFamily: '"JetBrains Mono", monospace',
}

const workflowAgentReadBodyStyle: React.CSSProperties = {
  padding: '0 9px 8px',
  color: '#cbd5e1',
  fontSize: 10,
  lineHeight: 1.35,
  maxHeight: 34,
  overflow: 'hidden',
}

const workflowDiagnosticsDetailsStyle: React.CSSProperties = {
  position: 'relative',
}

const workflowDiagnosticsSummaryStyle: React.CSSProperties = {
  width: 44,
  height: 44,
  display: 'grid',
  placeItems: 'center',
  listStyle: 'none',
  cursor: 'pointer',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 999,
  backgroundColor: EMBRY.bgDeep,
  color: EMBRY.white,
  fontSize: 13,
  fontWeight: 900,
}

const workflowDiagnosticsPopoverStyle: React.CSSProperties = {
  position: 'absolute',
  top: 52,
  right: 0,
  zIndex: 40,
  width: 360,
  maxHeight: 'calc(100vh - 110px)',
  overflow: 'auto',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 18,
  backgroundColor: 'rgba(14, 18, 25, 0.98)',
  boxShadow: '0 24px 80px rgba(0,0,0,0.65)',
  padding: 14,
}

const workflowDiagnosticsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr auto',
  gap: '8px 12px',
  color: EMBRY.dim,
  fontSize: 12,
  marginBottom: 14,
}

const workflowDiagnosticsPhaseListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
}

const workflowDiagnosticsPhaseButtonStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  width: '100%',
  minHeight: 36,
  padding: '7px 9px',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 10,
  backgroundColor: EMBRY.bgDeep,
  fontSize: 10,
  fontWeight: 800,
  cursor: 'pointer',
  textAlign: 'left',
}

const workflowTriageCardStyle: React.CSSProperties = {
  display: 'grid',
  gap: 12,
}

const workflowTriageSeverityRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
}

const workflowTriageQuestionStyle: React.CSSProperties = {
  margin: 0,
  color: EMBRY.white,
  fontSize: 17,
  lineHeight: 1.15,
  letterSpacing: '-0.035em',
  textWrap: 'balance',
}

const workflowIntentBoxStyle: React.CSSProperties = {
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 14,
  backgroundColor: '#000000',
  padding: 4,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const workflowIntentInputStyle: React.CSSProperties = {
  width: '100%',
  border: 0,
  outline: 'none',
  background: 'transparent',
  color: EMBRY.white,
  fontSize: 12,
  fontFamily: '"JetBrains Mono", monospace',
  padding: '9px 10px',
}

const workflowIntentModeStyle: React.CSSProperties = {
  flexShrink: 0,
  border: '1px solid',
  borderRadius: 999,
  padding: '5px 8px',
  fontSize: 9,
  fontWeight: 900,
  letterSpacing: '0.08em',
  fontFamily: '"JetBrains Mono", monospace',
}

const workflowTriageActionsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr 1.5fr',
  gap: 8,
}

const workflowActionButtonStyle: React.CSSProperties = {
  minHeight: 50,
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 14,
  backgroundColor: 'rgba(10, 14, 22, 0.72)',
  color: EMBRY.white,
  fontSize: 11,
  fontWeight: 800,
  fontFamily: '"JetBrains Mono", monospace',
  cursor: 'pointer',
  transitionProperty: 'transform, border-color, background-color, box-shadow',
  transitionDuration: '140ms',
  transitionTimingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
}

const workflowAcceptButtonStyle: React.CSSProperties = {
  borderColor: `${EMBRY.green}88`,
  color: '#b7ffe0',
  backgroundColor: 'rgba(0, 255, 136, 0.08)',
  boxShadow: 'inset 0 0 0 1px rgba(0, 255, 136, 0.08), 0 0 18px rgba(0, 255, 136, 0.08)',
}

const workflowLoadingStyle: React.CSSProperties = {
  width: '100vw',
  height: '100vh',
  display: 'grid',
  placeItems: 'center',
  backgroundColor: EMBRY.bg,
  color: EMBRY.white,
}

const workflowLoadingCardStyle: React.CSSProperties = {
  width: 'min(520px, 92vw)',
  border: `1px solid ${EMBRY.border}`,
  borderRadius: 22,
  backgroundColor: EMBRY.bgCard,
  padding: 24,
}

const workflowLoadingTitleStyle: React.CSSProperties = {
  margin: '6px 0 8px',
  color: EMBRY.white,
  fontSize: 24,
  letterSpacing: '-0.04em',
}


export default PdfLabView
