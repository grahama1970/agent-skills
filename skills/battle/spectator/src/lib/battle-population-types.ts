export type PopulationStatus = "PASS" | "BLOCKED" | "FAIL";

export type PopulationReceiptReference = {
	id: string;
	label?: string | null;
	schema?: string | null;
	status?: string | null;
	verdict?: string | null;
	sha256?: string | null;
};

export type PopulationMethod = {
	method_id: string;
	name: string;
	complexity?: string;
	source?: string;
	technique_class?: string;
};

export type SpecimenCard = {
	specimen_id: string;
	generation: number;
	parent_specimen_id?: string | null;
	compile_status: string;
	runtime_status: string;
	judge_status: string;
	judge_verified_exploits: number;
	selected_method_ids: string[];
	selected_methods?: PopulationMethod[];
	inherited_methods?: string[];
	provider_authorship: {
		provider_live: boolean;
		agentic?: boolean;
		authored_by: string;
		does_not_prove?: string[];
		[key: string]: unknown;
	};
	target_contact: {
		status: string;
		observed: boolean;
		entrypoint?: string | null;
		does_not_prove?: string[];
	};
	fitness: {
		tier: number;
		tier_label: string;
		compile_ok: boolean;
		runtime_ok: boolean;
		target_contact_unproven: boolean;
		judge_confirmed_exploit: boolean;
		method_count: number;
		novel_method_combination?: boolean;
		[key: string]: unknown;
	};
	novelty: {
		method_count: number;
		inherited_method_count: number;
		method_combo_hash: string;
		[key: string]: unknown;
	};
	selection: {
		status: string;
		promoted: boolean;
		reason: string;
		[key: string]: unknown;
	};
	[key: string]: unknown;
};

export type LineageEdge = {
	edge_id: string;
	edge_type: string;
	from_specimen_id: string;
	to_specimen_id: string;
	spawn_cause?: string;
	inherited_methods?: string[];
	promoted?: boolean;
	abandoned?: boolean;
	[key: string]: unknown;
};

export type GenerationAxisEntry = {
	generation: number;
	specimen_count: number;
	selected_count: number;
	specimen_ids: string[];
};

export type BattleNormalizedPopulationFixtureV1 = {
	schema: "battle.normalized_population_fixture.v1";
	fixture_kind: "pr5_population";
	battle_id: string;
	run_id: string;
	generated_at: string;
	proof_mode: string;
	status: PopulationStatus;
	mocked: false;
	live: string;
	campaign: {
		campaign_id: string;
		specimen_count: number;
		generation_count: number;
		best_specimen_id?: string | null;
		verdict?: string;
		full_population_engine_proven: false;
		source_proof?: string;
		source_limitations?: string[];
		[key: string]: unknown;
	};
	generation_axis: GenerationAxisEntry[];
	specimen_cards: SpecimenCard[];
	lineage_edges: LineageEdge[];
	lineage_summary?: {
		parent_child_edges?: number;
		recombination_edges?: number;
		promoted_count?: number;
		abandoned_count?: number;
		[key: string]: unknown;
	};
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
		compile_passed_is_not_runnable?: boolean;
		target_contact_is_not_exploit_success?: boolean;
		runnable_is_not_exploit_success?: boolean;
		population_fixture_is_not_full_engine?: boolean;
	};
	receipt_refs: PopulationReceiptReference[];
	provenance: {
		raw_paths_redacted?: boolean;
		tau_runtime_paths_exposed?: boolean;
		command_loop_paths_exposed?: boolean;
		provider_workspace_paths_exposed?: boolean;
		docker_raw_paths_exposed?: boolean;
		credentials_exposed?: boolean;
		[key: string]: unknown;
	};
	copy: {
		headline: string;
		subhead: string;
		status_label: string;
		boundary_notice?: string;
	};
	frontend_handoff?: Record<string, string>;
};

export type PopulationLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "POPULATION_FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "CONTRACT_VALIDATION_FAILED";

export type PopulationLoadError = {
	code: PopulationLoadErrorCode;
	title: string;
	detail: string;
};
