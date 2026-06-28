import { type KeyboardEvent, type MouseEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  BadgeCheck,
  CircleAlert,
  FileText,
  Heading,
  Eye,
  KeyRound,
  Link2,
  List,
  PanelBottom,
  PanelTop,
  Pilcrow,
  Quote,
  Table2,
  type LucideIcon,
} from 'lucide-react'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import { PdfLabEvidenceQA } from './PdfLabEvidenceQA'
import { PdfLabLabelingPage } from './PdfLabLabelingPage'
import { SurgicalTriageCleanRoom, type SurgicalTriageCleanRoomTask } from './SurgicalTriageCleanRoom'
import './PdfLabProductionWorkflow.css'

type WorkflowStage = 'initial-sweep' | 'parity-audit' | 'surgical-triage' | 'evidence-qa' | 'coverage' | 'labeling'

interface PdfLabProductionWorkflowProps {
  initialStage?: WorkflowStage
}

interface WorkflowManifest {
  artifact_gaps: unknown[]
  candidate_inventory: {
    candidate_page_count: number
    candidate_pages: CandidatePageArtifact[]
    source: string
  }
  document_family_preset: string
  element_summary: {
    total_elements?: number
    high_signal_pages?: Array<{
      element_count: number
      page: number
      types: Record<string, number>
    }>
  }
  evidence_elements_by_page: Record<string, EvidenceElement[]>
  evidence_artifacts?: {
    elements?: EvidenceArtifactElement[]
    manifest_uri?: string
  }
  gate: {
    status: string
    summary: string
    details?: {
      known_validation_accuracy?: number
      target?: number
      source?: string
    }
  }
  human_triage?: {
    task_count?: number
  }
  extraction_improvement?: {
    core_pdf_oxide_changed?: boolean
    explanation?: string
    preset_improved_pdf_oxide_behavior?: boolean
    preset?: {
      name?: string
      path?: string
      schema_version?: string
    }
    scope?: string
  }
  page_count: number
  source_comparison: string
  source_extraction: string
  source_pdf: string
}

interface EvidenceArtifactElement {
  bbox?: [number, number, number, number]
  crop_hash?: string
  crop_uri?: string
  element_id: string
  element_key?: string
  json_pointer?: string
  page: number
  page_image_hash?: string
  page_image_uri?: string
  source?: string
  text?: string
  type?: string
}

interface CandidatePageArtifact {
  element_count: number
  element_types: Record<string, number>
  gate_status: string
  inferred_match_score?: number | null
  page: number
  severity: string
  source: string
  task_count: number
  task_kinds: Record<string, number>
}

interface AgentResolvedFinding {
  agent_resolution?: string
  classification?: string
  finding_id: string
  kind: string
  page: number
  reason?: string
  recommended_engine_fix?: string
  severity?: string
  target_bbox?: [number, number, number, number]
  target_id?: string
}

interface CandidateAuditRow {
  arangoKey: string
  bbox?: [number, number, number, number]
  candidate?: CandidatePageArtifact
  correctedByAgent: boolean
  cropUri: string
  elementId: string
  elementText: string
  elementType: string
  finalState: 'pass' | 'fail' | 'warn'
  finding?: AgentResolvedFinding
  jsonPointer?: string
  memoryStatus: string
  page: number
  pageImageUri: string
  proofIssue: string
  proofLabel: string
  source: string
}

interface EvidenceElement {
  bbox?: [number, number, number, number]
  confidence?: number
  id: string
  page: number
  source?: string
  text?: string
  type: string
}

interface TriageQueue {
  page_count: number
  task_count: number
  agent_resolved_summary?: {
    finding_count?: number
    findings_by_kind?: Record<string, number>
    findings_by_severity?: Record<string, number>
  }
  agent_resolved_findings?: AgentResolvedFinding[]
  summary: {
    tasks_by_kind: Record<string, number>
    tasks_by_severity: Record<string, number>
    pages_with_tasks: number
  }
  human_triage_queue: TriageTaskArtifact[]
}

interface TriageTaskArtifact {
  agent_reasoning: string
  human_question: string
  kind: string
  page: number
  preview?: {
    text?: string
    type?: string
  }
  proposed_json_delta?: {
    before?: Record<string, unknown>
    after?: Record<string, unknown>
  }
  severity: string
  suggested_fix?: {
    action: string
    fallback_actions?: string[]
  }
  target_bbox?: [number, number, number, number]
  target_id: string
  task_id: string
}

interface ManualCandidate {
  page: number
  source: 'manual'
}

interface PdfLabExtractionJob {
  completedAt?: string
  createdAt: string
  error?: string
  exitCode?: number | null
  id: string
  logPath: string
  operation: string
  outputDir: string
  promoted?: {
    accuracy?: number
    candidate_pages?: number
    passed?: boolean
    triage_tasks?: number
  }
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  updatedAt: string
}

interface PdfLabJobResponse {
  async?: boolean
  job?: PdfLabExtractionJob
  logTail?: string
  ok: boolean
  promoted?: PdfLabExtractionJob['promoted']
}

interface ProductionData {
  manifest: WorkflowManifest
  triage: TriageQueue
  comparison: JsonComparison | null
  memoryQaReport: PdfLabMemoryQaReport | null
  statusReport: PdfLabStatusReport | null
  tocAudit: TocAudit | null
  coverageLoop: CoverageLoopReport | null
}

interface TocAudit {
  generated_at: string
  policy: {
    human_boundary: string
    match_threshold: number
    page_window: number
    purpose: string
  }
  rows: TocAuditRow[]
  schema_version: string
  summary: {
    agent_resolved_pages: number
    human_triage_pages: number
    match_rate: number
    matched_as_other_type: number
    matched_as_section_header: number
    matched_as_semantic_section_anchor?: number
    matched_toc_entries: number
    pdf_oxide_section_header_elements: number
    semantic_section_anchor_elements?: number
    toc_entries: number
    toc_backed_section_anchor_elements?: number
    unmatched_toc_entries: number
  }
}

interface TocAuditRow {
  action: string
  level: number
  page: number
  pdf_oxide_match: {
    element_id: string | null
    matched: boolean
    matched_as_section_header: boolean
    matched_as_semantic_section_anchor?: boolean
    page: number | null
    score: number
    text: string | null
    type: string | null
  }
  second_pass_status: string
  title: string
  toc_id: string
}

interface PdfLabStatusReport {
  artifact_paths: Record<string, { bytes: number; exists: boolean; path: string | null }>
  blockers: Array<{
    area: string
    detail: string
    next_action: string
    severity: 'critical' | 'high' | 'medium' | 'low'
  }>
  current_interpretation: string
  generated_at: string
  schema_version: string
  summary: {
    agent_resolved_count: number
    agent_resolved_kinds: Record<string, number>
    candidate_page_count: number
    core_pdf_oxide_changed: boolean
    document_family_preset?: { name?: string; path?: string; schema_version?: string } | string
    evidence_element_count: number
    evidence_page_count: number
    evidence_section_count?: number
    extraction_element_count: number
    human_triage_task_count: number
    matched_expected_elements: number
    page_count: number
    parity_accuracy: number
    parity_passed: boolean
    parity_target: number
    preset_improved_pdf_oxide_behavior: boolean
    memory_qa_implemented?: boolean
    memory_qa_passed?: boolean
    memory_qa_report_passed?: boolean
    memory_upsert_passed?: boolean
    memory_text_recall_passed?: boolean
    memory_visual_recall_passed?: boolean
    memory_crop_coverage_passed?: boolean
    memory_sample_checks?: number
    memory_sample_checks_passed?: number
    memory_text_indexed_total?: number
    memory_visual_indexed_total?: number
    memory_visual_indexed_pages?: number
    memory_visual_indexed_sections?: number
    memory_text_indexed_elements?: number
    memory_visual_required_elements?: number
    memory_visual_indexed_required_elements?: number
    memory_visual_optional_elements?: number
    memory_visual_indexed_optional_elements?: number
    memory_visual_indexed_elements?: number
    second_pass_backlog_count?: number
    toc_entries?: number
    toc_matched_entries?: number
    toc_matched_as_section_header?: number
    toc_matched_as_semantic_section_anchor?: number
    toc_type_repairs?: number
    toc_missing_entries?: number
    toc_match_rate?: number
    toc_audit_passed?: boolean
    total_expected_elements: number
    unmatched_actual_elements: number
    unmatched_expected_elements: number
  }
  trouble_report?: {
    agent_resolved_by_kind?: Record<string, number>
    agent_resolved_by_severity?: Record<string, number>
    missed_expected_by_type?: Record<string, number>
    unmatched_actual_sample_by_type?: Record<string, number>
  }
}

interface PdfLabMemoryQaReport {
  gates?: Array<{
    detail: string
    name: string
    passed: boolean
  }>
  passed?: boolean
  sample_checks?: MemoryQaSampleCheck[]
  summary?: {
    memory_upsert_applied?: boolean
    qdrant_collection?: string
    sample_checks?: number
    sample_checks_passed?: number
    visual_required_element_types?: string[]
  }
}

interface MemoryQaSampleCheck {
  element_key: string
  element_type: string
  page: number
  returned_keys?: string[]
  status: string
  text_hash?: string
}

interface CoverageLoopReport {
  active_blocker: {
    area: string
    detail: string
    next_action: string
    severity: string
  } | null
  active_plan_path: string | null
  blocker_count: number
  blocker_signature: string
  generated_at: string
  loop_safe_to_continue: boolean
  memory_recall_required: boolean
  must_stop_for_dogpile: boolean
  must_stop_for_interview: boolean
  next_action: 'complete' | 'new_plan' | 'amend_plan' | 'stop_interview' | 'stop_dogpile'
  project_knowledge_checked: boolean
  rationale: string
  recommended_command: string
  same_blocker_streak: number
  schema_version: string
}

interface JsonComparison {
  accuracy: number
  created_at: string
  matched_expected_elements: number
  matches: ComparisonMatch[]
  misses: ComparisonMiss[]
  passed: boolean
  schema_version: string
  subscores: Record<string, number>
  target: number
  total_expected_elements: number
  unmatched_actual_elements: number
  unmatched_actual_sample: ComparisonActual[]
  unmatched_expected_elements: number
}

interface ComparisonMatch {
  actual_id: string
  expected_id: string
  iou: number
  page: number
  score: number
  text_similarity: number
  type_compatible: boolean
}

interface ComparisonMiss {
  bbox?: [number, number, number, number]
  best_candidate?: {
    iou?: number
    score?: number
    text_similarity?: number
  }
  expected_id: string
  page: number
  reason: string
  text?: string
  type: string
}

interface ComparisonActual {
  bbox?: [number, number, number, number]
  id: string
  page: number
  source?: string
  text?: string
  type: string
}

type ConvergenceClarification =
  | 'single_table_wrong_bounds'
  | 'split_table_across_extracts'
  | 'not_a_table'
  | 'paragraph_crop_truncated'
  | 'paragraph_crop_correct'
  | 'caption_wrong_target'
  | 'caption_association_correct'
  | 'list_structure_wrong'
  | 'list_structure_correct'
  | 'extraction_bounds_wrong'
  | 'extraction_correct'
  | 'need_more_evidence'

type ConvergenceClarificationOption = { label: string; value: ConvergenceClarification }

const TABLE_CLARIFICATION_OPTIONS: ConvergenceClarificationOption[] = [
  { label: 'Single table, wrong bounds', value: 'single_table_wrong_bounds' },
  { label: 'Split table across extracts', value: 'split_table_across_extracts' },
  { label: 'Not a table', value: 'not_a_table' },
  { label: 'Need more evidence', value: 'need_more_evidence' },
]

const PARAGRAPH_CLARIFICATION_OPTIONS: ConvergenceClarificationOption[] = [
  { label: 'Text continues past crop', value: 'paragraph_crop_truncated' },
  { label: 'Paragraph crop is correct', value: 'paragraph_crop_correct' },
  { label: 'Wrong text region', value: 'extraction_bounds_wrong' },
  { label: 'Need more evidence', value: 'need_more_evidence' },
]

const CAPTION_CLARIFICATION_OPTIONS: ConvergenceClarificationOption[] = [
  { label: 'Caption attached to wrong target', value: 'caption_wrong_target' },
  { label: 'Caption association is correct', value: 'caption_association_correct' },
  { label: 'Wrong crop or bounds', value: 'extraction_bounds_wrong' },
  { label: 'Need more evidence', value: 'need_more_evidence' },
]

