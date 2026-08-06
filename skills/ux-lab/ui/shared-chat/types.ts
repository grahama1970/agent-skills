/**
 * Shared chat types — unified across Embry Terminal + SPARTA Explorer.
 */

export type EntityType = "skill" | "control" | "cwe" | "attack" | "framework" | "sparta" | "domain";

export type CascadeLayer = "recall" | "intent" | "llm" | "aql";

export interface RecallItem {
	_key?: string;
	_source?: string;
	control_id?: string;
	name?: string;
	question?: string;
	problem?: string;
	solution?: string;
	content?: string;
	scores?: { bm25?: number; graph?: number; dense?: number; freshness?: number };
}

export interface RecallResult {
	found: boolean;
	confidence: number;
	items: RecallItem[];
}

export interface EntityRef {
	id: string;
	label: string;
	type?: EntityType;
	exists: boolean;
	/** Regex-derived references are display-only and are not source-grounded evidence. */
	displayOnly?: boolean;
	source?: "regex" | "structured" | string;
}

export interface EvidenceGate {
	gate: string;
	passed: boolean;
	detail: string;
	duration?: number;
}

export interface EvidenceCaseSpan {
	text?: string;
	span?: [number, number];
	kind?: string;
	framework?: string;
	name?: string;
	grounded_to_framework?: boolean;
	start?: number;
	end?: number;
	type?: string;
	[key: string]: unknown;
}

export interface ThreatMatrixSummary {
	totalTechniques: number;
	totalTactics: number;
	satisfied: number;
	inconclusive: number;
	notSatisfied: number;
	noEvidence: number;
	datalake: string;
}

export interface ReasoningStep {
	id: string;
	type: "recall" | "skill" | "text" | "pending";
	skill?: string;
	status: "running" | "done" | "failed" | "pending";
	summary: string;
	detail?: string;
	duration?: number;
	startedAt?: number;
	confidence?: number;
	recallItems?: RecallItem[];
	children?: ReasoningStep[];
}

export type EvidenceRunEventStatus = "pending" | "running" | "done" | "failed";

export type EvidenceRunEvent =
	| {
			type: "evidence_run_started";
			runId: string;
			timestamp: number;
			skill?: string;
			requestId?: string;
	  }
	| {
			type: "evidence_gate";
			runId: string;
			timestamp: number;
			gate: string;
			status: EvidenceRunEventStatus;
			passed?: boolean;
			detail?: string;
			duration?: number;
	  }
	| {
			type: "evidence_run_completed";
			runId: string;
			timestamp: number;
			verdict?: string;
			grade?: string;
			gatesPassed?: number;
			gatesTotal?: number;
			tier?: string;
	  }
	| {
			type: "evidence_run_failed";
			runId: string;
			timestamp: number;
			message?: string;
	  }
	| {
			type: "evidence_run_text";
			runId: string;
			timestamp: number;
			text: string;
	  };

export interface EvidenceRunTrace {
	runId: string;
	requestId?: string;
	skill?: string;
	status: EvidenceRunEventStatus;
	startedAt?: number;
	completedAt?: number;
	events: EvidenceRunEvent[];
}

export interface FigureSpec {
	title?: string;
	caption?: string;
	width?: number;
	height?: number;
}

export interface Artifact {
	id: string;
	title: string;
	type:
		| "code"
		| "html"
		| "svg"
		| "markdown"
		| "react-table"
		| "graph"
		| "figure"
		| "gsn-diagram"
		| "pdf"
		| "document"
		| string;
	content: string;
	language?: string;
	data?: unknown;
	figureSpec?: FigureSpec;
	description?: string;
	code?: string;
	sourceSkill?: string;
	caseId?: string;
	sampleDerived?: boolean;
	provenanceState?: string;
	sha256?: string;
	caption?: string;
	sectionHeading?: string;
	sectionIntro?: string;
	preview?: { kind: string; content: string };
	refreshedAt?: string;
}

export interface Skill {
	name: string;
	description: string;
	triggers: string[];
}

export interface Agent {
	id: string;
	name: string;
	color: string;
}

// Glossary term from /create-evidence-case daemon
export interface GlossaryTerm {
	term: string;
	type:
		| "control"
		| "cwe_weakness"
		| "attack_technique"
		| "attack_mobile_technique"
		| "countermeasure"
		| "technique"
		| "domain_term";
	definition?: string;
}

