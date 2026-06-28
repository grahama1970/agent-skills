// --- Supervisor types (from supervisor_*.json) ---
export interface SupervisorState {
	label: string;
	root: string;
	status: string; // "running" | "stopped" | "error"
	updated_at: string;
	run_id: string;
	run_log: string;
	child_pid: number;
	restart_count: number;
	run_count: number;
	cycle_completed?: number;
	cycle_failures?: number;
	child_age_seconds?: number;
	review_heartbeat_fresh: boolean;
	review_heartbeat_age_seconds: number;
	run_metrics: RunMetrics;
	failure_buckets: Record<string, number>;
	stop_file?: string;
}

export interface RunMetrics {
	phase: string; // "discover" | "extract" | "score" | "debug" | "evaluate" | "summary"
	phase_age_seconds?: number;
	documents_total?: number;
	documents_analyzed?: number;
	documents_missing?: number;
	documents_missing_ratio?: number | null;
	rolling_docs_analyzed?: number;
	rolling_avg_score?: number | null;
	rolling_fail_ratio?: number | null;
	rolling_critical_doc_ratio?: number | null;
	overall_average_score?: number | null;
	last_loop_healthy?: boolean | null;
	last_loop_score?: number | null;
	last_loop_fail_ratio?: number | null;
	loop_cycle_count?: number;
	extraction_success_count: number;
	extraction_cached_profile_count: number;
	extraction_failed_count: number;
	extraction_timeout_count?: number;
	extraction_missing_structural_count?: number;
	extraction_timeout_hint_count?: number;
	extraction_attempts: number;
	extraction_deferred_count?: number;
	preflight_failed_count?: number;
	extraction_fail_rate_pct: number;
	extraction_timeout_rate_pct: number;
	extraction_missing_structural_rate_pct?: number;
	timeout_model_decisions: number;
	timeout_model_used_count?: number;
	timeout_model_used_rate_pct?: number;
	timeout_model_high_risk_count?: number;
	timeout_model_last_risk?: number;
	recent_failed_events?: unknown[];
	recent_failed_pdfs?: string[];
	recent_failed_pdf_count?: number;
	recommended_watchdog_seconds?: number;
	adaptive_heartbeat_timeout_seconds?: number;
	last_extracted_pdf?: string;
	memory_retry_queue_count: number;
	memory_retry_dead_letter_count: number;
	memory_retry_retried_count?: number;
	memory_retry_succeeded_count?: number;
	extraction_throughput_per_hour: number;
	workers: number;
	worker_aggregate: WorkerAggregate;
	blacklist_count?: number;
	deferred_review_count?: number;
	expected_fail_floor?: number;
	quality_gate_action: string; // "continue_extracting" | "pause_and_debug" | "escalate_persona_review"
	quality_gate_reason: string;
	quality_gate_consecutive_failures?: number;
}

export interface WorkerAggregate {
	worker_count: number;
	worker_files?: string[];
	max_elapsed_seconds: number;
	max_last_output_age_seconds: number;
}

// --- Worker state (from review_state_worker_*.json) ---
export interface WorkerState {
	completed: number;
	stats: {
		worker_id?: number;
		elapsed_seconds: number;
		last_output_age_seconds: number;
	};
	current_item: string;
	last_updated: string;
}

// --- Corpus coverage ---
export interface CorpusCoverage {
	sectors: SectorCoverage[];
	total_pdfs: number;
	total_extracted: number;
	overall_coverage_pct: number;
}

export interface SectorRating {
	jurisdiction: string;
	distribution: string;
	family: string;
}

export interface SectorCoverage {
	name: string; // "arxiv" | "defense" | "nasa" | "nist" | "engineering" | "industry" | "adversarial"
	total: number;
	extracted: number;
	pending: number;
	failed: number;
	coverage_pct: number;
	target: number;
	deficit: number;
	rating?: SectorRating;
	previousRating?: SectorRating;
}

// --- Quarantine ---
export interface QuarantineEntry {
	id: string;
	filename: string;
	path: string;
	category: string;
	reason: "low-confidence" | "extraction-error" | "novel-layout" | "timeout";
	timestamp: string;
	pages?: number;
	extraction_time_ms?: number;
	fail_rate?: number;
	cascade_tier?: number;
	scores?: Record<string, number>;
	error?: string;
}