const LIST_CLARIFICATION_OPTIONS: ConvergenceClarificationOption[] = [
  { label: 'List structure is wrong', value: 'list_structure_wrong' },
  { label: 'List structure is correct', value: 'list_structure_correct' },
  { label: 'Wrong crop or bounds', value: 'extraction_bounds_wrong' },
  { label: 'Need more evidence', value: 'need_more_evidence' },
]

const WORKFLOW_VERSION = '20260504-list-control-reference-v1'
const PDF_LAB_ARTIFACT_BASE_URL = '/artifacts/pdf-lab'
const MANIFEST_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-workflow-manifest.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const TRIAGE_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-human-triage-queue.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const COMPARISON_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-comparison.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const STATUS_REPORT_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-status-report.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const COVERAGE_LOOP_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-coverage-loop.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const TOC_AUDIT_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-toc-audit.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const MEMORY_QA_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-memory-qa-report.json?pdfLabWorkflow=${WORKFLOW_VERSION}`
const PDF_URL = `${PDF_LAB_ARTIFACT_BASE_URL}/NIST_SP_800-53r5.pdf`

const FAMILY_LABELS: Record<string, string> = {
  caption: 'Captions',
  control_reference: 'Control References',
  figure: 'Figures',
  list: 'Lists',
  list_item: 'List Items',
  paragraph: 'Paragraphs',
  requirement: 'Requirements',
  running_footer: 'Running Footers',
  running_header: 'Running Headers',
  section_header: 'Section Headers',
  table: 'Tables',
}

function normalizeInitialStage(initialStage?: WorkflowStage): WorkflowStage {
  return initialStage ?? 'evidence-qa'
}

function getHashTriageTaskId(): string | null {
  const parts = window.location.hash.replace(/^#/, '').split('/')
  const stageIndex = parts.findIndex(part => part === 'surgical-triage' || part === 'triage')
  const encodedTaskId = stageIndex >= 0 ? parts[stageIndex + 1] : undefined
  return encodedTaskId ? decodeURIComponent(encodedTaskId) : null
}

function pdfLabStageHash(stage: WorkflowStage, taskId?: string | null): string {
  if (stage === 'surgical-triage' && taskId) {
    return `#pdf-lab/surgical-triage/${encodeURIComponent(taskId)}`
  }
  return `#pdf-lab/${stage}`
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(`Failed to load ${url}: ${response.status}`)
  return response.json() as Promise<T>
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : response.statusText
    throw new Error(`${url} failed: ${detail}`)
  }
  return payload as T
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

function formatFamily(type: string): string {
  return FAMILY_LABELS[type] ?? type.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

function getCandidateFamilies(candidate: CandidatePageArtifact): string[] {
  return Object.entries(candidate.element_types)
    .filter(([, count]) => count > 0)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 3)
    .map(([type]) => formatFamily(type))
}

function getPrimaryPreset(candidate: CandidatePageArtifact): string {
  const matchedPresets = (candidate as CandidatePageArtifact & { matched_presets?: string[] }).matched_presets
  if (Array.isArray(matchedPresets) && matchedPresets.length > 0) return matchedPresets[0]
  if (candidate.element_types.table) return 'table'
  if (candidate.element_types.requirement) return 'requirement'
  if (candidate.element_types.list_item) return 'list_item'
  if (candidate.element_types.caption) return 'caption'
  if (candidate.element_types.section_header) return 'section_header'
  return Object.keys(candidate.element_types)[0] ?? 'unknown'
}

function getSweepEvidence(candidate: CandidatePageArtifact): string {
  const sweepEvidence = (candidate as CandidatePageArtifact & { sweep_evidence?: string[] }).sweep_evidence
  if (Array.isArray(sweepEvidence) && sweepEvidence.length > 0) return sweepEvidence.slice(0, 2).join(' · ')
  return `${candidate.task_count} tasks · ${candidate.gate_status}`
}

function getEvidenceForPage(manifest: WorkflowManifest, page: number): EvidenceElement[] {
  return manifest.evidence_elements_by_page[String(page - 1)]
    ?? manifest.evidence_elements_by_page[String(page)]
    ?? []
}

function getPresetScanThumbnailUrl(page: number): string {
  return `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-nist-preset-scan/page_${page}.png`
}

function getEvidencePageImageUri(page: number): string {
  return `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-evidence/pdf-lab-toc-repair-20260503T124447Z/pages/page-${String(page).padStart(4, '0')}.png`
}

function toPublicEvidenceUri(uri?: string): string {
  if (!uri) return ''
  const storagePrefix = '/mnt/storage12tb/pdf-lab/evidence/'
  const publicPrefix = '/home/graham/workspace/experiments/pi-mono/packages/ux-lab/public/'
  if (uri.startsWith(storagePrefix)) return `${PDF_LAB_ARTIFACT_BASE_URL}/pdf-lab-evidence/${uri.slice(storagePrefix.length)}`
  if (uri.startsWith(publicPrefix)) return `${PDF_LAB_ARTIFACT_BASE_URL}/${uri.slice(publicPrefix.length)}`
  return uri
}

