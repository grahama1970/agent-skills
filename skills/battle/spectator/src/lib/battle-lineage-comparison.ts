import type { BattleNormalizedUxFixture, Lane } from "./battle-types";

export type LineageComparisonViewModel = {
	schema: "battle.lineage_comparison_preview.v1";
	compositeDemonstration: boolean;
	parent: {
		laneId: string;
		name: string;
		generation: number | null;
	} | null;
	child: {
		laneId: string;
		name: string;
		generation: number | null;
	} | null;
	inherited: string[];
	newOrUnknown: string[];
	spawnReceiptId: string | null;
	doesNotProve: string[];
	questions: string[];
};

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function buildLineageComparisonViewModel(
	fixture: BattleNormalizedUxFixture,
	compositeDemonstration: boolean,
): LineageComparisonViewModel | null {
	const lineage = asRecord((fixture as { lineage?: unknown }).lineage);
	const spawns = Array.isArray(lineage?.spawns) ? lineage!.spawns : [];
	if (!spawns.length) return null;
	const spawn = asRecord(spawns[0]);
	if (!spawn) return null;
	const parentId = typeof spawn.parent_lane_id === "string" ? spawn.parent_lane_id : null;
	const childId = typeof spawn.child_lane_id === "string" ? spawn.child_lane_id : null;
	const lanes = (fixture.lanes ?? []) as Lane[];
	const parentLane = lanes.find((lane) => lane.id === parentId) ?? null;
	const childLane = lanes.find((lane) => lane.id === childId) ?? null;
	const inherited = Array.isArray(spawn.inherited_context)
		? spawn.inherited_context.filter((item): item is string => typeof item === "string")
		: [];
	const inheritedState = asRecord(spawn.inherited_state);
	const hypothesis = typeof inheritedState?.hypothesis === "string" ? inheritedState.hypothesis : null;
	return {
		schema: "battle.lineage_comparison_preview.v1",
		compositeDemonstration,
		parent: parentLane
			? {
					laneId: parentLane.id,
					name: parentLane.name || parentLane.id,
					generation: typeof spawn.generation === "number" ? Math.max(1, spawn.generation - 1) : 1,
				}
			: null,
		child: childLane
			? {
					laneId: childLane.id,
					name: childLane.name || childLane.id,
					generation: typeof spawn.generation === "number" ? spawn.generation : 2,
				}
			: null,
		inherited,
		newOrUnknown: hypothesis ? [`active hypothesis: ${hypothesis}`] : ["child novelty not receipt-separated in this composite fixture"],
		spawnReceiptId:
			(typeof spawn.spawn_receipt_id === "string" && spawn.spawn_receipt_id) ||
			(typeof spawn.source_receipt_id === "string" && spawn.source_receipt_id) ||
			null,
		doesNotProve: [
			"adaptive intelligence",
			"child used inherited knowledge with acknowledgement",
			"single-campaign causal continuity",
			...(Array.isArray(lineage?.does_not_prove)
				? lineage!.does_not_prove.filter((item): item is string => typeof item === "string")
				: []),
		],
		questions: [
			"Why did the child exist?",
			"What did it inherit?",
			"What changed?",
			"What happened under Judge?",
			"Why was a lineage retained?",
		],
	};
}
