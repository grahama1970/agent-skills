export type AdaptiveTeam = "red" | "blue";

export type AdaptiveReceiptRef = {
	receipt_id: string | null;
	schema: string;
	sha256: string;
	status: string | null;
	verdict: string | null;
};

export type AdaptiveLineageLane = {
	lane_id: "red-g1" | "red-g2" | "blue-g1" | "blue-g2";
	team: AdaptiveTeam;
	generation: 1 | 2;
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

export type AdaptiveLineageEdge = {
	edge_id: string;
	team: AdaptiveTeam;
	parent_lane_id: string;
	child_lane_id: string;
	requested_receipt_ref: AdaptiveReceiptRef;
	authorized_receipt_ref: AdaptiveReceiptRef;
	visible_from_elapsed_seconds: number;
};

export type AdaptiveLineageEvent = {
	seq: number;
	event_id: string;
	elapsed_seconds: number;
	event_type: string;
	generation: 1 | 2 | null;
	team: AdaptiveTeam | null;
	lane_id: string | null;
	scope: "lane" | "generation_pair" | "campaign";
	affected_lane_ids: string[];
	receipt_ref: AdaptiveReceiptRef;
	payload: Record<string, unknown>;
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
		time_authority: "event.elapsed_seconds_is_receipt_commit_time";
		event_order_authority: "event.seq";
		child_visibility_event: "spawn_authorized";
		child_pending_state: "AUTHORIZED_PENDING";
		child_activation_event: "child_research_materialized";
		pair_judge_event_is_global: true;
		selection_is_not_victory: true;
		no_promotion_is_not_promoted: true;
		sprite_identity_is_cosmetic_only: true;
	};
	events: AdaptiveLineageEvent[];
	receipt_refs: AdaptiveReceiptRef[];
	selection: Record<string, unknown>;
	memory_evaluation: Record<string, unknown>;
	claim_boundary: { may_claim: string[]; must_not_claim: string[] };
	provenance: { raw_paths_redacted: true; source_run_count: 1; source_proof_id: string };
};