export interface EvidenceCaseData {
	case_id?: string;
	qraKey?: string;
	verdict: string;
	grade: string;
	gates_passed: number;
	gates_total: number;
	gate_summary: string;
	gate_trace?: Array<{ gate: string; passed: boolean; detail: string; duration?: number }>;
	control_ids: string[];
	tier: string;
	drift?: { old_verdict: string; new_verdict: string; timestamp: string };
	recall_count?: number;
	recall_breakdown?: Record<string, number>;
	source_traceability?: Record<string, number>;
	description?: string;
	answer?: string;
	answer_blocks?: Array<{
		type?: string;
		text?: string;
		citation_ids?: string[];
		[key: string]: unknown;
	}>;
	memory_answer?: {
		schema?: string;
		status?: string;
		answer_blocks?: Array<{
			type?: string;
			text?: string;
			citation_ids?: string[];
			[key: string]: unknown;
		}>;
		citations?: Array<{
			id?: string;
			canonical_ref?: string;
			title?: string;
			source_locator?: string;
			[key: string]: unknown;
		}>;
		retrieval_diagnostics?: Record<string, unknown>;
		actions?: Array<{
			name?: string;
			target_ref?: string;
			[key: string]: unknown;
		}>;
		missing_artifacts?: Array<Record<string, unknown>>;
		[key: string]: unknown;
	};
	question?: string;
	bound_artifact?: string;
	artifact_hash?: string;
	artifact?: {
		name?: string;
		sha256?: string;
		page_count?: number;
		extraction_state?: string;
	};
	claims?: string[];
	citations?: string[];
	receipts?: Array<{ id?: string; state?: string; summary?: string }>;
	trace_state?: string;
	approval_state?: string;
	response_action?: "answer" | "deflect" | "clarify" | string;
	blocker_reason?: string;
	response_policy?: Record<string, unknown>;
	chat_evidence_binding?: Record<string, unknown>;
	chat_evidence_run_binding?: Record<string, unknown>;
	glossary?: GlossaryTerm[];
	spans?: EvidenceCaseSpan[];
	diagnostics?: Record<string, unknown>;
	evidence_case_version?: Record<string, unknown>;
	gap_review?: Record<string, unknown>;
	gap_review_status?: string;
	human_review_state?: string;
	proposed_correction?: Record<string, unknown>;
	correction_lineage?: Record<string, unknown>;
	metadata?: {
		gates_passed?: number;
		gates_total?: number;
		gate_trace?: Array<{ gate: string; passed: boolean; detail: string; duration?: number }>;
	};
	/**
	 * grahama1970/sparta#30. `fixture` marks a synthetic development-only evidence case that
	 * must never be persisted, exported as a receipt, or granted speech authority.
	 */
	evidence_class?: "fixture" | "live";
	audit_valid?: boolean;
	fixture_disclosure?: string;
}

export interface ChatMessage {
	id?: string;
	role: "user" | "assistant" | "system" | "agent";
	content: string;
	timestamp?: number;
	/**
	 * Legacy diagnostic-only assistant turn (e.g. "Found N related QRAs via CWE
	 * search.") tombstoned on session load; rendered collapsed and clearly
	 * invalidated, never as a current substantive answer (grahama1970/sparta#36).
	 */
	supersededDiagnostic?: boolean;
	/** UI flag for BinaryExplorerView chat journal */
	isExplanation?: boolean;
	// Agent metadata
	agent?: string;
	skillUsed?: string;
	chainTitle?: string;
	// Recall + reasoning
	recall?: RecallResult;
	recallItems?: RecallItem[];
	reasoningSteps?: ReasoningStep[];
	// Artifacts
	artifact?: Artifact;
	artifacts?: Artifact[];
	// Structured results
	verdict?: { state: string; gates: EvidenceGate[]; tier?: string };
	matrixSummary?: ThreatMatrixSummary;
	evidenceCase?: EvidenceCaseData;
	evidenceRun?: EvidenceRunTrace;
	// Entity + classification
	entities?: EntityRef[];
	cascadeLayer?: CascadeLayer;
	// SPARTA-specific
	type?: "natural" | "aql";
	alertType?: "threat-delta";
	_querySpec?: Record<string, unknown>;
	clarifyOptions?: Array<{ question: string }>;
	resultCount?: number;
	// Interaction
	feedback?: "up" | "down" | null;
	/** scillm transport room: human | project_agent | worker */
	transportCollaborator?: string;
	answerState?: "bound" | "clarify" | "deflect";
	askPrompts?: string[];
	tryPrompts?: string[];
	blockedReasons?: string[];
	heardQueryLabel?: string;
	inputChannel?: "voice" | "typed";
	/** Pre-computed /create-evidence-case spans for question highlighting */
	entitySpans?: EvidenceCaseSpan[];
	/**
	 * Structured, non-rendered classification for a message. Call sites previously smuggled
	 * this through an `as Omit<ChatMessage, ...>` cast; grahama1970/sparta#30 requires it to
	 * be a real field, because `evidence_class` / `audit_valid` are what persistence and
	 * export guards read to tell a development fixture from a governed result.
	 */
	metadata?: Record<string, unknown>;
}

// ── Activity Feed Types ─────────────────────────────────────────────────

export interface ActivityEvent {
	type:
		| "agent_started"
		| "agent_completed"
		| "agent_finding"
		| "presence_update"
		| "suggestion"
		| "suggestion_resolved";
	agent?: string;
	project?: string;
	summary?: string;
	entity?: string;
	entityType?: EntityType;
	controlId?: string;
	finding?: string;
	confidence?: number;
	id?: string;
	status?: string;
	timestamp: number;
}

export interface PresenceEntry {
	userId: string;
	displayName: string;
	project?: string;
	status: "active" | "idle" | "offline";
	lastSeen: number;
	isAgent: boolean;
	agentType?: string;
}

export interface AgentSuggestion {
	id: string;
	agent: string;
	controlId: string;
	finding: string;
	evidence: string;
	confidence: number;
	status: "pending" | "accepted" | "rejected";
	resolvedBy?: string;
	resolvedAt?: number;
}
