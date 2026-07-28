export type AdaptiveTeam = "red" | "blue";

export type AdaptiveReceiptRef = {
	receipt_id: string | null;
	schema: string;
	sha256: string;
	status: string | null;
	verdict: string | null;
};

export type AdaptiveLineageLane = {
	lane_id: string;
	team: AdaptiveTeam;
	generation: number;
	role: "parent" | "child";
	parent_lane_id: string | null;
	display_name: string;
	visible_from_elapsed_seconds: number;
	active_from_elapsed_seconds: number;
	end_elapsed_seconds: number;
	actor_visual: {
		variant_id: "v13-shared-runner";
		cosmetic_only: true;
		semantic_authority: false;
	};
};

type AdaptiveLineageEdgeBase = {
	edge_id: string;
	team: AdaptiveTeam;
	parent_lane_id: string;
	child_lane_id: string;
	visible_from_elapsed_seconds: number;
};

export type AdaptiveSpawnLineageEdge = AdaptiveLineageEdgeBase & {
	edge_kind?: "spawn";
	requested_receipt_ref: AdaptiveReceiptRef;
	authorized_receipt_ref: AdaptiveReceiptRef;
};

export type AdaptiveMemoryLineageEdge = AdaptiveLineageEdgeBase & {
	edge_kind: "memory_continuation";
	promoted_receipt_ref: AdaptiveReceiptRef;
	written_receipt_ref: AdaptiveReceiptRef;
	recalled_receipt_ref: AdaptiveReceiptRef;
	use_receipt_ref: AdaptiveReceiptRef;
};

export type AdaptiveLineageEdge = AdaptiveSpawnLineageEdge | AdaptiveMemoryLineageEdge;

export type AdaptiveLineageEvent = {
	seq: number;
	event_id: string;
	elapsed_seconds: number;
	event_type: string;
	generation: number | null;
	team: AdaptiveTeam | null;
	lane_id: string | null;
	scope: "lane" | "generation_pair" | "campaign";
	affected_lane_ids: string[];
	receipt_ref: AdaptiveReceiptRef;
	payload: Record<string, unknown>;
};

export type CanonicalDualTeamMechanicsNode = {
	lane_id: string;
	team: AdaptiveTeam;
	generation: number;
	role: "parent" | "child" | string;
	parent_lane_id: string | null;
	mutation_operator: string | null;
	selection_disposition: string;
	observation_receipt_ref?: AdaptiveReceiptRef | null;
	fitness_receipt_ref?: AdaptiveReceiptRef | null;
	genome_delta_receipt_ref?: AdaptiveReceiptRef | null;
	selection_receipt_ref?: AdaptiveReceiptRef | null;
};

export type CanonicalDualTeamMechanicsEdge = {
	edge_id: string;
	team: AdaptiveTeam;
	parent_lane_id: string;
	child_lane_id: string;
	visible_from_elapsed_seconds: number;
	requested_receipt_ref?: AdaptiveReceiptRef;
	authorized_receipt_ref?: AdaptiveReceiptRef;
};

export type CanonicalDualTeamMechanicsTrees = {
	schema: "battle.canonical_dual_team_mechanics_trees.v1";
	isolation: {
		status: string;
		edge_policy: string;
		cross_team_edge_count: number;
		opponent_private_projection_reference_count: number;
	};
	teams: Record<AdaptiveTeam, {
		team: AdaptiveTeam;
		nodes: CanonicalDualTeamMechanicsNode[];
		edges: CanonicalDualTeamMechanicsEdge[];
	}>;
};

export type CanonicalDualTeamScoreboard = {
	schema: "battle.canonical_dual_team_scoreboard.v1";
	status: string;
	policy_id: string;
	red_score: number;
	blue_score: number;
	inputs: Array<Record<string, unknown>>;
	claims?: { proves?: string[]; does_not_prove?: string[] };
};

export type CanonicalDualTeamContract = {
	schema: "battle.canonical_dual_team_contract.v1";
	status: string;
	red_node_count: number;
	blue_node_count: number;
	red_edge_count: number;
	blue_edge_count: number;
	cross_team_edge_count: number;
	source_run_count: number;
	resolved_reference_count: number;
	score_status: string;
};

export type BattleNormalizedAdaptiveLineageFixtureV1 = {
	schema: "battle.normalized_adaptive_lineage_fixture.v1";
	fixture_id: string;
	battle_id: string;
	run_id: string;
	proof_mode: "receipt_backed_fixture";
	live_source: string;
	causal_continuity_proven: true;
	campaign: {
		campaign_clock_id: string;
		elapsed_seconds: number;
		generation_count: 2;
		generation_ids?: [number, number];
		teams: ["red", "blue"];
	};
	lanes: AdaptiveLineageLane[];
	lineage_edges: AdaptiveLineageEdge[];
	sprite_theme: {
		schema: "battle.sprite_theme.v1";
		theme_id: string;
		proof_scope: "cosmetic_identity_only";
		shared_atlas: true;
		semantic_authority: false;
		variants: {
			"v13-shared-runner": { sprite_id: "plague_nurgling"; scale: 1 };
		};
	};
	renderer_contract: {
		schema: "battle.adaptive_lineage_renderer_contract.v1";
		time_authority: string;
		event_order_authority: "event.seq";
		child_visibility_event: "spawn_authorized" | "memory_promoted";
		child_pending_state: "AUTHORIZED_PENDING" | "MEMORY_PENDING";
		child_activation_event: "child_research_materialized" | "memory_use_acknowledged";
		pair_judge_event_is_global: true;
		selection_is_not_victory: true;
		no_promotion_is_not_promoted: true;
		memory_use_is_not_improvement?: true;
		sprite_identity_is_cosmetic_only: true;
	};
	events: AdaptiveLineageEvent[];
	receipt_refs: AdaptiveReceiptRef[];
	selection: Record<string, unknown>;
	memory_evaluation: Record<string, unknown>;
	claim_boundary: { may_claim: string[]; must_not_claim: string[] };
	provenance: {
		raw_paths_redacted: true;
		source_run_count: number;
		source_proof_id: string;
		projection_kind?: "adaptive_lineage_v13" | "adaptive_memory_v14";
	};
	memory_lifecycle?: Record<string, unknown>;
	source_campaign?: Record<string, unknown>;
	mechanics_trees?: CanonicalDualTeamMechanicsTrees;
	scoreboard?: CanonicalDualTeamScoreboard;
	canonical_dual_team_contract?: CanonicalDualTeamContract;
};