function getBboxStyle(bbox?: [number, number, number, number]) {
  if (!bbox) return undefined
  const [left, top, right, bottom] = bbox
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${Math.max(0, right - left) * 100}%`,
    height: `${Math.max(0, bottom - top) * 100}%`,
  }
}

function elementSortScore(element: EvidenceArtifactElement): number {
  const text = String(element.text ?? '')
  if (element.type === 'section_header' && /^3\.\d+\s+[A-Z]/.test(text)) return -1200
  if (element.type === 'section_header' && /^\d+\.\d+\s+[A-Z]/.test(text)) return -1000
  if (element.type === 'table' && text.includes('CONTROL\\nNUMBER')) return -1000
  if (element.type === 'table' && text.includes('CONTROL')) return -900
  if (element.type === 'caption' && text.toLowerCase().includes('table')) return -100
  if (element.type === 'list') return -95
  if (element.type === 'control_reference' && /^[A-Z]{2}-\d+/.test(text)) return -90
  return element.page
}

function isValidCoverageProofElement(element: EvidenceArtifactElement): boolean {
  const text = String(element.text ?? '').trim()
  if (!element.crop_uri || text.length <= 2) return false
  if (element.type === 'section_header') {
    return element.page > 20 && /^\d+\.\d+\s+[A-Z]/.test(text)
  }
  if (element.type === 'table') {
    return text.includes('CONTROL\\nNUMBER') || text.includes('CONTROL NAME') || element.page > 400
  }
  if (element.type === 'requirement') {
    return text.length > 30 && /\b(shall|must|required|requirement|organization-defined)\b/i.test(text)
  }
  if (element.type === 'control_reference') {
    return /^[A-Z]{2}-\d+(?:\(\d+\))?$/.test(text)
  }
  if (element.type === 'list') {
    return element.page > 10 && text.includes('\n') && text.length > 80
  }
  if (element.type === 'paragraph') {
    return element.page > 20 && text.length > 40
  }
  if (element.type === 'caption') {
    return element.page > 10 && /table|figure|appendix|contents/i.test(text)
  }
  return true
}

function buildCandidateAuditRows(manifest: WorkflowManifest, triage: TriageQueue): CandidateAuditRow[] {
  const candidateByPage = new Map(manifest.candidate_inventory.candidate_pages.map(candidate => [candidate.page, candidate]))
  const artifactElements = manifest.evidence_artifacts?.elements ?? []
  const desiredTypes = ['table', 'list', 'control_reference', 'caption', 'section_header', 'paragraph', 'running_header', 'running_footer']
  const rows: CandidateAuditRow[] = []

  for (const type of desiredTypes) {
    const elements = artifactElements
      .filter(element => element.type === type && isValidCoverageProofElement(element))
      .sort((left, right) => elementSortScore(left) - elementSortScore(right))
      .slice(0, 3)

    for (const element of elements) {
      const finding = triage.agent_resolved_findings?.find(item => item.target_id === element.element_id || item.page === element.page)
      const candidate = candidateByPage.get(element.page)
      const correctedByAgent = Boolean(finding)
      const hasOpenCandidateWork = (candidate?.task_count ?? 0) > 0
      const hasInspectableArtifacts = Boolean(element.crop_uri && element.page_image_uri && element.json_pointer)
      const finalState: CandidateAuditRow['finalState'] = hasOpenCandidateWork || correctedByAgent
        ? 'fail'
        : hasInspectableArtifacts
          ? 'warn'
          : 'fail'
      const proofLabel = finalState === 'fail' ? 'needs review' : 'sample only'
      const proofIssue = hasOpenCandidateWork
        ? `${candidate?.task_count ?? 0} candidate task${candidate?.task_count === 1 ? '' : 's'} remain on this page`
        : correctedByAgent
          ? finding?.reason ?? 'Agent-resolved finding exists for this element or page'
          : hasInspectableArtifacts
            ? 'Visual crop and extracted payload are inspectable; final pass still requires Memory/Qdrant recall QA'
            : 'Required crop, page image, or JSON pointer is missing'
      rows.push({
        arangoKey: element.element_key ?? `pdf_elements/${element.element_id}`,
        bbox: element.bbox,
        candidate,
        correctedByAgent,
        cropUri: toPublicEvidenceUri(element.crop_uri),
        elementId: element.element_id,
        elementText: String(element.text ?? ''),
        elementType: element.type ?? 'element',
        finalState,
        finding,
        jsonPointer: element.json_pointer,
        memoryStatus: 'provenance key only; recall status comes from Memory/Qdrant QA',
        page: element.page,
        pageImageUri: toPublicEvidenceUri(element.page_image_uri) || getEvidencePageImageUri(element.page),
        proofIssue,
        proofLabel,
        source: element.source ?? 'pdf_oxide',
      })
    }
  }

  return rows
}

function getDefaultClarification(row: CandidateAuditRow): ConvergenceClarification {
  const issue = `${row.proofIssue} ${row.elementText} ${row.finding?.kind ?? ''}`.toLowerCase()
  if (row.elementType === 'paragraph') return 'paragraph_crop_truncated'
  if (row.elementType === 'caption') return 'caption_wrong_target'
  if (row.elementType === 'list') return 'list_structure_wrong'
  if (issue.includes('split')) return 'split_table_across_extracts'
  if (issue.includes('false positive') || issue.includes('not a table')) return 'not_a_table'
  if (issue.includes('missing') || issue.includes('more evidence')) return 'need_more_evidence'
  return 'single_table_wrong_bounds'
}

function getClarificationOptions(row: CandidateAuditRow): ConvergenceClarificationOption[] {
  if (row.elementType === 'paragraph') return PARAGRAPH_CLARIFICATION_OPTIONS
  if (row.elementType === 'caption') return CAPTION_CLARIFICATION_OPTIONS
  if (row.elementType === 'list') return LIST_CLARIFICATION_OPTIONS
  if (row.elementType === 'table') return TABLE_CLARIFICATION_OPTIONS
  return [
    { label: `${formatFamily(row.elementType)} bounds are wrong`, value: 'extraction_bounds_wrong' },
    { label: `${formatFamily(row.elementType)} extraction is correct`, value: 'extraction_correct' },
    { label: 'Reject as non-issue', value: 'not_a_table' },
    { label: 'Need more evidence', value: 'need_more_evidence' },
  ]
}

function getPrimaryDecisionAction(clarification: ConvergenceClarification) {
  if (clarification === 'not_a_table') {
    return {
      action: 'PDF_LAB_CONVERGENCE_REJECT_NON_ISSUE',
      decision: 'rejected_non_issue',
      label: 'Reject non-issue',
      title: 'Reject this candidate because the selected extraction is not an issue',
    }
  }
  if (
    clarification === 'paragraph_crop_correct'
    || clarification === 'caption_association_correct'
    || clarification === 'list_structure_correct'
    || clarification === 'extraction_correct'
  ) {
    return {
      action: 'PDF_LAB_CONVERGENCE_ACCEPT_EXTRACTION',
      decision: 'accepted_extraction',
      label: 'Accept extraction as correct',
      title: 'Accept the current deterministic extraction as correct',
    }
  }
  if (clarification === 'need_more_evidence') {
    return {
      action: 'PDF_LAB_CONVERGENCE_REQUEST_MORE_EVIDENCE',
      decision: 'needs_more_evidence',
      label: 'Request more evidence',
      title: 'Request more visual or extraction evidence before resolving this case',
    }
  }
  return {
    action: 'PDF_LAB_CONVERGENCE_CONFIRM_EXTRACTOR_FAILURE',
    decision: 'confirmed_extractor_failure',
    label: 'Confirm extractor failure',
    title: 'Confirm that this candidate is a real deterministic extractor failure',
  }
}

function getConvergenceCaseSummary(row: CandidateAuditRow) {
  const family = formatFamily(row.elementType)
  if (row.elementType === 'table') {
    return {
      actual: `pdf_oxide emitted ${row.elementId} with extracted table evidence; the current issue is ${row.proofIssue.toLowerCase()}.`,
      delta: 'Bounds likely capture only a repeated table row instead of the full table region.',
      expected: 'One 4-column control table: Control Number, Control Name, Implemented By, Assurance.',
      failureType: 'Table bounds',
      familyLabel: 'Table structure',
      hypothesis: 'the extractor captured only a repeated row as the table region.',
      question: 'Is this a single table with incorrect bounds?',
      title: 'Table bounds',
    }
  }
  if (row.elementType === 'paragraph') {
    return {
      actual: `pdf_oxide emitted ${row.elementId} as paragraph text on p${row.page}.`,
      delta: 'The crop may truncate visible continuation text or overrun the intended paragraph region.',
      expected: 'One contiguous paragraph region with complete visible text and correct bounds.',
      failureType: 'Paragraph crop',
      familyLabel: 'Paragraph structure',
      hypothesis: 'the detected paragraph crop may not cover the complete visible text region.',
      question: 'Does this paragraph continue beyond the detected crop?',
      title: 'Paragraph crop',
    }
  }
  if (row.elementType === 'caption') {
    return {
      actual: `pdf_oxide emitted ${row.elementId} as a caption on p${row.page}.`,
      delta: 'The caption may be associated with the wrong neighboring table or figure.',
      expected: 'Caption text associated with the correct table or figure on the same page region.',
      failureType: 'Caption association',
      familyLabel: 'Caption association',
      hypothesis: 'the caption may be attached to the wrong visual element.',
      question: 'Is this caption attached to the wrong table?',
      title: 'Caption mismatch',
    }
  }
  if (row.elementType === 'list') {
    return {
      actual: `pdf_oxide emitted ${row.elementId} as list structure on p${row.page}.`,
      delta: 'The list hierarchy or item grouping may not match the visible document structure.',
      expected: 'Visible list items represented with correct nesting, order, and bounds.',
      failureType: 'List structure',
      familyLabel: 'List structure',
      hypothesis: 'the extracted list may merge, split, or mis-order visible list items.',
      question: 'Does this list structure match the visible page?',
      title: 'List structure',
    }
  }
  return {
    actual: `pdf_oxide emitted ${row.elementId} as ${family} on p${row.page}.`,
    delta: row.proofIssue,
    expected: `One visually inspectable ${family.toLowerCase()} element with correct bounds and extracted payload.`,
    failureType: family,
    familyLabel: family,
    hypothesis: row.proofIssue.charAt(0).toLowerCase() + row.proofIssue.slice(1),
    question: `Is this ${family.toLowerCase()} extraction correct?`,
    title: family,
  }
}

function buildCandidateFamilySummary(rows: CandidateAuditRow[]): string {
  const totals = new Map<string, number>()
  for (const row of rows) {
    totals.set(row.elementType, (totals.get(row.elementType) ?? 0) + 1)
  }
  return Array.from(totals.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8)
    .map(([type, count]) => `${formatFamily(type)} ${count.toLocaleString()}`)
    .join(' · ')
}

function collapseRowsToConvergenceCases(rows: CandidateAuditRow[]): CandidateAuditRow[] {
  const cases = new Map<string, CandidateAuditRow>()
  for (const row of rows) {
    const summary = getConvergenceCaseSummary(row)
    const key = `${row.page}:${row.elementType}:${summary.failureType}`
    const current = cases.get(key)
    if (!current || row.finalState === 'fail' || (row.candidate?.task_count ?? 0) > (current.candidate?.task_count ?? 0)) {
      cases.set(key, row)
    }
  }
  return Array.from(cases.values())
}

function getConvergenceCardDescription(row: CandidateAuditRow): string {
  if (row.page === 457 && row.elementType === 'table') return 'Possible repeated row bounds bug; likely one table.'
  if (row.page === 458 && row.elementType === 'table') return 'Headers and body may be split across two extracts.'
  if (row.elementType === 'paragraph') return 'Text appears truncated past right boundary.'
  if (row.elementType === 'caption') return 'Caption may be attached to wrong table.'
  return getConvergenceCaseSummary(row).hypothesis
}

function buildFamilyTallies(manifest: WorkflowManifest): Array<[string, number]> {
  const tallies = new Map<string, number>()
  for (const evidence of Object.values(manifest.evidence_elements_by_page).flat()) {
    tallies.set(evidence.type, (tallies.get(evidence.type) ?? 0) + 1)
  }
  if (tallies.size === 0) {
    for (const candidate of manifest.candidate_inventory.candidate_pages) {
      for (const [type, count] of Object.entries(candidate.element_types)) {
        tallies.set(type, (tallies.get(type) ?? 0) + count)
      }
    }
  }
  return Array.from(tallies.entries())
    .sort((left, right) => right[1] - left[1])
    .map(([type, count]) => [formatFamily(type), count])
}

function getCoverageElementIcon(type: string): LucideIcon {
  const normalizedType = type.toLowerCase()
  if (normalizedType.includes('table')) return Table2
  if (normalizedType.includes('list')) return List
  if (normalizedType.includes('control_reference')) return Link2
  if (normalizedType.includes('caption')) return Quote
  if (normalizedType.includes('section_header')) return Heading
  if (normalizedType.includes('paragraph')) return Pilcrow
  if (normalizedType.includes('running_header')) return PanelTop
  if (normalizedType.includes('running_footer')) return PanelBottom
  return FileText
}

function getCoverageProofIcon(state: CandidateAuditRow['finalState']): LucideIcon {
  if (state === 'pass') return BadgeCheck
  if (state === 'fail') return CircleAlert
  return Eye
}

function buildTriageTask(task: TriageTaskArtifact): SurgicalTriageCleanRoomTask {
  const action = task.suggested_fix?.action
  const isBoundsCheck = task.kind === 'comparison_miss' && action === 'FIX_BBOX'
  const target = task.target_id
  const previewType = task.preview?.type ? String(task.preview.type).replace(/_/g, ' ') : 'element'
  const previewText = task.preview?.text ? `“${task.preview.text}”` : 'the highlighted text'
  return {
    id: task.task_id,
    question: isBoundsCheck
      ? 'Bounds check: does this highlight cover the right PDF evidence?'
      : task.human_question,
    reasoning: isBoundsCheck
      ? `This is not a table/not-table decision. The JSON comparison says the type is compatible; only the bbox alignment is unresolved for ${target}. Confirm whether ${previewText} is the correct ${previewType} evidence region.`
      : task.agent_reasoning,
    path: `NIST › Page ${task.page} › ${task.kind.replace(/_/g, ' ')}`,
    severity: task.severity,
    bbox: task.target_bbox ?? [0.12, 0.2, 0.72, 0.82],
  }
}

function summarizeDelta(task: TriageTaskArtifact): { before: string; after: string } {
  const before = task.proposed_json_delta?.before ?? {}
  const after = task.proposed_json_delta?.after ?? {}
  return {
    before: String(before.type ?? before.reviewStatus ?? before.id ?? 'pending'),
    after: String(after.type ?? after.reviewStatus ?? after.id ?? task.suggested_fix?.action ?? 'review'),
  }
}

function buildComparisonRows(comparison: JsonComparison | null) {
  if (!comparison) return []
  const missingRows = comparison.misses.slice(0, 24).map(miss => ({
    id: miss.expected_id,
    page: miss.page,
    expected: miss.type,
    actual: miss.best_candidate ? `best score ${miss.best_candidate.score?.toFixed(3) ?? 'n/a'}` : 'none',
    status: 'missing' as const,
    detail: miss.reason,
  }))
  const extraRows = comparison.unmatched_actual_sample.slice(0, Math.max(0, 24 - missingRows.length)).map(actual => ({
    id: actual.id,
    page: actual.page,
    expected: 'none',
    actual: actual.type,
    status: 'extra' as const,
    detail: actual.text ?? actual.source ?? 'unmatched actual element',
  }))
  const matchRows = comparison.matches.slice(0, Math.max(0, 24 - missingRows.length - extraRows.length)).map(match => ({
    id: match.expected_id,
    page: match.page,
    expected: match.expected_id,
    actual: match.actual_id,
    status: 'matched' as const,
    detail: `score ${match.score.toFixed(3)} · text ${match.text_similarity.toFixed(3)} · IoU ${match.iou.toFixed(3)}`,
  }))
  return [...missingRows, ...extraRows, ...matchRows]
}

function buildComparisonPageStats(comparison: JsonComparison | null) {
  const byPage = new Map<number, { extra: number; matched: number; missing: number }>()
  if (!comparison) return byPage
  for (const match of comparison.matches) {
    const stats = byPage.get(match.page) ?? { extra: 0, matched: 0, missing: 0 }
    stats.matched += 1
    byPage.set(match.page, stats)
  }
  for (const miss of comparison.misses) {
    const stats = byPage.get(miss.page) ?? { extra: 0, matched: 0, missing: 0 }
    stats.missing += 1
    byPage.set(miss.page, stats)
  }
  for (const actual of comparison.unmatched_actual_sample) {
    const stats = byPage.get(actual.page) ?? { extra: 0, matched: 0, missing: 0 }
    stats.extra += 1
    byPage.set(actual.page, stats)
  }
  return byPage
}

function buildCandidateRunRows(comparison: JsonComparison | null, candidates: CandidatePageArtifact[]) {
  const pageStats = buildComparisonPageStats(comparison)
  const candidatesByPage = new Map(candidates.map(candidate => [candidate.page, candidate]))
  if (!comparison) {
    return candidates.slice(0, 16).map(candidate => ({
      elementCount: candidate.element_count,
      extra: 0,
      matched: 0,
      missing: 0,
      page: candidate.page,
      preset: getPrimaryPreset(candidate),
      triageTasks: candidate.task_count,
    }))
  }
  return Array.from(pageStats.entries())
    .map(([page, stats]) => {
      const candidate = candidatesByPage.get(page)
      return {
        elementCount: candidate?.element_count ?? stats.matched + stats.missing + stats.extra,
        extra: stats.extra,
        matched: stats.matched,
        missing: stats.missing,
        page,
        preset: candidate ? getPrimaryPreset(candidate) : 'agent_oracle',
        triageTasks: candidate?.task_count ?? 0,
      }
    })
    .sort((left, right) => (right.missing + right.extra) - (left.missing + left.extra) || left.page - right.page)
    .slice(0, 16)
}

export function PdfLabProductionWorkflow({ initialStage }: PdfLabProductionWorkflowProps) {
  useRegisterAction('pdf-lab:production:stage-initial-sweep', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_INITIAL_SWEEP',
    label: 'Open Initial Sweep',
    description: 'Show preset discovery, candidate pages, and evidence preview',
  })
  useRegisterAction('pdf-lab:production:stage-parity-audit', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_PARITY_AUDIT',
    label: 'Open Parity Audit',
    description: 'Show deterministic extraction comparison and triage output',
  })
  useRegisterAction('pdf-lab:production:stage-surgical-triage', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_SURGICAL_TRIAGE',
    label: 'Open Surgical Triage',
    description: 'Open the final human ambiguity deck',
  })
  useRegisterAction('pdf-lab:production:stage-evidence-qa', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_EVIDENCE_QA',
    label: 'Open Evidence QA',
    description: 'Open the final Nico evidence QA gate using real PDF crops and extracted JSON',
  })
  useRegisterAction('pdf-lab:production:stage-coverage', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_COVERAGE',
    label: 'Open Coverage / Status',
    description: 'Show artifact-derived PDF Lab blockers and definition-of-done gates',
  })
  useRegisterAction('pdf-lab:production:stage-labeling', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_STAGE_LABELING',
    label: 'Open Labeling',
    description: 'Manually draw and label expected elements on a rendered PDF page',
  })
  useRegisterAction('pdf-lab:production:add-page', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_ADD_PAGE_TO_CANDIDATES',
    label: 'Add Page to Candidates',
    description: 'Manually add a known page to the candidate extraction queue',
  })
  useRegisterAction('pdf-lab:production:commit-sweep', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_COMMIT_SWEEP',
    label: 'Commit Sweep to Run',
    description: 'Commit discovered candidate pages to the deterministic pdf_oxide run',
  })
  useRegisterAction('pdf-lab:production:bulk-rerun', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_BULK_REPAIR_RERUN',
    label: 'Bulk Repair / Re-run',
    description: 'Repair systemic extraction settings and re-run candidate pages',
  })
  useRegisterAction('pdf-lab:production:eject-triage', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_EJECT_MISMATCHES_TO_TRIAGE',
    label: 'Eject Mismatches to Triage',
    description: 'Create human triage cards only for unresolved mismatches',
  })
  useRegisterAction('pdf-lab:production:promote-direct-run', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PRODUCTION_PROMOTE_DIRECT_RUN',
    label: 'Promote Direct Run',
    description: 'Promote a direct pdf_oxide output directory into UX Lab artifacts',
  })

  const [stage, setStage] = useState<WorkflowStage>(() => normalizeInitialStage(initialStage))
  const [data, setData] = useState<ProductionData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedPage, setSelectedPage] = useState<number | null>(null)
  const [manualCandidates, setManualCandidates] = useState<ManualCandidate[]>([])
  const [triageIndex, setTriageIndex] = useState(0)
  const [intentDraft, setIntentDraft] = useState('')
  const [lastDecision, setLastDecision] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [currentJob, setCurrentJob] = useState<PdfLabExtractionJob | null>(null)
  const [jobLogTail, setJobLogTail] = useState<string>('')
  const [candidateAuditRow, setCandidateAuditRow] = useState<CandidateAuditRow | null>(null)

  useEffect(() => {
    setStage(normalizeInitialStage(initialStage))
  }, [initialStage])

  const loadArtifacts = useCallback(async (cancelled?: () => boolean) => {
    setError(null)
    const [manifest, triage, comparison, memoryQaReport, statusReport, tocAudit, coverageLoop] = await Promise.all([
      fetchJson<WorkflowManifest>(MANIFEST_URL),
      fetchJson<TriageQueue>(TRIAGE_URL),
      fetchJson<JsonComparison>(COMPARISON_URL).catch(() => null),
      fetchJson<PdfLabMemoryQaReport>(MEMORY_QA_URL).catch(() => null),
      fetchJson<PdfLabStatusReport>(STATUS_REPORT_URL).catch(() => null),
      fetchJson<TocAudit>(TOC_AUDIT_URL).catch(() => null),
      fetchJson<CoverageLoopReport>(COVERAGE_LOOP_URL).catch(() => null),
    ])
    if (cancelled?.()) return
    setData({ manifest, triage, comparison, memoryQaReport, statusReport, tocAudit, coverageLoop })
    setSelectedPage(current => current ?? manifest.candidate_inventory.candidate_pages[0]?.page ?? null)
  }, [])

  useEffect(() => {
    let cancelled = false
    loadArtifacts(() => cancelled).catch((err: Error) => {
      if (!cancelled) setError(err.message)
    })
    return () => { cancelled = true }
  }, [loadArtifacts])

  const openStage = useCallback((nextStage: WorkflowStage, taskId?: string | null) => {
    setStage(nextStage)
    const activeTaskId = taskId
      ?? (nextStage === 'surgical-triage'
        ? data?.triage.human_triage_queue[triageIndex]?.task_id ?? data?.triage.human_triage_queue[0]?.task_id
        : null)
    window.history.replaceState(null, '', pdfLabStageHash(nextStage, activeTaskId))
  }, [data?.triage.human_triage_queue, triageIndex])

  const goToTriageIndex = useCallback((nextIndex: number) => {
    const queue = data?.triage.human_triage_queue ?? []
    const boundedIndex = Math.max(0, Math.min(queue.length - 1, nextIndex))
    setTriageIndex(boundedIndex)
    const taskId = queue[boundedIndex]?.task_id
    if (taskId) window.history.replaceState(null, '', pdfLabStageHash('surgical-triage', taskId))
  }, [data?.triage.human_triage_queue])

  useEffect(() => {
    if (!data || stage !== 'surgical-triage') return
    const queue = data.triage.human_triage_queue
    if (queue.length === 0) return
    const hashTaskId = getHashTriageTaskId()
    if (hashTaskId) {
      const hashIndex = queue.findIndex(task => task.task_id === hashTaskId)
      if (hashIndex >= 0 && hashIndex !== triageIndex) {
        setTriageIndex(hashIndex)
        return
      }
    }
    const activeTaskId = queue[triageIndex]?.task_id ?? queue[0]?.task_id
    if (activeTaskId && window.location.hash !== pdfLabStageHash('surgical-triage', activeTaskId)) {
      window.history.replaceState(null, '', pdfLabStageHash('surgical-triage', activeTaskId))
    }
  }, [data, stage, triageIndex])

  const addPageToCandidates = useCallback(() => {
    if (!data) return
    const input = window.prompt('Add page number to candidate queue')
    if (!input) return
    const page = Number(input)
    if (!Number.isInteger(page) || page < 1 || page > data.manifest.page_count) {
      setNotice(`Invalid page: ${input}`)
      return
    }
    setManualCandidates(current => current.some(candidate => candidate.page === page) ? current : [...current, { page, source: 'manual' }])
    setSelectedPage(page)
    setNotice(`Page ${page} added to candidates`)
  }, [data])

  const advanceTriage = useCallback(async (decision: 'accept' | 'reject' | 'skip') => {
    const task = data?.triage.human_triage_queue[triageIndex]
    if (!task) return
    setActionBusy(`triage-${decision}`)
    try {
      await postJson('/api/pdf-lab/triage-decision', {
        taskId: task.task_id,
        decision,
        intent: intentDraft,
        page: task.page,
        task,
        proposedJsonDelta: task.proposed_json_delta ?? null,
      })
      setLastDecision(`${decision}: ${task.task_id}`)
      goToTriageIndex(triageIndex + 1)
      setIntentDraft('')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    } finally {
      setActionBusy(null)
    }
  }, [data?.triage.human_triage_queue, goToTriageIndex, intentDraft, triageIndex])

  const undoLastDecision = useCallback(async () => {
    const task = data?.triage.human_triage_queue[Math.max(0, triageIndex - 1)] ?? data?.triage.human_triage_queue[triageIndex]
    if (!task) return
    setActionBusy('triage-undo')
    try {
      await postJson('/api/pdf-lab/triage-decision', {
        taskId: task.task_id,
        decision: 'undo',
        intent: intentDraft,
        page: task.page,
        task,
        proposedJsonDelta: task.proposed_json_delta ?? null,
      })
      setLastDecision(null)
      goToTriageIndex(triageIndex - 1)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    } finally {
      setActionBusy(null)
    }
  }, [data?.triage.human_triage_queue, goToTriageIndex, intentDraft, triageIndex])

  const pollExtractionJob = useCallback(async (
    jobId: string,
    actionLabel: string,
    nextStage?: WorkflowStage,
  ) => {
    for (;;) {
      await sleep(2500)
      const status = await fetchJson<PdfLabJobResponse>(`/api/pdf-lab/jobs/${jobId}`)
      if (status.job) setCurrentJob(status.job)
      if (typeof status.logTail === 'string') setJobLogTail(status.logTail)

      if (status.job?.status === 'succeeded') {
        await loadArtifacts()
        if (nextStage) openStage(nextStage)
        const promoted = status.job.promoted
        const accuracy = typeof promoted?.accuracy === 'number' ? ` · ${(promoted.accuracy * 100).toFixed(2)}% parity` : ''
        const triageTasks = typeof promoted?.triage_tasks === 'number' ? ` · ${promoted.triage_tasks} triage cards` : ''
        setNotice(`${actionLabel} complete${accuracy}${triageTasks}`)
        return
      }

      if (status.job?.status === 'failed') {
        setNotice(`${actionLabel} failed: ${status.job.error ?? `see ${status.job.logPath}`}`)
        return
      }
    }
  }, [loadArtifacts, openStage])

  const promoteDirectRun = useCallback(async () => {
    const outputDir = window.prompt('Promote direct pdf_oxide output directory, e.g. /tmp/pdf-lab-direct-50-debug')
    if (!outputDir) return
    setActionBusy('Promote Direct Run')
    setNotice(`Promoting direct run ${outputDir}…`)
    try {
      const result = await postJson<PdfLabJobResponse>('/api/pdf-lab/jobs/promote-output', { outputDir })
      await loadArtifacts()
      const accuracy = typeof result.promoted?.accuracy === 'number' ? ` · ${(result.promoted.accuracy * 100).toFixed(2)}% parity` : ''
      setNotice(`Promoted direct run${accuracy}`)
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    } finally {
      setActionBusy(null)
    }
  }, [loadArtifacts])

  const runWorkflowAction = useCallback(async (
    actionLabel: string,
    endpoint: string,
    nextStage?: WorkflowStage,
  ) => {
    setActionBusy(actionLabel)
    setNotice(`${actionLabel} queued against real pdf_oxide artifacts…`)
    setJobLogTail('')
    try {
      const result = await postJson<PdfLabJobResponse>(endpoint, {
        maxPages: 50,
        topK: 5,
        maxIterations: 1,
        target: 0.95,
      })
      if (result.async && result.job) {
        setCurrentJob(result.job)
        setNotice(`${actionLabel} running as job ${result.job.id}`)
        await pollExtractionJob(result.job.id, actionLabel, nextStage)
      } else {
        await loadArtifacts()
        if (nextStage) openStage(nextStage)
        const accuracy = typeof result.promoted?.accuracy === 'number' ? ` · ${(result.promoted.accuracy * 100).toFixed(2)}% parity` : ''
        setNotice(`${actionLabel} complete${accuracy}`)
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : String(err))
    } finally {
      setActionBusy(null)
    }
  }, [loadArtifacts, openStage, pollExtractionJob])

  const candidates = useMemo(() => {
    if (!data) return []
    const manualPages = new Set(manualCandidates.map(candidate => candidate.page))
    const existingPages = new Set(data.manifest.candidate_inventory.candidate_pages.map(candidate => candidate.page))
    const manualRows: CandidatePageArtifact[] = Array.from(manualPages)
      .filter(page => !existingPages.has(page))
      .map(page => {
        const evidence = getEvidenceForPage(data.manifest, page)
        const elementTypes = evidence.reduce<Record<string, number>>((types, item) => {
          types[item.type] = (types[item.type] ?? 0) + 1
          return types
        }, {})
        return {
          element_count: evidence.length,
          element_types: elementTypes,
          gate_status: 'manual',
          inferred_match_score: null,
          page,
          severity: 'manual',
          source: 'manual operator add',
          task_count: data.triage.human_triage_queue.filter(task => task.page === page).length,
          task_kinds: {},
        }
      })
    return [...data.manifest.candidate_inventory.candidate_pages, ...manualRows]
  }, [data, manualCandidates])

  const selectedCandidate = useMemo(() => {
    if (!selectedPage) return candidates[0]
    return candidates.find(candidate => candidate.page === selectedPage) ?? candidates[0]
  }, [candidates, selectedPage])

  const activeTriageArtifact = data?.triage.human_triage_queue[triageIndex] ?? data?.triage.human_triage_queue[0] ?? null
  const activeTriageCard = activeTriageArtifact ? buildTriageTask(activeTriageArtifact) : null

  if (error) {
    return (
      <div className="pdf-lab-prod-root pdf-lab-prod-state" data-qid="pdf-lab:production:error">
        <h1>PDF Lab artifact load failed</h1>
        <p>{error}</p>
      </div>
    )
  }

  if (!data || !selectedCandidate) {
    return (
      <div className="pdf-lab-prod-root pdf-lab-prod-state" data-qid="pdf-lab:production:loading">
        <h1>Loading real PDF Lab artifacts…</h1>
        <p>{MANIFEST_URL}</p>
      </div>
    )
  }

  if (stage === 'surgical-triage') {
    if (!activeTriageCard) {
      const resolvedCount = data.triage.agent_resolved_summary?.finding_count ?? 0
      const resolvedKinds = data.triage.agent_resolved_summary?.findings_by_kind ?? {}
      const resolvedRows = Object.entries(resolvedKinds)
      const recentFindings = data.triage.agent_resolved_findings?.slice(0, 4) ?? []
      const improvement = data.manifest.extraction_improvement
      const presetName = improvement?.preset?.name ?? 'document-family preset'

      return (
        <div className="pdf-lab-prod-root pdf-lab-prod-empty-deck" data-qid="pdf-lab:production:triage-empty">
          <section className="pdf-lab-prod-empty-card">
            <div className="pdf-lab-prod-empty-eyebrow">PDF Lab · Second-pass complete</div>
            <h1>No human triage cards remain</h1>
            <p>
              The agent resolved the current residuals before handing work to the human.
              The production rule is working: humans only see unresolved ambiguity, not
              obvious extractor or canonicalization defects.
            </p>

            {improvement && (
              <div className="pdf-lab-prod-empty-report">
                <h2>Extraction report boundary</h2>
                <p>
                  The <code>{presetName}</code> preset and PDF Lab second-pass orchestration improved the
                  effective <code>pdf_oxide</code> extraction for this NIST-like PDF. This run did not patch
                  the core Rust extractor: <code>core_pdf_oxide_changed={String(Boolean(improvement.core_pdf_oxide_changed))}</code>.
                </p>
              </div>
            )}

            <div className="pdf-lab-prod-empty-grid">
              <div>
                <span>Human cards</span>
                <strong>{data.triage.task_count}</strong>
              </div>
              <div>
                <span>Agent-resolved findings</span>
                <strong>{resolvedCount}</strong>
              </div>
              <div>
                <span>Parity gate</span>
                <strong>{data.comparison ? `${(data.comparison.accuracy * 100).toFixed(2)}%` : 'passed'}</strong>
              </div>
            </div>

            <div className="pdf-lab-prod-empty-findings">
              <h2>Resolved by second pass</h2>
              {resolvedRows.length > 0 ? (
                <ul>
                  {resolvedRows.map(([kind, count]) => (
                    <li key={kind}>
                      <code>{kind}</code>
                      <span>{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No agent-resolved findings were reported.</p>
              )}
            </div>

            {recentFindings.length > 0 && (
              <div className="pdf-lab-prod-empty-findings">
                <h2>Recent examples</h2>
                <ul>
                  {recentFindings.map(finding => (
                    <li key={finding.finding_id}>
                      <code>{finding.kind}</code>
                      <span>p{finding.page}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="pdf-lab-prod-empty-actions">
              <button
                data-qid="pdf-lab:production:triage-empty-open-evidence-qa"
                data-qs-action="PDF_LAB_PRODUCTION_OPEN_EVIDENCE_QA"
                title="Open Nico evidence QA for stratified final checks"
                onClick={() => openStage('evidence-qa')}
              >
                Open Evidence QA
              </button>
              <button
                data-qid="pdf-lab:production:triage-empty-open-parity"
                data-qs-action="PDF_LAB_PRODUCTION_OPEN_PARITY_AUDIT"
                title="Open the parity audit that produced this empty human deck"
                onClick={() => openStage('parity-audit')}
              >
                Open Parity Audit
              </button>
              <button
                data-qid="pdf-lab:production:triage-empty-open-sweep"
                data-qs-action="PDF_LAB_PRODUCTION_OPEN_INITIAL_SWEEP"
                title="Open the initial sweep candidate inventory"
                onClick={() => openStage('initial-sweep')}
              >
                Open Initial Sweep
              </button>
            </div>
          </section>
        </div>
      )
    }

    return (
      <div className="pdf-lab-prod-root pdf-lab-prod-triage" data-qid="pdf-lab:production:root">
        <SurgicalTriageCleanRoom
          pdfUrl={PDF_URL}
          pageNumber={Math.max(0, (activeTriageArtifact?.page ?? 1) - 1)}
          taskIndex={triageIndex}
          taskCount={data.triage.human_triage_queue.length}
          task={activeTriageCard}
          intentDraft={intentDraft}
          onIntentChange={setIntentDraft}
          onAccept={() => { void advanceTriage('accept') }}
          onReject={() => { void advanceTriage('reject') }}
          onSkip={() => { void advanceTriage('skip') }}
          onPrevious={() => goToTriageIndex(triageIndex - 1)}
          onNext={() => goToTriageIndex(triageIndex + 1)}
          onUndoLastDecision={undoLastDecision}
          onOpenAudit={() => undefined}
          onOpenQueue={() => openStage('parity-audit')}
        />
        {lastDecision && <div className="pdf-lab-prod-decision-toast">Last decision: {lastDecision}</div>}
      </div>
    )
  }

  if (stage === 'evidence-qa') {
    return (
      <div className="pdf-lab-prod-root" data-qid="pdf-lab:production:evidence-qa-root">
        <header className="pdf-lab-prod-header">
          <div>
            <div className="pdf-lab-prod-brand">PDF Lab</div>
            <div className="pdf-lab-prod-subtitle">
              Final Nico evidence QA · real PDF crops, extracted JSON, and memory-ready provenance
            </div>
          </div>
          <div className="pdf-lab-prod-header-actions">
            <button
              data-qid="pdf-lab:production:evidence-qa-open-triage"
              data-qs-action="PDF_LAB_PRODUCTION_STAGE_SURGICAL_TRIAGE"
              title="Open the final human ambiguity deck"
              onClick={() => openStage('surgical-triage')}
            >
              Open Triage Deck
            </button>
            <button
              data-qid="pdf-lab:production:evidence-qa-open-parity"
              data-qs-action="PDF_LAB_PRODUCTION_STAGE_PARITY_AUDIT"
              title="Open parity audit"
              onClick={() => openStage('parity-audit')}
            >
              Open Parity Audit
            </button>
          </div>
        </header>

        <nav className="pdf-lab-prod-stage-nav" aria-label="PDF Lab workflow stages">
          <StageButton id="initial-sweep" label="1 · Initial Sweep" activeStage={stage} onOpen={openStage} />
          <StageButton id="parity-audit" label="2 · Parity Audit" activeStage={stage} onOpen={openStage} />
          <StageButton id="surgical-triage" label="3 · Surgical Triage" activeStage={stage} onOpen={openStage} />
          <StageButton id="evidence-qa" label="4 · Evidence QA" activeStage={stage} onOpen={openStage} />
          <StageButton id="coverage" label="5 · Coverage" activeStage={stage} onOpen={openStage} />
          <StageButton id="labeling" label="6 · Labeling" activeStage={stage} onOpen={openStage} />
          <div className="pdf-lab-prod-metric"><span>Pages</span><b>{data.manifest.page_count}</b></div>
          <div className="pdf-lab-prod-metric"><span>Candidates</span><b>{candidates.length}</b></div>
          <div className="pdf-lab-prod-metric"><span>Triage Cards</span><b>{data.triage.task_count}</b></div>
        </nav>

        <PdfLabEvidenceQA />
      </div>
    )
  }

  if (stage === 'coverage') {
    return (
      <div className="pdf-lab-prod-root" data-qid="pdf-lab:production:coverage-root">
        <header className="pdf-lab-prod-header">
          <div>
            <div className="pdf-lab-prod-brand">PDF Lab</div>
            <div className="pdf-lab-prod-subtitle">
              Coverage / status · artifact-derived blockers and definition-of-done gates
            </div>
          </div>
          <div className="pdf-lab-prod-header-actions">
            <button
              data-qid="pdf-lab:production:coverage-open-parity"
              data-qs-action="PDF_LAB_PRODUCTION_STAGE_PARITY_AUDIT"
              title="Open parity audit"
              onClick={() => openStage('parity-audit')}
            >
              Open Parity Audit
            </button>
            <button
              data-qid="pdf-lab:production:coverage-open-evidence"
              data-qs-action="PDF_LAB_PRODUCTION_STAGE_EVIDENCE_QA"
              title="Open evidence QA"
              onClick={() => openStage('evidence-qa')}
            >
              Open Evidence QA
            </button>
          </div>
        </header>

        <nav className="pdf-lab-prod-stage-nav" aria-label="PDF Lab workflow stages">
          <StageButton id="initial-sweep" label="1 · Initial Sweep" activeStage={stage} onOpen={openStage} />
          <StageButton id="parity-audit" label="2 · Parity Audit" activeStage={stage} onOpen={openStage} />
          <StageButton id="surgical-triage" label="3 · Surgical Triage" activeStage={stage} onOpen={openStage} />
          <StageButton id="evidence-qa" label="4 · Evidence QA" activeStage={stage} onOpen={openStage} />
          <StageButton id="coverage" label="5 · Coverage" activeStage={stage} onOpen={openStage} />
          <StageButton id="labeling" label="6 · Labeling" activeStage={stage} onOpen={openStage} />
          <div className="pdf-lab-prod-metric"><span>Pages</span><b>{data.manifest.page_count}</b></div>
          <div className="pdf-lab-prod-metric"><span>Candidates</span><b>{candidates.length}</b></div>
          <div className="pdf-lab-prod-metric"><span>Triage Cards</span><b>{data.triage.task_count}</b></div>
        </nav>

        <CoverageStatusPane
          comparison={data.comparison}
          coverageLoop={data.coverageLoop}
          manifest={data.manifest}
          onOpenCandidateAudit={setCandidateAuditRow}
          onOpenStage={openStage}
          statusReport={data.statusReport}
          tocAudit={data.tocAudit}
          triage={data.triage}
        />
        {candidateAuditRow && (
          <CandidateAuditModal row={candidateAuditRow} onClose={() => setCandidateAuditRow(null)} />
        )}
      </div>
    )
  }

  if (stage === 'labeling') {
    return (
      <div className="pdf-lab-prod-root pdf-lab-prod-root-labeling" data-qid="pdf-lab:production:labeling-root">
        <header className="pdf-lab-prod-header">
          <div>
            <div className="pdf-lab-prod-brand">PDF Lab</div>
            <div className="pdf-lab-prod-subtitle">
              Labeling · draw expected elements directly on the rendered PDF page
            </div>
          </div>
          <div className="pdf-lab-prod-header-actions">
            <button
              data-qid="pdf-lab:production:labeling-open-coverage"
              data-qs-action="PDF_LAB_PRODUCTION_STAGE_COVERAGE"
              title="Back to Coverage"
              onClick={() => openStage('coverage')}
            >
              Back to Coverage
            </button>
          </div>
        </header>

        <nav className="pdf-lab-prod-stage-nav" aria-label="PDF Lab workflow stages">
          <StageButton id="initial-sweep" label="1 · Initial Sweep" activeStage={stage} onOpen={openStage} />
          <StageButton id="parity-audit" label="2 · Parity Audit" activeStage={stage} onOpen={openStage} />
          <StageButton id="surgical-triage" label="3 · Surgical Triage" activeStage={stage} onOpen={openStage} />
          <StageButton id="evidence-qa" label="4 · Evidence QA" activeStage={stage} onOpen={openStage} />
          <StageButton id="coverage" label="5 · Coverage" activeStage={stage} onOpen={openStage} />
          <StageButton id="labeling" label="6 · Labeling" activeStage={stage} onOpen={openStage} />
        </nav>

        <PdfLabLabelingPage />
      </div>
    )
  }

  return (
    <div className="pdf-lab-prod-root" data-qid="pdf-lab:production:root">
      <header className="pdf-lab-prod-header">
        <div>
          <div className="pdf-lab-prod-brand">PDF Lab</div>
          <div className="pdf-lab-prod-subtitle">
            Real workflow artifacts · humans resolve {data.triage.task_count} final ambiguities across {data.triage.summary.pages_with_tasks} pages
          </div>
        </div>
        <div className="pdf-lab-prod-header-actions">
          <button
            data-qid="pdf-lab:production:add-page"
            data-qs-action="PDF_LAB_PRODUCTION_ADD_PAGE_TO_CANDIDATES"
            title="Add a known page to the candidate queue"
            onClick={addPageToCandidates}
          >
            Add Page to Candidates
          </button>
          <button
            data-qid="pdf-lab:production:promote-direct-run"
            data-qs-action="PDF_LAB_PRODUCTION_PROMOTE_DIRECT_RUN"
            title="Promote a direct pdf_oxide output directory into UX Lab artifacts"
            onClick={promoteDirectRun}
            disabled={Boolean(actionBusy)}
          >
            Promote Direct Run
          </button>
          <button
            data-qid="pdf-lab:production:open-triage"
            data-qs-action="PDF_LAB_PRODUCTION_STAGE_SURGICAL_TRIAGE"
            title="Open the final human ambiguity deck"
            onClick={() => openStage('surgical-triage')}
          >
            Open Triage Deck
          </button>
        </div>
      </header>

      <nav className="pdf-lab-prod-stage-nav" aria-label="PDF Lab workflow stages">
        <StageButton id="initial-sweep" label="1 · Initial Sweep" activeStage={stage} onOpen={openStage} />
        <StageButton id="parity-audit" label="2 · Parity Audit" activeStage={stage} onOpen={openStage} />
        <StageButton id="surgical-triage" label="3 · Surgical Triage" activeStage={stage} onOpen={openStage} />
        <StageButton id="evidence-qa" label="4 · Evidence QA" activeStage={stage} onOpen={openStage} />
        <StageButton id="coverage" label="5 · Coverage" activeStage={stage} onOpen={openStage} />
        <StageButton id="labeling" label="6 · Labeling" activeStage={stage} onOpen={openStage} />
        <div className="pdf-lab-prod-metric"><span>Pages</span><b>{data.manifest.page_count}</b></div>
        <div className="pdf-lab-prod-metric"><span>Candidates</span><b>{candidates.length}</b></div>
        <div className="pdf-lab-prod-metric"><span>Triage Cards</span><b>{data.triage.task_count}</b></div>
      </nav>

      {notice && <div className="pdf-lab-prod-notice">{notice}</div>}
      {currentJob && currentJob.status !== 'succeeded' && (
        <div className="pdf-lab-prod-job-status" data-qid="pdf-lab:production:job-status">
          <div>
            <b>{currentJob.status.toUpperCase()}</b> {currentJob.id}
            <span>{currentJob.outputDir}</span>
          </div>
          {jobLogTail && <pre>{jobLogTail}</pre>}
        </div>
      )}

      {stage === 'initial-sweep' ? (
        <InitialSweepPane
          candidates={candidates}
          familyTallies={buildFamilyTallies(data.manifest)}
          manifest={data.manifest}
          selectedCandidate={selectedCandidate}
          selectedPage={selectedPage ?? selectedCandidate.page}
          setSelectedPage={setSelectedPage}
          actionBusy={actionBusy}
          onCommit={() => runWorkflowAction('Commit Sweep to Run', '/api/pdf-lab/commit-sweep-to-run', 'parity-audit')}
        />
      ) : (
        <ParityAuditPane
          comparison={data.comparison}
          manifest={data.manifest}
          triage={data.triage}
          candidates={candidates}
          actionBusy={actionBusy}
          onBulkRerun={() => runWorkflowAction('Bulk Repair / Re-run', '/api/pdf-lab/bulk-repair-rerun', 'parity-audit')}
          onEject={() => runWorkflowAction('Eject Mismatches to Triage', '/api/pdf-lab/eject-mismatches-to-triage', 'surgical-triage')}
        />
      )}
    </div>
  )
}

function StageButton({
  id,
  label,
  activeStage,
  onOpen,
}: {
  id: WorkflowStage
  label: string
  activeStage: WorkflowStage
  onOpen: (stage: WorkflowStage) => void
}) {
  const action = `PDF_LAB_PRODUCTION_STAGE_${id.replace('-', '_').toUpperCase()}`
  return (
    <button
      className={`pdf-lab-prod-stage-button ${activeStage === id ? 'active' : ''}`}
      data-qid={`pdf-lab:production:stage:${id}`}
      data-qs-action={action}
      title={`Open ${label}`}
      onClick={() => onOpen(id)}
    >
      {label}
    </button>
  )
}

function InitialSweepPane({
  candidates,
  familyTallies,
  manifest,
  selectedCandidate,
  selectedPage,
  setSelectedPage,
  actionBusy,
  onCommit,
}: {
  candidates: CandidatePageArtifact[]
  familyTallies: Array<[string, number]>
  manifest: WorkflowManifest
  selectedCandidate: CandidatePageArtifact
  selectedPage: number
  setSelectedPage: (page: number) => void
  actionBusy: string | null
  onCommit: () => void
}) {
  const evidence = getEvidenceForPage(manifest, selectedCandidate.page)
  const primaryEvidence = evidence.find(item => item.bbox) ?? evidence[0]
  const [failedImages, setFailedImages] = useState<Set<number>>(() => new Set())
  const evidenceImageMissing = failedImages.has(selectedCandidate.page)
  const evidenceImageUrl = getPresetScanThumbnailUrl(selectedCandidate.page)

  return (
    <main className="pdf-lab-prod-three-pane">
      <aside className="pdf-lab-prod-pane pdf-lab-prod-elements">
        <PaneHeader title="Elements" detail="Real preset element tally found during sweep" />
        {familyTallies.map(([label, count]) => (
          <button
            key={label}
            className={`pdf-lab-prod-family-row ${label === 'Tables' ? 'active' : ''}`}
            data-qid={`pdf-lab:production:family:${label.toLowerCase().replaceAll(' ', '-')}`}
            data-qs-action="PDF_LAB_PRODUCTION_FILTER_FAMILY"
            title={`Filter candidate pages by ${label}`}
            onClick={() => undefined}
          >
            <span>{label}</span>
            <b>{count}</b>
          </button>
        ))}
      </aside>

      <section className="pdf-lab-prod-pane pdf-lab-prod-candidates">
        <PaneHeader title="Candidate Pages" detail={`${candidates.length} real pages selected for deterministic extraction`} />
        <div className="pdf-lab-prod-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Page</th>
                <th>Preview</th>
                <th>Detected Families</th>
                <th>Matched Presets</th>
                <th>Evidence / Anchors</th>
                <th>Next Step</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map(candidate => (
                <tr
                  key={`${candidate.source}:${candidate.page}`}
                  className={candidate.page === selectedPage ? 'selected' : ''}
                  data-qid={`pdf-lab:production:candidate:${candidate.page}`}
                  data-qs-action="PDF_LAB_PRODUCTION_SELECT_CANDIDATE_PAGE"
                  title={`Inspect candidate page ${candidate.page}`}
                  tabIndex={0}
                  onClick={() => setSelectedPage(candidate.page)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') setSelectedPage(candidate.page)
                  }}
                >
                  <td className="pdf-lab-prod-page-num">{candidate.page}</td>
                  <td>
                    <div className="pdf-lab-prod-thumb">
                      <img
                        alt={`Rendered candidate page ${candidate.page}`}
                        src={getPresetScanThumbnailUrl(candidate.page)}
                        onError={(event) => { event.currentTarget.style.display = 'none' }}
                      />
                    </div>
                  </td>
                  <td><TagList tags={getCandidateFamilies(candidate)} /></td>
                  <td><code>{getPrimaryPreset(candidate)}</code></td>
                  <td>{getSweepEvidence(candidate)}</td>
                  <td className="pdf-lab-prod-next-step">{candidate.task_count > 0 ? 'Compare JSON' : 'Extract Page'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pdf-lab-prod-pane-footer">
          <button
            className="pdf-lab-prod-primary"
            data-qid="pdf-lab:production:commit-sweep"
            data-qs-action="PDF_LAB_PRODUCTION_COMMIT_SWEEP"
            title="Commit sweep candidates to deterministic extraction"
            onClick={onCommit}
            disabled={actionBusy !== null}
          >
            {actionBusy === 'Commit Sweep to Run' ? 'Running pdf_oxide…' : 'Commit Sweep to Run →'}
          </button>
        </div>
      </section>

      <aside className="pdf-lab-prod-pane pdf-lab-prod-evidence">
        <PaneHeader title="Evidence" detail={`Real evidence extracted from page ${selectedCandidate.page}`} />
        <div className="pdf-lab-prod-evidence-card">
          {evidenceImageMissing ? (
            <div className="pdf-lab-prod-evidence-missing">
              <b>No rendered preset-scan thumbnail for page {selectedCandidate.page}</b>
              <span>Run Commit Sweep to regenerate real page evidence.</span>
            </div>
          ) : (
            <div className="pdf-lab-prod-real-page">
              <img
                alt={`Rendered NIST page ${selectedCandidate.page}`}
                src={evidenceImageUrl}
                onError={() => setFailedImages(current => new Set(current).add(selectedCandidate.page))}
              />
              {primaryEvidence?.bbox && (
                <div className="pdf-lab-prod-evidence-bbox" style={getBboxStyle(primaryEvidence.bbox)}>
                  <span>{formatFamily(primaryEvidence.type)}</span>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="pdf-lab-prod-evidence-note">
          <b>{primaryEvidence?.id ?? `page-${selectedCandidate.page}`}</b>
          <p>{primaryEvidence?.text ?? `${selectedCandidate.element_count} extracted elements available for this page.`}</p>
        </div>
      </aside>
    </main>
  )
}

function ParityAuditPane({
  comparison,
  manifest,
  triage,
  candidates,
  actionBusy,
  onBulkRerun,
  onEject,
}: {
  comparison: JsonComparison | null
  manifest: WorkflowManifest
  triage: TriageQueue
  candidates: CandidatePageArtifact[]
  actionBusy: string | null
  onBulkRerun: () => void
  onEject: () => void
}) {
  const comparisonRows = buildComparisonRows(comparison)
  const runRows = buildCandidateRunRows(comparison, candidates)
  const autoForwardCount = Math.max(0, manifest.page_count - triage.summary.pages_with_tasks)

  return (
    <main className="pdf-lab-prod-three-pane parity">
      <aside className="pdf-lab-prod-pane pdf-lab-prod-run">
        <PaneHeader title="Candidate Run" detail="Real pdf_oxide extraction status by page and preset" />
        {runRows.map(row => (
          <div key={row.page} className={`pdf-lab-prod-run-row ${row.missing > 0 || row.extra > 0 || row.triageTasks > 0 ? 'review' : 'pass'}`}>
            <div><b>Page {row.page}</b><code>{row.preset}</code></div>
            <span>{row.elementCount} elements · {row.matched} matched</span>
            <strong>{row.missing} missing · {row.extra} extra · {row.triageTasks} triage tasks</strong>
          </div>
        ))}
        <button
          className="pdf-lab-prod-secondary"
          data-qid="pdf-lab:production:bulk-rerun"
          data-qs-action="PDF_LAB_PRODUCTION_BULK_REPAIR_RERUN"
          title="Repair systemic settings and rerun the deterministic extraction pass"
          onClick={onBulkRerun}
          disabled={actionBusy !== null}
        >
          {actionBusy === 'Bulk Repair / Re-run' ? 'Running pdf_oxide…' : 'Bulk Repair / Re-run'}
        </button>
      </aside>

      <section className="pdf-lab-prod-pane pdf-lab-prod-compare">
        <PaneHeader
          title="Parity Audit"
          detail={comparison
            ? `${comparison.matched_expected_elements}/${comparison.total_expected_elements} matched · ${(comparison.accuracy * 100).toFixed(2)}% parity`
            : 'Comparison artifact unavailable; no parity rows rendered'}
        />
        {comparison && (
          <div className={`pdf-lab-prod-artifact-gap ${comparison.passed ? 'success' : 'warn'}`}>
            <b>Real comparison artifact mounted</b>
            <p>
              <code>{manifest.source_comparison}</code> {comparison.passed ? 'passed' : 'failed'} target {(comparison.target * 100).toFixed(0)}%
              {' '}with {comparison.unmatched_expected_elements} missing expected and {comparison.unmatched_actual_elements} unmatched actual elements.
            </p>
          </div>
        )}
        {!comparison && (
          <div className="pdf-lab-prod-artifact-gap">
            <b>Comparison artifact not mounted</b>
            <p>The UI attempted to load <code>{COMPARISON_URL}</code>. Regenerate or publish <code>comparison.json</code> before using this stage.</p>
          </div>
        )}
        <div className="pdf-lab-prod-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Element</th>
                <th>Page</th>
                <th>Expected</th>
                <th>Actual</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(row => (
                <tr key={`${row.status}:${row.id}`}>
                  <td><code title={row.detail}>{row.id}</code></td>
                  <td>{row.page}</td>
                  <td>{row.expected}</td>
                  <td>{row.actual}</td>
                  <td><span className={`pdf-lab-prod-parity ${row.status}`}>{row.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="pdf-lab-prod-pane pdf-lab-prod-output">
        <PaneHeader title="Triage Output" detail="Only unresolved mismatches become human cards" />
        <div className={`pdf-lab-prod-output-card ${comparison?.passed ? 'success' : 'warn'}`}>
          <b>{comparison ? `${comparison.matched_expected_elements} elements matched` : `${autoForwardCount} pages auto-forwarded`}</b>
          <p>
            {comparison
              ? `Parity audit ${comparison.passed ? 'passed' : 'failed'} at ${(comparison.accuracy * 100).toFixed(2)}% against the ${(comparison.target * 100).toFixed(0)}% gate.`
              : manifest.gate.summary}
          </p>
        </div>
        <div className="pdf-lab-prod-output-card warn">
          <b>{triage.task_count} human cards</b>
          <p>{triage.summary.tasks_by_severity.high ?? 0} high · {triage.summary.tasks_by_severity.medium ?? 0} medium · {triage.summary.pages_with_tasks} pages.</p>
        </div>
        <button
          className="pdf-lab-prod-primary"
          data-qid="pdf-lab:production:eject-triage"
          data-qs-action="PDF_LAB_PRODUCTION_EJECT_MISMATCHES_TO_TRIAGE"
          title="Create human triage cards only for unresolved mismatches"
          onClick={onEject}
          disabled={actionBusy !== null}
        >
          {actionBusy === 'Eject Mismatches to Triage' ? 'Generating triage…' : 'Eject Mismatches to Triage →'}
        </button>
      </aside>
    </main>
  )
}

function CoverageStatusPane({
  comparison,
  coverageLoop,
  manifest,
  onOpenCandidateAudit,
  onOpenStage,
  statusReport,
  triage,
}: {
  comparison: JsonComparison | null
  coverageLoop: CoverageLoopReport | null
  manifest: WorkflowManifest
  onOpenCandidateAudit: (row: CandidateAuditRow) => void
  onOpenStage: (stage: WorkflowStage) => void
  statusReport: PdfLabStatusReport | null
  tocAudit: TocAudit | null
  triage: TriageQueue
}) {
  useRegisterAction('pdf-lab:convergence:select-case', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_SELECT_CASE',
    label: 'Select convergence case',
    description: 'Select an unresolved agentic sweep candidate for human clarification',
  })
  useRegisterAction('pdf-lab:convergence:shortcuts', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_SHORTCUTS',
    label: 'Show shortcuts',
    description: 'Show PDF Lab convergence keyboard shortcuts',
  })
  useRegisterAction('pdf-lab:convergence:help', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_HELP',
    label: 'Show help',
    description: 'Show help for PDF Lab convergence cases',
  })
  useRegisterAction('pdf-lab:convergence:share-run', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_SHARE_RUN',
    label: 'Share run',
    description: 'Share this PDF Lab convergence run',
  })
  useRegisterAction('pdf-lab:convergence:set-clarification', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_SET_CLARIFICATION',
    label: 'Set clarification',
    description: 'Set the human clarification for the selected convergence case',
  })
  useRegisterAction('pdf-lab:convergence:view-resolved', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_VIEW_RESOLVED',
    label: 'View resolved cases',
    description: 'Open resolved convergence cases for this PDF Lab run',
  })
  useRegisterAction('pdf-lab:convergence:confirm-extractor-failure', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_CONFIRM_EXTRACTOR_FAILURE',
    label: 'Confirm extractor failure',
    description: 'Confirm that the selected agentic sweep candidate is a real deterministic extractor failure',
  })
  useRegisterAction('pdf-lab:convergence:accept-extraction', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_ACCEPT_EXTRACTION',
    label: 'Accept extraction as correct',
    description: 'Mark the current deterministic extraction output as correct for the selected candidate',
  })
  useRegisterAction('pdf-lab:convergence:reject-non-issue', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_REJECT_NON_ISSUE',
    label: 'Reject non-issue',
    description: 'Reject the selected agentic sweep candidate as not requiring an extractor fix',
  })
  useRegisterAction('pdf-lab:convergence:request-more-evidence', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_REQUEST_MORE_EVIDENCE',
    label: 'Request more evidence',
    description: 'Mark the selected convergence case as requiring more visual or extraction evidence',
  })
  useRegisterAction('pdf-lab:convergence:tune-preset', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_TUNE_PRESET',
    label: 'Tune preset',
    description: 'Open the preset tuning path for the selected extractor failure',
  })
  useRegisterAction('pdf-lab:convergence:promote-fixture', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_PROMOTE_REGRESSION_FIXTURE',
    label: 'Promote regression fixture',
    description: 'Promote an artifact-backed convergence case into a regression fixture when gates pass',
  })
  useRegisterAction('pdf-lab:convergence:create-parser-task', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_CREATE_PARSER_PATCH_TASK',
    label: 'Create parser patch task',
    description: 'Create a project-agent task for a core parser/extractor patch',
  })
  useRegisterAction('pdf-lab:convergence:open-debug-json', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_OPEN_DEBUG_JSON',
    label: 'Open debug raw JSON',
    description: 'Expand the selected candidate raw extraction JSON debug drawer',
  })
  useRegisterAction('pdf-lab:convergence:open-run-status', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_OPEN_RUN_STATUS',
    label: 'Open run status artifacts',
    description: 'Expand run status artifacts for the selected convergence case',
  })
  useRegisterAction('pdf-lab:convergence:open-provenance', {
    app: 'pdf-lab',
    action: 'PDF_LAB_CONVERGENCE_OPEN_PROVENANCE',
    label: 'Open provenance',
    description: 'Expand provenance details for the selected convergence case',
  })

  const summary = statusReport?.summary
  const candidateAuditRows = buildCandidateAuditRows(manifest, triage)
  const unresolvedCases = candidateAuditRows
    .filter(row => row.candidate && row.finalState !== 'pass')
    .sort((left, right) => {
      const preferredPages = [457, 458, 21, 27]
      const leftPreferred = preferredPages.indexOf(left.page)
      const rightPreferred = preferredPages.indexOf(right.page)
      if (leftPreferred !== -1 || rightPreferred !== -1) {
        return (leftPreferred === -1 ? Number.MAX_SAFE_INTEGER : leftPreferred)
          - (rightPreferred === -1 ? Number.MAX_SAFE_INTEGER : rightPreferred)
      }
      const leftTasks = left.candidate?.task_count ?? 0
      const rightTasks = right.candidate?.task_count ?? 0
      return rightTasks - leftTasks || left.page - right.page || left.elementId.localeCompare(right.elementId)
    })
  const fallbackCases = candidateAuditRows
    .filter(row => row.finalState !== 'pass')
    .slice(0, 4)
  const casesNeedingClarification = collapseRowsToConvergenceCases(unresolvedCases.length > 0 ? unresolvedCases : fallbackCases)
  const [selectedElementId, setSelectedElementId] = useState<string | null>(null)
  const selectedRow = casesNeedingClarification.find(row => row.elementId === selectedElementId)
    ?? casesNeedingClarification[0]
    ?? candidateAuditRows[0]
    ?? null
  const [clarification, setClarification] = useState<ConvergenceClarification>('single_table_wrong_bounds')

  useEffect(() => {
    if (selectedRow && selectedElementId !== selectedRow.elementId) {
      setSelectedElementId(selectedRow.elementId)
      setClarification(getDefaultClarification(selectedRow))
    }
  }, [selectedElementId, selectedRow])

  if (!selectedRow) {
    return (
      <main className="pdf-lab-prod-convergence pdf-lab-prod-convergence-empty" data-qid="pdf-lab:convergence:empty">
        <section>
          <h1>PDF Lab · Convergence Cases</h1>
          <p>No artifact-backed convergence cases are available. Generate agentic sweep and human triage artifacts before using this route.</p>
        </section>
      </main>
    )
  }

  const selectedCaseSummary = getConvergenceCaseSummary(selectedRow)
  const clarificationOptions = getClarificationOptions(selectedRow)
  const primaryAction = getPrimaryDecisionAction(clarification)
  const selectedRecord = {
    bbox: selectedRow.bbox ?? null,
    clarification,
    crop_uri: selectedRow.cropUri,
    element_id: selectedRow.elementId,
    failure_type: selectedCaseSummary.failureType,
    human_decision: primaryAction.decision,
    json_pointer: selectedRow.jsonPointer ?? null,
    page: selectedRow.page,
    proof_issue: selectedRow.proofIssue,
    source: selectedRow.source,
    text: selectedRow.elementText,
    type: selectedRow.elementType,
  }
  const similarCaseCount = Math.max(1, triage.agent_resolved_summary?.finding_count ?? casesNeedingClarification.length)
  const impactedDocCount = Math.max(1, Object.keys(summary?.agent_resolved_kinds ?? triage.agent_resolved_summary?.findings_by_kind ?? {}).length)
  const promoteFixtureReady = Boolean(
    selectedRow.bbox
    && selectedRow.cropUri
    && selectedRow.pageImageUri
    && selectedRow.jsonPointer
    && selectedRow.finalState !== 'fail'
    && comparison?.passed,
  )

  return (
    <main className="pdf-lab-prod-convergence" data-qid="pdf-lab:convergence:workbench">
      <header className="pdf-lab-prod-convergence-topbar" data-qid="pdf-lab:convergence:topbar">
        <div className="pdf-lab-prod-convergence-brand">
          <span aria-hidden="true">⚗</span>
          <div>
            <h1>PDF Lab · Convergence Cases</h1>
            <p><i /> Agentic sweep → human clarification → deterministic fix</p>
          </div>
        </div>
        <div className="pdf-lab-prod-convergence-top-actions">
          <button
            type="button"
            data-qid="pdf-lab:convergence:shortcuts"
            data-qs-action="PDF_LAB_CONVERGENCE_SHORTCUTS"
            title="Show keyboard shortcuts"
          >
            ⌘K Shortcuts
          </button>
          <button
            type="button"
            data-qid="pdf-lab:convergence:help"
            data-qs-action="PDF_LAB_CONVERGENCE_HELP"
            title="Show convergence case help"
          >
            ?
          </button>
          <button
            type="button"
            data-qid="pdf-lab:convergence:share-run"
            data-qs-action="PDF_LAB_CONVERGENCE_SHARE_RUN"
            title="Share this PDF Lab run"
          >
            Share run
          </button>
        </div>
      </header>

      <section className="pdf-lab-prod-convergence-shell">
        <aside className="pdf-lab-prod-convergence-queue" data-qid="pdf-lab:convergence:queue">
          <header>
            <div>
              <h2>Cases Needing Clarification</h2>
              <p>Unresolved cases only</p>
            </div>
            <span title="Agentic sweep cases are sorted by current severity">☷</span>
          </header>
          <div className="pdf-lab-prod-convergence-cases">
            {casesNeedingClarification.map(row => {
              const caseSummary = getConvergenceCaseSummary(row)
              const selected = row.elementId === selectedRow.elementId
              return (
                <button
                  type="button"
                  key={row.elementId}
                  className={`pdf-lab-prod-convergence-case ${selected ? 'selected' : ''}`}
                  data-qid={`pdf-lab:convergence:case:${row.elementId}`}
                  data-qs-action="PDF_LAB_CONVERGENCE_SELECT_CASE"
                  title={`Review convergence case ${caseSummary.title} on page ${row.page}`}
                  onClick={() => {
                    setSelectedElementId(row.elementId)
                    setClarification(getDefaultClarification(row))
                  }}
                >
                  <span className="pdf-lab-prod-convergence-page page-badge">p{row.page}</span>
                  <span>
                    <b>{caseSummary.title}</b>
                    <small>{getConvergenceCardDescription(row)}</small>
                    <em>{caseSummary.familyLabel}</em>
                  </span>
                  <strong className="status-pill">Needs human decision</strong>
                </button>
              )
            })}
          </div>
          <button
            type="button"
            className="pdf-lab-prod-convergence-resolved"
            data-qid="pdf-lab:convergence:view-resolved"
            data-qs-action="PDF_LAB_CONVERGENCE_VIEW_RESOLVED"
            title="View resolved convergence cases"
          >
            View resolved cases →
          </button>
        </aside>

        <section className="pdf-lab-prod-convergence-proof" data-qid="pdf-lab:convergence:proof-workspace">
          <header className="pdf-lab-prod-convergence-case-head">
            <span>Convergence case · p{selectedRow.page}</span>
            <h2>{selectedCaseSummary.question}</h2>
            <p>Current agent hypothesis: {selectedCaseSummary.hypothesis}</p>
            <div>
              <b>Failure type: {selectedCaseSummary.failureType}</b>
              <b>Expected source: Agent hypothesis</b>
              <b>Authority: <mark>Low</mark></b>
              <b>Actual source: {selectedRow.source}</b>
            </div>
          </header>

          <section className="pdf-lab-prod-convergence-visual" data-qid="pdf-lab:convergence:visual-proof">
            <header><Eye size={16} /><b>Visual proof</b></header>
            <div className="pdf-lab-prod-convergence-visual-grid">
              <figure>
                <figcaption>Full page (p{selectedRow.page})</figcaption>
                <div className="pdf-lab-prod-convergence-page-proof">
                  <img src={selectedRow.pageImageUri} alt={`Full PDF page ${selectedRow.page}`} />
                  {selectedRow.bbox && <i style={getBboxStyle(selectedRow.bbox)} />}
                </div>
              </figure>
              <figure>
                <figcaption>Selected crop (zoomed)</figcaption>
                <div className="pdf-lab-prod-convergence-crop-proof">
                  <img src={selectedRow.cropUri} alt={`Selected extraction crop for ${selectedRow.elementId}`} />
                </div>
                <div className="pdf-lab-prod-convergence-zoom" aria-label="Static crop zoom controls">
                  <span>−</span><b>176%</b><span>+</span><em>Fit width</em>
                </div>
              </figure>
            </div>
          </section>

          <section className="pdf-lab-prod-convergence-delta" data-qid="pdf-lab:convergence:expected-actual-delta">
            <article className="expected">
              <h3>Expected</h3>
              <p>{selectedCaseSummary.expected}</p>
            </article>
            <article className="actual">
              <h3>Actual</h3>
              <p>{selectedCaseSummary.actual}</p>
            </article>
            <article className="delta">
              <h3>Delta</h3>
              <p>{selectedCaseSummary.delta}</p>
            </article>
          </section>

          <div className="pdf-lab-prod-convergence-debug">
            <details>
              <summary
                data-qid="pdf-lab:convergence:debug-json"
                data-qs-action="PDF_LAB_CONVERGENCE_OPEN_DEBUG_JSON"
                title="Open debug raw JSON"
              >
                Debug raw JSON
              </summary>
              <pre>{JSON.stringify(selectedRecord, null, 2)}</pre>
            </details>
            <details>
              <summary
                data-qid="pdf-lab:convergence:run-status"
                data-qs-action="PDF_LAB_CONVERGENCE_OPEN_RUN_STATUS"
                title="Open run status artifacts"
              >
                Run status artifacts
              </summary>
              <div className="pdf-lab-prod-convergence-ledger">
                <span>Parity <b>{comparison?.passed ? 'passed' : 'not proven'}</b></span>
                <span>Coverage loop <b>{coverageLoop?.next_action ?? 'missing'}</b></span>
                <span>Status blockers <b>{statusReport?.blockers.length ?? 'unknown'}</b></span>
              </div>
            </details>
            <details>
              <summary
                data-qid="pdf-lab:convergence:provenance"
                data-qs-action="PDF_LAB_CONVERGENCE_OPEN_PROVENANCE"
                title="Open provenance details"
              >
                Provenance
              </summary>
              <div className="pdf-lab-prod-convergence-ledger">
                <span>Element <b>{selectedRow.elementId}</b></span>
                <span>Key <b>{selectedRow.arangoKey}</b></span>
                <span>JSON pointer <b>{selectedRow.jsonPointer ?? 'missing'}</b></span>
              </div>
            </details>
          </div>
        </section>

        <aside className="pdf-lab-prod-convergence-decision" data-qid="pdf-lab:convergence:decision-lane">
          <header>
            <div>
              <h2>Human decision</h2>
              <p>Clarify ambiguity</p>
            </div>
            <span>Needs review</span>
          </header>

          <fieldset className="pdf-lab-prod-convergence-options">
            <legend>Clarify ambiguity</legend>
            {clarificationOptions.map(option => (
              <label key={option.value} className={clarification === option.value ? 'selected' : ''}>
                <input
                  type="radio"
                  name="pdf-lab-convergence-clarification"
                  value={option.value}
                  checked={clarification === option.value}
                  data-qid={`pdf-lab:convergence:clarification:${option.value}`}
                  data-qs-action="PDF_LAB_CONVERGENCE_SET_CLARIFICATION"
                  title={`Set clarification: ${option.label}`}
                  onChange={() => setClarification(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </fieldset>

          <button
            type="button"
            className="pdf-lab-prod-convergence-primary-action"
            data-qid="pdf-lab:convergence:primary-action"
            data-qs-action={primaryAction.action}
            title={primaryAction.title}
            onClick={() => {
              if (primaryAction.action === 'PDF_LAB_CONVERGENCE_REQUEST_MORE_EVIDENCE') {
                onOpenCandidateAudit(selectedRow)
              }
            }}
          >
            {primaryAction.label}
          </button>
          <button
            type="button"
            className="pdf-lab-prod-convergence-secondary-action"
            data-qid="pdf-lab:convergence:accept-extraction"
            data-qs-action="PDF_LAB_CONVERGENCE_ACCEPT_EXTRACTION"
            title="Accept the current deterministic extraction as correct"
          >
            Accept extraction as correct
          </button>
          <button
            type="button"
            className="pdf-lab-prod-convergence-secondary-action"
            data-qid="pdf-lab:convergence:reject-non-issue"
            data-qs-action="PDF_LAB_CONVERGENCE_REJECT_NON_ISSUE"
            title="Reject this candidate as a non-issue"
          >
            Reject non-issue
          </button>

          <section className="pdf-lab-prod-convergence-fixpath">
            <h3>Fix path <small>gated by evidence</small></h3>
            <button
              type="button"
              disabled={!promoteFixtureReady}
              data-qid="pdf-lab:convergence:promote-fixture"
              data-qs-action="PDF_LAB_CONVERGENCE_PROMOTE_REGRESSION_FIXTURE"
              title={promoteFixtureReady ? 'Promote this case to a regression fixture' : 'Promote regression fixture requires evidence gates to pass'}
            >
              Promote regression fixture <small>{promoteFixtureReady ? 'ready' : 'requires evidence gates'}</small>
            </button>
            <button
              type="button"
              data-qid="pdf-lab:convergence:tune-preset"
              data-qs-action="PDF_LAB_CONVERGENCE_TUNE_PRESET"
              title="Open preset tuning path for this candidate"
              onClick={() => onOpenStage('parity-audit')}
            >
              Tune preset
            </button>
            <button
              type="button"
              data-qid="pdf-lab:convergence:create-parser-task"
              data-qs-action="PDF_LAB_CONVERGENCE_CREATE_PARSER_PATCH_TASK"
              title="Create a parser patch task for this extractor failure"
            >
              Create parser patch task
            </button>
          </section>

          <section className="pdf-lab-prod-convergence-impact" data-qid="pdf-lab:convergence:impact">
            <h3>Impact</h3>
            <div><span>Similar cases</span><b>{similarCaseCount}</b></div>
            <div><span>Impacted docs</span><b>{impactedDocCount}</b></div>
            <div><span>Fixture family</span><b>NIST control tables</b></div>
          </section>
        </aside>
      </section>
    </main>
  )
}

function CoverageElementRow({
  onOpenCandidateAudit,
  onSelect,
  row,
  selected,
}: {
  onOpenCandidateAudit: (row: CandidateAuditRow) => void
  onSelect: (elementId: string) => void
  row: CandidateAuditRow
  selected: boolean
}) {
  const TypeIcon = getCoverageElementIcon(row.elementType)
  const ProofIcon = getCoverageProofIcon(row.finalState)
  const copyProvenanceKey = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    await navigator.clipboard.writeText(row.arangoKey)
  }
  const selectFromKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(row.elementId)
    }
  }

  return (
    <div
      className={`pdf-lab-prod-elements-row ${row.finalState} ${selected ? 'selected' : ''}`}
      data-qid={`pdf-lab:coverage:candidate:${row.elementId}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(row.elementId)}
      onDoubleClick={() => onOpenCandidateAudit(row)}
      onKeyDown={selectFromKeyboard}
    >
      <span>
        <strong>{row.elementId}</strong>
        <b>{formatFamily(row.elementType)} · p{row.page}</b>
        <small>{row.elementText.slice(0, 64) || row.proofIssue}</small>
      </span>
      <img src={row.cropUri} alt={`${row.elementType} crop from page ${row.page}`} />
      <em title={formatFamily(row.elementType)} aria-label={formatFamily(row.elementType)}>
        <TypeIcon size={16} strokeWidth={2} />
      </em>
      <mark title={row.proofLabel} aria-label={row.proofLabel}>
        <ProofIcon size={16} strokeWidth={2} />
      </mark>
      <button
        type="button"
        className="pdf-lab-prod-provenance-copy"
        title={`Copy provenance key: ${row.arangoKey}`}
        aria-label={`Copy provenance key for ${row.elementId}`}
        onClick={copyProvenanceKey}
      >
        <KeyRound size={16} strokeWidth={2} />
      </button>
    </div>
  )
}

