export type SynthesisStatus = "PASS" | "BLOCKED" | "FAIL";

export type SynthesisReceiptReference = {
	id: string;
	label?: string | null;
	schema?: string | null;
	status?: string | null;
	verdict?: string | null;
	sha256?: string | null;
};

export type SynthesisCodePreview = {
	available: boolean;
	line_count_total: number;
	lines: string[];
	max_bytes?: number;
	max_lines?: number;
	preview_sha256?: string;
	redacted?: boolean;
	redaction_reasons?: string[];
	truncated?: boolean;
};

export type BattleNormalizedSynthesisFixtureV1 = {
	schema: "battle.normalized_synthesis_fixture.v1";
	fixture_kind: "pr3c_provider_code_author";
	battle_id: string;
	run_id: string;
	generated_at: string;
	proof_mode: string;
	status: SynthesisStatus;
	mocked: false;
	live: string;
	agentic: boolean;
	provider_live: true;
	fixture_fallback_used: false;
	stage_scope: {
		included_through: string;
		included_nodes: string[];
		excluded_nodes: string[];
		downstream_receipts_ignored: boolean;
	};
	source_run?: Record<string, unknown>;
	node_status: Record<string, string>;
	node_verdict?: Record<string, string>;
	provider_authorship: {
		status: string;
		provider_live: true;
		agentic: boolean;
		authored_by: string;
		observed_provider: string;
		observed_model: string;
		requested_provider?: string | null;
		requested_model?: string | null;
		provider_run_id_present: boolean;
		provider_session_id_present: boolean;
		provider_run_ref_sha256?: string;
		code_sha256: string;
		code_bytes: number;
		goal_hash_bound?: boolean;
		output_hash_bound?: boolean;
		claim_boundary_passed?: boolean;
		[key: string]: unknown;
	};
	specimen: {
		schema: string;
		specimen_id: string;
		language: string;
		code_artifact_label: string;
		code_sha256: string;
		code_bytes: number;
		code_preview: SynthesisCodePreview;
		child_lane_id?: string;
		generation?: number;
		created_by?: string;
		provider_live?: boolean;
		agentic?: boolean;
		selected_method_ids?: string[];
		inherited_method_ids?: string[];
		[key: string]: unknown;
	};
	research: {
		status?: string;
		method?: string;
		external_tool_called?: boolean;
		provider_live?: boolean;
		review_required?: boolean;
		source_count?: number;
		sources?: Array<Record<string, unknown>>;
		[key: string]: unknown;
	};
	genome: {
		status?: string;
		created_by?: string;
		agentic?: boolean;
		provider_live?: boolean;
		selected_method_ids?: string[];
		deferred_method_ids?: string[];
		inherited_method_ids?: string[];
		rationale_summary?: string;
		strategy?: Record<string, string>;
		[key: string]: unknown;
	};
	execution_boundary: {
		compile_status: string;
		runtime_status: string;
		target_contact: string;
		judge_status: string;
		judge_verified_exploits: number;
		packet_behavior: string;
		memory_promotion: string;
	};
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
	};
	receipt_refs: SynthesisReceiptReference[];
	provenance: {
		raw_paths_redacted?: boolean;
		tau_runtime_paths_exposed?: boolean;
		command_loop_paths_exposed?: boolean;
		provider_workspace_paths_exposed?: boolean;
		credentials_exposed?: boolean;
		[key: string]: unknown;
	};
	copy: {
		headline: string;
		subhead: string;
		status_label: string;
		boundary_notice?: string;
	};
};

export type SynthesisLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "SYNTHESIS_FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "CONTRACT_VALIDATION_FAILED";

export type SynthesisLoadError = {
	code: SynthesisLoadErrorCode;
	title: string;
	detail: string;
};

export const SYNTHESIS_NODE_ORDER = [
	"lineage-summarizer",
	"research-scout",
	"method-combiner",
	"exploit-code-author",
] as const;
