export type ProofCardStatus = "PASS" | "BLOCKED" | "FAIL";

export type ProofReceiptReference = {
	id: string;
	schema?: string | null;
	status?: string | null;
	verdict?: string | null;
};

export type ProofCardSource = {
	source_id: string;
	title: string;
	source_type?: string;
	method?: string;
	relevance?: string;
	url?: string;
	claims_supported?: string[];
	limitations?: string[];
	classification?: string;
	used_for?: string[];
	retrieved_at?: string;
};

export type ProofCardMethod = {
	method_id: string;
	name: string;
	complexity?: string;
	access_mode?: string;
	technique_class?: string;
	source?: string;
	inherited?: boolean;
	expected_usefulness?: string;
	rationale?: string;
	known_risks?: string[];
	evidence_refs?: string[];
};

export type ChildResearchSummary = {
	schema: "battle.child_research_receipts.v1";
	status?: string;
	mocked?: boolean;
	provider_live?: boolean;
	fixture_fallback_used?: boolean;
	query?: {
		value?: string;
		method?: string;
		external_tool_called?: boolean;
		safety_receipt?: string | null;
	};
	sources?: ProofCardSource[];
	source_receipts?: Array<{
		schema?: string;
		status?: string;
		method?: string;
		source_type?: string;
		source_count?: number;
		review_required?: boolean;
	}>;
	claims?: { proves?: string[]; does_not_prove?: string[] };
};

export type ChildCandidateMethodsSummary = {
	schema: "battle.child_candidate_methods.v1";
	status?: string;
	mocked?: boolean;
	provider_live?: boolean;
	methods?: ProofCardMethod[];
	claims?: { proves?: string[]; does_not_prove?: string[] };
};

export type ChildExploitGenomeSummary = {
	schema: "battle.child_exploit_genome.v1";
	status?: string;
	mocked?: boolean;
	provider_live?: boolean;
	agentic?: boolean;
	created_by?: string;
	selected_method_ids?: string[];
	rejected_method_ids?: string[];
	strategy?: Record<string, string>;
	claims?: { proves?: string[]; does_not_prove?: string[] };
};

export type BattleNormalizedProofCardFixtureV1 = {
	schema: "battle.normalized_proof_card_fixture.v1";
	proof_card_kind: "pr3b_tau_research_combiner";
	battle_id: string;
	run_id: string;
	generated_at?: string;
	proof_mode: string;
	status: ProofCardStatus;
	reason?: string | null;
	mocked: false;
	live: string;
	agentic: boolean;
	fixture_fallback_used: false;
	tau_execution?: string;
	tau_receipt_status?: string | null;
	tau_receipt_verdict?: string | null;
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
	};
	node_status: Record<string, string>;
	node_verdict?: Record<string, string>;
	artifacts: {
		child_research_receipts: ChildResearchSummary;
		child_candidate_methods: ChildCandidateMethodsSummary;
		child_exploit_genome: ChildExploitGenomeSummary;
	};
	receipt_refs: ProofReceiptReference[];
	scoreboard?: Record<string, unknown>;
	copy: {
		headline: string;
		subhead: string;
		status_label: string;
	};
};

export type ProofCardLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "PROOF_FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "CONTRACT_VALIDATION_FAILED";

export type ProofCardLoadError = {
	code: ProofCardLoadErrorCode;
	title: string;
	detail: string;
};

export const PROOF_CARD_NODE_ORDER = [
	"lineage-summarizer",
	"research-scout",
	"method-combiner",
	"exploit-code-author",
] as const;

export type ProofCardNodeId = (typeof PROOF_CARD_NODE_ORDER)[number];
