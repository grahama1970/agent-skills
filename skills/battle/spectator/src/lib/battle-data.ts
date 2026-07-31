import { generatedBattleFixture } from "./battle-data.generated";
import { isBattleDesignView, mockupDesignLanes } from "./battle-mockup-lanes";
import { isBattleReceiptReplayView } from "./battle-receipt-replay";
import { isBattleLiveView } from "./battle-transport-registry";
import { adaptReceiptLanesForDesignPartition } from "./receipt-mockup-adapter";
import { hasGeneticLifecycle, lanesWithGeneticLifecycleEvents } from "./battle-genetic-lifecycle";
import type {
	BattleEvent,
	BattleNormalizedUxFixture,
	BattleReceiptRef,
	BluePatchAction,
	Lane,
	LeaderboardEntry,
} from "./battle-types";

type GeneratedBattleFixture = BattleNormalizedUxFixture & {
	bluePatchActions?: BluePatchAction[];
	scoreboard?: {
		red_score?: number;
		blue_score?: number;
		tdsr?: number;
		asc?: number;
		verdict?: string;
	};
};

function withDevLineagePreview(source: Lane[]): Lane[] {
	if (typeof window === "undefined" || !import.meta.env.DEV) return source;
	if (!new URLSearchParams(window.location.search).has("lineage")) return source;
	if (source.some((lane) => lane.parentId || lane.children?.length)) return source;
	const [first, second] = source;
	if (!first || !second) return source;
	const childId = `${first.id}-child-preview`;
	return [
		{ ...first, children: [childId], lineColor: "purple" as const },
		{
			...second,
			id: childId,
			name: `${first.name} · spawn`,
			parentId: first.id,
			generation: Math.max(2, (first.generation ?? 1) + 1),
			lineColor: "green" as const,
			xStart: Math.min(95, (first.xEnd ?? 80) * 0.72 + 4),
			events: first.events.some((event) => event.kind === "handoff")
				? []
				: [
						{
							id: `${first.id}:preview-handoff`,
							kind: "handoff" as const,
							x: Math.min(90, (first.xEnd ?? 80) * 0.72),
							label: "SPAWN",
						},
					],
		},
	];
}

export const legacyReceiptBackedFixture = generatedBattleFixture as unknown as GeneratedBattleFixture;

const EMPTY_RECEIPT_FIXTURE: GeneratedBattleFixture = {
	...(legacyReceiptBackedFixture as GeneratedBattleFixture),
	lanes: [],
	events: [],
	leaderboard: [],
	receipts: [],
};

export function activeBattleFixture(receiptFixture?: GeneratedBattleFixture | null): GeneratedBattleFixture {
	if (isBattleReceiptReplayView() || isBattleLiveView()) {
		return receiptFixture ?? EMPTY_RECEIPT_FIXTURE;
	}
	return legacyReceiptBackedFixture;
}

/** @deprecated use activeBattleFixture() for route-aware fixture selection */
export const receiptBackedFixture = legacyReceiptBackedFixture;

export const lanes: Lane[] = legacyReceiptBackedFixture.lanes;

export function battleLanesForView(source?: Lane[], receiptFixture?: GeneratedBattleFixture | null): Lane[] {
	const fixtureLanes = source ?? activeBattleFixture(receiptFixture).lanes;
	if (isBattleDesignView()) return mockupDesignLanes;
	const adapted = adaptReceiptLanesForDesignPartition(withDevLineagePreview(fixtureLanes));
	if (receiptFixture && hasGeneticLifecycle(receiptFixture)) {
		return lanesWithGeneticLifecycleEvents(adapted, receiptFixture);
	}
	return adapted;
}
export function battleLeaderboardForView(receiptFixture?: GeneratedBattleFixture | null): LeaderboardEntry[] {
	return activeBattleFixture(receiptFixture).leaderboard;
}

export function battleEventsForView(receiptFixture?: GeneratedBattleFixture | null): BattleEvent[] {
	return activeBattleFixture(receiptFixture).events;
}

export function battleReceiptsForView(receiptFixture?: GeneratedBattleFixture | null): BattleReceiptRef[] {
	return activeBattleFixture(receiptFixture).receipts;
}

export function battleBluePatchActionsForView(receiptFixture?: GeneratedBattleFixture | null): BluePatchAction[] {
	return activeBattleFixture(receiptFixture).bluePatchActions ?? [];
}

export const leaderboard: LeaderboardEntry[] = legacyReceiptBackedFixture.leaderboard;
export const battleEvents: BattleEvent[] = legacyReceiptBackedFixture.events;
export const receipts: BattleReceiptRef[] = legacyReceiptBackedFixture.receipts;
export const bluePatchActions: BluePatchAction[] = legacyReceiptBackedFixture.bluePatchActions ?? [];

export const receiptBackedBattleEvents: BattleEvent[] = battleEvents;
export const receiptBackedReceipts: BattleReceiptRef[] = receipts;

export const demoFixtureLanes: Lane[] = [];
export const demoFixtureLeaderboard: LeaderboardEntry[] = [];
export const demoFixtureBattleEvents: BattleEvent[] = [];
export const demoFixtureBluePatchActions: BluePatchAction[] = [];