// --- Quarantine Detail (section-centric) ---
export interface QuarantineDetail {
	id: string;
	pdf_path: string;
	page_count: number;
	extraction_available: boolean;
	extraction_error?: string;
	blocks: QuarantineBlock[];
	sections: Section[];
	tables: Table[];
	figures: Figure[];
	cascade_log: CascadeDecision[];
}

export interface QuarantineBlock {
	id: string;
	page: number;
	bbox: [number, number, number, number];
	text: string;
	block_type: string;
	font_size: number;
	confidence?: number;
	header_disposition?: string;
	section_idx?: number;
}

// --- Provider info ---
export interface ProviderInfo {
	name: string;
	class_name: string;
	extensions: string[];
	extraction_count: number;
	success_rate: number;
	avg_time_ms: number;
	family: "document" | "spreadsheet" | "markup" | "data" | "image" | "pdf" | "presentation" | "web";
}

// --- Cascade decision points ---
export interface CascadeEscalation {
	filename: string;
	doc_id?: string;
	confidence: number;
	rust_guess: string; // "Accept" | "Reject"
	classifier_disposition?: string; // "Accept" | "Reject" | "Escalate"
	features: Record<string, number | boolean | string>;
	timestamp?: string;
}

export interface CascadeDecisionPoint {
	name: string; // "header-verdict" | "pdf-profile" | "pdf-strategy"
	total_samples: number;
	shadow_file_size_bytes: number;
	date_range: { start: string; end: string };
	disposition_counts: Record<string, number>;
	confidence_distribution: number[]; // 5 bins: [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]
	tier_counts?: Record<string, number>; // e.g. { "Tier 0": 400000, "Tier 0.5": 120000, "Tier 2": 9340 }
	promotion_status: "Early" | "Learning" | "Ready";
	agreement_rate: number;
	wilson_lower_bound: number;
	samples_vs_threshold: { current: number; threshold: number };
	recent_escalations?: CascadeEscalation[];
}

// --- Quality trends ---
export interface QualityPresetBreakdown {
	preset: string; // "nist" | "defense" | "arxiv" | "engineering"
	pass_rate?: number;
	fail_rate?: number;
	quarantine_rate?: number;
	extraction_quality_mean?: number;
	throughput_per_hour?: number;
}

// --- Quality trends ---
export interface QualityTrendPoint {
	date: string;
	fail_rate?: number;
	throughput?: number;
	quality_score?: number;
	memory_ingestion_rate?: number;
	cascade_agreement?: number;
	pass_rate?: number;
	quarantine_rate?: number;
	extraction_quality_mean?: number;
	throughput_per_hour?: number;
	preset_breakdown?: QualityPresetBreakdown[];
}

// --- Re-exported from extract-pdf viewer for PDF drill-down ---
export interface ExtractionResult {
	version: string;
	engine: string;
	engine_version: string;
	profile: DocumentProfile;
	blocks: Block[];
	sections: Section[];
	tables: Table[];
	figures: Figure[];
	cascade_decisions?: CascadeDecision[];
	taxonomy_tags?: TaxonomyTag[];
}

export interface DocumentProfile {
	domain: string;
	preset: string;
	complexity_score: number;
	page_count: number;
	is_scanned: boolean;
	primary_font?: string;
	primary_font_size?: number;
	strategy?: string;
}

export interface Block {
	id: string;
	page: number;
	bbox: [number, number, number, number];
	text: string;
	block_type: string; // "Header" | "Body" | "Boilerplate" | "Caption" | "Footnote"
	font_size: number;
	is_header: boolean;
	header_level?: number;
	header_disposition?: string; // "Accept" | "Reject" | "Escalate"
	taxonomy_tags?: string[];
}

export interface Section {
	title: string;
	display_title: string;
	level: number;
	section_number?: string;
	page_start: number;
	page_end: number;
	parent_idx?: number;
	header_disposition?: string;
}

export interface Table {
	page_number: number;
	bbox: [number, number, number, number];
	strategy: string;
	rows: string[][];
	score?: number;
}

export interface Figure {
	figure_id: string;
	page: number;
	bbox: [number, number, number, number];
	image_path?: string;
	context_above?: string;
}

export interface CascadeDecision {
	decision_point: string; // "header-verdict" | "pdf-profile" | "pdf-strategy"
	predicted: string;
	confidence: number;
	tier: number;
	features?: Record<string, number | boolean | string>;
}

export interface TaxonomyTag {
	text: string;
	category: "mind" | "heart";
	confidence: number;
}

