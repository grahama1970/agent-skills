export type CompileStatus = "PASS" | "BLOCKED" | "FAIL";

export type CompileReceiptReference = {
	id: string;
	label?: string | null;
	schema?: string | null;
	status?: string | null;
	verdict?: string | null;
	sha256?: string | null;
};

export type CompileStderrSummary = {
	available: boolean;
	line_count_total: number;
	lines: string[];
	redacted?: boolean;
	redaction_reasons?: string[];
};

export type SpecimenVersion = {
	version_id: string;
	role: string;
	code_artifact_label?: string;
	code_sha256: string;
	code_bytes: number;
	compile_attempted: boolean;
	compile_status: "NOT_RUN" | "FAILED" | "PASSED";
	compile_failed?: boolean;
	compile_passed?: boolean;
	source_version_id?: string;
	stderr_summary_ref?: string;
	[key: string]: unknown;
};

export type BattleNormalizedCompileFixtureV1 = {
	schema: "battle.normalized_compile_fixture.v1";
	fixture_kind: "pr3d_compile_repair";
	battle_id: string;
	run_id: string;
	generated_at: string;
	proof_mode: string;
	status: CompileStatus;
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
		status?: string;
		provider_live: true;
		authored_by: string;
		observed_provider: string;
		observed_model: string;
		code_sha256?: string;
		code_bytes?: number;
		[key: string]: unknown;
	};
	compile: {
		status: string;
		verdict?: string;
		compiler?: string;
		compile_attempted: boolean;
		compile_failed: boolean;
		compile_passed: boolean;
		source_version_id?: string;
		compiled_version_id?: string;
		stderr_summary?: CompileStderrSummary;
		does_not_prove?: string[];
		[key: string]: unknown;
	};
	repair: {
		repair_attempted: boolean;
		repair_exhausted: boolean;
		attempt_count?: number;
		provider_repair_live?: boolean;
		[key: string]: unknown;
	};
	specimen_versions: SpecimenVersion[];
	selected_version: {
		version_id: string;
		code_sha256: string;
		compile_status: string;
		compile_failed?: boolean;
		compile_passed?: boolean;
		[key: string]: unknown;
	};
	execution_boundary: {
		runtime_status: "NOT_RUN";
		target_contact: "NOT_RUN";
		judge_status: "NOT_RUN";
		judge_verified_exploits: 0;
		packet_behavior: string;
		memory_promotion: string;
	};
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
		compile_passed_is_not_runnable?: boolean;
	};
	receipt_refs: CompileReceiptReference[];
	provenance: {
		raw_paths_redacted?: boolean;
		tau_runtime_paths_exposed?: boolean;
		command_loop_paths_exposed?: boolean;
		provider_workspace_paths_exposed?: boolean;
		compile_stderr_paths_exposed?: boolean;
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

export type CompileLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "COMPILE_FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "CONTRACT_VALIDATION_FAILED";

export type CompileLoadError = {
	code: CompileLoadErrorCode;
	title: string;
	detail: string;
};

export const COMPILE_NODE_ORDER = [
	"lineage-summarizer",
	"research-scout",
	"method-combiner",
	"exploit-code-author",
	"compile-repair",
] as const;
