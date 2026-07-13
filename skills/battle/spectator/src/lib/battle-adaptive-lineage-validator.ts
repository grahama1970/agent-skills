import type { BattleNormalizedAdaptiveLineageFixtureV1 } from "./battle-adaptive-lineage-types";

type ValidationResult =
	| { ok: true; fixture: BattleNormalizedAdaptiveLineageFixtureV1 }
	| { ok: false; error: { code: "UNSUPPORTED_SCHEMA" | "CONTRACT_VALIDATION_FAILED"; title: string; detail: string } };

const EXPECTED_LANES = ["red-g1", "red-g2", "blue-g1", "blue-g2"] as const;
const RAW_PATH_MARKERS = ["/tmp/", "tau-live", "command-loop/", "provider-workspace", "arena/private", "reviewed/"];

function record(value: unknown): Record<string, unknown> | null {
	return value != null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function fail(detail: string): ValidationResult {
	return { ok: false, error: { code: "CONTRACT_VALIDATION_FAILED", title: "ADAPTIVE LINEAGE FIXTURE INVALID", detail } };
}

export function validateAdaptiveLineageFixture(data: unknown): ValidationResult {
	const root = record(data);
	if (!root || root.schema !== "battle.normalized_adaptive_lineage_fixture.v1") {
		return { ok: false, error: { code: "UNSUPPORTED_SCHEMA", title: "UNSUPPORTED SCHEMA", detail: "Expected battle.normalized_adaptive_lineage_fixture.v1." } };
	}
	if (root.proof_mode !== "receipt_backed_fixture" || root.causal_continuity_proven !== true) return fail("Causal receipt-backed proof is required.");
	const campaign = record(root.campaign);
	if (!campaign || campaign.generation_count !== 2 || !Number.isFinite(campaign.elapsed_seconds)) return fail("Two-generation campaign clock is invalid.");

	const lanes = Array.isArray(root.lanes) ? root.lanes.map(record) : [];
	if (lanes.length !== 4 || lanes.some((lane) => !lane)) return fail("Exactly four adaptive lanes are required.");
	const laneIds = lanes.map((lane) => String(lane!.lane_id));
	if (new Set(laneIds).size !== 4 || EXPECTED_LANES.some((laneId) => !laneIds.includes(laneId))) return fail("Stable Red/Blue G1/G2 lane ids are required.");
	for (const lane of lanes) {
		const visual = record(lane!.actor_visual);
		if (!visual || visual.variant_id !== "v13-shared-runner" || visual.cosmetic_only !== true || visual.semantic_authority !== false) return fail(`Lane ${String(lane!.lane_id)} lacks the cosmetic-only sprite binding.`);
		if (!Number.isFinite(lane!.visible_from_elapsed_seconds) || !Number.isFinite(lane!.active_from_elapsed_seconds) || Number(lane!.active_from_elapsed_seconds) < Number(lane!.visible_from_elapsed_seconds)) return fail(`Lane ${String(lane!.lane_id)} has invalid visibility/activation timing.`);
	}

	const edges = Array.isArray(root.lineage_edges) ? root.lineage_edges.map(record) : [];
	if (edges.length !== 2 || edges.some((edge) => !edge)) return fail("Exactly two lineage edges are required.");
	for (const edge of edges) {
		if (!laneIds.includes(String(edge!.parent_lane_id)) || !laneIds.includes(String(edge!.child_lane_id))) return fail("Lineage edge references an unknown lane.");
		if (!record(edge!.requested_receipt_ref) || !record(edge!.authorized_receipt_ref)) return fail("Lineage edge receipt bindings are required.");
	}

	const theme = record(root.sprite_theme);
	const variant = record(record(theme?.variants)?.["v13-shared-runner"]);
	if (!theme || theme.shared_atlas !== true || theme.semantic_authority !== false || variant?.sprite_id !== "plague_nurgling" || variant.scale !== 1) return fail("The single validated plague_nurgling theme must be explicit and non-semantic.");
	const renderer = record(root.renderer_contract);
	if (!renderer || renderer.child_visibility_event !== "spawn_authorized" || renderer.child_activation_event !== "child_research_materialized" || renderer.pair_judge_event_is_global !== true || renderer.selection_is_not_victory !== true || renderer.no_promotion_is_not_promoted !== true) return fail("Renderer claim gates are incomplete.");

	const events = Array.isArray(root.events) ? root.events.map(record) : [];
	if (events.length !== 24 || events.some((event) => !event)) return fail("The retained V13 journal must contain 24 events.");
	let lastElapsed = -1;
	for (let index = 0; index < events.length; index += 1) {
		const event = events[index]!;
		if (event.seq !== index + 1) return fail("Event sequence must be contiguous.");
		const elapsed = Number(event.elapsed_seconds);
		if (!Number.isFinite(elapsed) || elapsed < lastElapsed) return fail("Event receipt-commit time must be monotonic.");
		lastElapsed = elapsed;
		const affected = Array.isArray(event.affected_lane_ids) ? event.affected_lane_ids : [];
		if (!affected.length || affected.some((laneId) => !laneIds.includes(String(laneId)))) return fail(`Event ${String(event.event_id)} has invalid affected lanes.`);
		if (event.scope === "lane" && !laneIds.includes(String(event.lane_id))) return fail(`Lane event ${String(event.event_id)} lacks a stable lane id.`);
		if (event.scope === "generation_pair" && event.lane_id !== null) return fail("Pair-level Judge events must remain global.");
	}
	if (events.filter((event) => event!.event_type === "judge_verdict" && event!.scope === "generation_pair").length !== 2) return fail("Exactly two global Judge events are required.");
	if (events.some((event) => event!.event_type === "selection_decision" && event!.scope !== "campaign")) return fail("Selection must remain campaign-scoped.");

	const serialized = JSON.stringify(data);
	if (RAW_PATH_MARKERS.some((marker) => serialized.includes(marker))) return fail("Raw runtime path leakage detected.");
	return { ok: true, fixture: data as BattleNormalizedAdaptiveLineageFixtureV1 };
}