// --- Batch result (used in PDF drill-down) ---
export interface BatchResult {
	filename: string;
	status: "success" | "error" | "timeout";
	result?: ExtractionResult;
	error?: string;
	duration_ms: number;
}

// --- Requirements view types ---
export type EvidenceStatus = "pass" | "partial" | "none";
export type ProofStatus = "proven" | "partial" | "unproven" | "axiom";

export interface RequirementEntry {
	id: string;
	reqId: string; // e.g. "03.01.01"
	text: string;
	nistSource: string; // e.g. "AC-2"
	spartaRef?: string; // e.g. "SS-005"
	sectionId: string;
	evidence: EvidenceStatus;
	proofStatus: ProofStatus;
	lean4Preview?: string; // theorem declaration snippet
	lean4Fn?: string; // function name in the theorem
}

export interface RequirementSection {
	id: string;
	num: string; // e.g. "3.1"
	title: string;
	level: number; // 0=top, 1=sub, 2=subsub
	reqCount: number;
	children: RequirementSection[];
}

// --- Monitor strip types ---
export type MonitorEventStatus = "pass" | "warn" | "fail" | "info";

export interface MonitorStripEvent {
	id: string;
	timestamp: string;
	status: MonitorEventStatus;
	source: string; // e.g. "monitor-codebase"
	message: string;
}

// --- V8 ThreatMatrixView ---
export interface ThreatCell {
	controlId: string;
	controlName: string;
	sector: string;
	coverageScore: number; // 0-1
	evidenceCount: number;
	status: "covered" | "partial" | "gap";
}

export interface ThreatDrillthrough {
	cell: ThreatCell;
	evidenceCases: EvidenceCase[];
	relatedControls: string[];
	spartaMapping?: string;
}

export interface EvidenceCase {
	id: string;
	claim: string;
	verdict: "supported" | "refuted" | "insufficient";
	confidence: number;
	sources: string[];
	createdAt: string;
}

// --- V9 LemmaGraphView ---
export interface LemmaNode {
	id: string;
	label: string;
	proofStatus: ProofStatus;
	dependencyCount: number;
	impactScore: number; // what breaks if this fails
	lean4Snippet?: string;
	requirementIds: string[];
}

export interface LemmaEdge {
	source: string;
	target: string;
	relation: "depends_on" | "proves" | "contradicts";
	strength: number;
}

// --- V10 MonitorView ---
export interface MonitorService {
	name: string;
	status: "healthy" | "degraded" | "down";
	lastCheck: string;
	latencyMs?: number;
	errorRate?: number;
	details?: string;
}

export interface MonitorEvent {
	timestamp: string;
	source: string;
	level: "info" | "warn" | "error";
	message: string;
	linkTo?: string;
}

// --- BBox Workspace (V1 overhaul) ---
export interface TocEntry {
	title: string;
	page: number;
	qid?: string; // Associated QID marker for validation
}

export interface BboxBlock {
	id: string;
	page: number;
	bbox: [number, number, number, number]; // x1, y1, x2, y2 normalized 0..1
	blockType:
		| "table"
		| "header"
		| "figure"
		| "text"
		| "equation"
		| "list_item"
		| "caption"
		| "page_number"
		| "boilerplate";
	semanticType?: string;
	text: string;
	confidence: number;
	cascadeTrail?: CascadeStep[];
	sectionId?: string;
	editState?: BboxEditState;
	// PDF Lab extensions
	qids?: string[]; // QID markers extracted from this block
	tocEntries?: TocEntry[]; // Parsed TOC entries if this is a TOC block
	reviewNotes?: string[];
	flagged?: boolean;
	hasOpenComments?: boolean;
	humanEdited?: boolean;
	humanEditedAt?: string;
	reviewStatus?: "active" | "verified" | "rejected" | "ignored";
}

export interface CascadeStep {
	tier: "T0" | "T0.5" | "T2";
	tierName: string; // 'Rust heuristic', 'RF classifier', 'Human'
	disposition: "accept" | "reject" | "escalate";
	confidence: number;
}

export interface BboxEditState {
	isEditing: boolean;
	originalBbox: [number, number, number, number];
	originalType: string;
	dirty: boolean;
}

export interface ReextractResult {
	scope: "section" | "page";
	targetId: string;
	blocksAdded: number;
	blocksRemoved: number;
	blocksModified: number;
	confidenceDelta: number;
	pipelineSteps: PipelineStep[];
}

export interface PipelineStep {
	name: string;
	status: "pending" | "running" | "done" | "error";
	durationMs?: number;
}
