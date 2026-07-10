export type RuntimeJudgeStatus = "PASS" | "BLOCKED" | "FAIL";

export type RuntimeReceiptReference = {
	id: string;
	label?: string | null;
	schema?: string | null;
	status?: string | null;
	verdict?: string | null;
	sha256?: string | null;
};

export type IoSummary = {
	available: boolean;
	line_count_total: number;
	lines: string[];
	redacted?: boolean;
	redaction_reasons?: string[];
};

export type SpecimenTargetContact = {
	status: string;
	observed: boolean;
	entrypoint?: string | null;
	does_not_prove?: string[];
};

export type SpecimenRun = {
	specimen_id: string;
	runtime_status: string;
	raw_status?: string;
	compile_ok: boolean;
	runtime_ok: boolean;
	exit_code: number;
	elapsed_seconds?: number;
	stdout_summary: IoSummary;
	stderr_summary: IoSummary;
	target_contact: SpecimenTargetContact;
	does_not_prove?: string[];
	[key: string]: unknown;
};

export type BattleNormalizedRuntimeJudgeFixtureV1 = {
	schema: "battle.normalized_runtime_judge_fixture.v1";
	fixture_kind: "pr4_runtime_judge";
	battle_id: string;
	run_id: string;
	generated_at: string;
	proof_mode: string;
	status: RuntimeJudgeStatus;
	mocked: false;
	live: string;
	runtime: {
		docker: {
			image: string;
			network: string;
			timeout_seconds: number;
			user?: string;
			cap_drop_all?: boolean;
			no_new_privileges?: boolean;
			command_shape?: string[];
			[key: string]: unknown;
		};
		specimen_runs: SpecimenRun[];
		summary: {
			generated_specimens: number;
			compile_failed: number;
			runtime_failed: number;
			runnable_unproven: number;
			target_contact_unproven: number;
			best_specimen_id?: string | null;
			[key: string]: unknown;
		};
	};
	judge: {
		judge_status: string;
		judge_verified_exploits: number;
		judge_progression: string[];
		does_not_prove?: string[];
		[key: string]: unknown;
	};
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
		compile_passed_is_not_runnable?: boolean;
		target_contact_is_not_exploit_success?: boolean;
	};
	receipt_refs: RuntimeReceiptReference[];
	provenance: {
		raw_paths_redacted?: boolean;
		tau_runtime_paths_exposed?: boolean;
		command_loop_paths_exposed?: boolean;
		provider_workspace_paths_exposed?: boolean;
		docker_mount_paths_exposed?: boolean;
		raw_stdout_paths_exposed?: boolean;
		raw_stderr_paths_exposed?: boolean;
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

export type RuntimeLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "RUNTIME_FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "CONTRACT_VALIDATION_FAILED";

export type RuntimeLoadError = {
	code: RuntimeLoadErrorCode;
	title: string;
	detail: string;
};