function StatusMetric({
  detail,
  label,
  state,
  value,
}: {
  detail: string
  label: string
  state: 'bad' | 'ok' | 'warn'
  value: string
}) {
  return (
    <div className={`pdf-lab-prod-status-metric ${state}`}>
      <span>{label}</span>
      <b>{value}</b>
      <small>{detail}</small>
    </div>
  )
}

function CandidateAuditModal({ row, onClose }: { row: CandidateAuditRow; onClose: () => void }) {
  const extractionRecord = {
    _key: row.arangoKey,
    element_id: row.elementId,
    type: row.elementType,
    page: row.page,
    bbox: row.bbox ?? null,
    source: row.source,
    json_pointer: row.jsonPointer ?? null,
    crop_uri: row.cropUri,
    text: row.elementText,
    proof_state: row.proofLabel,
    proof_issue: row.proofIssue,
    memory_status: row.memoryStatus,
  }

  return (
    <div className="pdf-lab-prod-candidate-modal" role="dialog" aria-modal="true" aria-label={`Extracted element ${row.elementId} details`}>
      <div className="pdf-lab-prod-candidate-modal-card">
        <header>
          <div>
            <span>Element evidence inspection</span>
            <h2>{formatFamily(row.elementType)} · page {row.page} · {row.proofLabel}</h2>
            <p>{row.proofIssue}</p>
          </div>
          <button type="button" onClick={onClose}>Close</button>
        </header>
        <div className="pdf-lab-prod-candidate-modal-grid">
          <section className="pdf-lab-prod-candidate-modal-visual">
            <h3>PDF crop and page context</h3>
            <figure className="pdf-lab-prod-candidate-crop-proof">
              <img src={row.cropUri} alt={`${row.elementType} crop ${row.elementId}`} />
              <figcaption>Readable source crop artifact for visual comparison</figcaption>
            </figure>
            <figure className="pdf-lab-prod-candidate-page-proof">
              <div className="pdf-lab-prod-candidate-page-frame">
                <img src={row.pageImageUri} alt={`Page ${row.page}`} />
                {row.bbox && <span className="pdf-lab-prod-candidate-bbox" style={getBboxStyle(row.bbox)} />}
              </div>
              <figcaption>Full page with extraction bbox overlay</figcaption>
            </figure>
          </section>
          <section className="pdf-lab-prod-candidate-modal-record">
            <h3>Extracted payload and provenance</h3>
            <div className="pdf-lab-prod-candidate-modal-details">
              <div><b>Element</b><code>{row.elementId}</code></div>
              <div><b>Type</b><span>{formatFamily(row.elementType)}</span></div>
              <div><b>pdf_oxide source</b><code>{row.source}</code></div>
              <div><b>Extracted text / payload</b><span>{row.elementText}</span></div>
              <div><b>Agent correction</b><span>{row.correctedByAgent ? `${row.finding?.classification ?? row.finding?.kind}` : 'none'}</span></div>
              <div><b>Agent note</b><span>{row.finding?.recommended_engine_fix ?? row.proofIssue}</span></div>
              <div><b>Provenance key</b><code>{row.arangoKey}</code></div>
              <div><b>Recall status</b><span>{row.memoryStatus}</span></div>
              <div><b>JSON pointer</b><code>{row.jsonPointer ?? 'not provided'}</code></div>
              <div><b>BBox</b><code>{row.bbox ? `[${row.bbox.join(', ')}]` : 'not provided'}</code></div>
            </div>
            <pre className="pdf-lab-prod-candidate-arango-json">{JSON.stringify(extractionRecord, null, 2)}</pre>
          </section>
        </div>
      </div>
    </div>
  )
}

function PaneHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="pdf-lab-prod-pane-head">
      <h2>{title}</h2>
      <p>{detail}</p>
    </div>
  )
}

function TagList({ tags }: { tags: string[] }) {
  return (
    <div className="pdf-lab-prod-tags">
      {tags.map(tag => <span key={tag}>{tag}</span>)}
    </div>
  )
}
