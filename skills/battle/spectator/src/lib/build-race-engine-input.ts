import { activeBattleFixture } from "./battle-data";
import { isBattleDesignView } from "./battle-mockup-lanes";
import { isBattleReceiptReplayView } from "./battle-receipt-replay";
import { mockupAllottedSeconds, mockupPlayheadSeconds } from "./mockup-design-fixture";
import type {
	BattleNormalizedUxFixture,
	BattleRaceEngineInput,
	BattleRaceEngineMode,
	BattleRaceEngineRowLayout,
	BattleTimelineViewportState,
	Lane,
} from "./battle-types";
import { BATTLE_LANE_LABEL_PX, BATTLE_MOCKUP_LANE_ROW_CHILD_PX, BATTLE_MOCKUP_LANE_ROW_ROOT_PX } from "./layout-constants";
import { battlePixiTestModeFromUrl } from "./is-battle-pixi-test-mode";
import { battleTimelineDomain } from "./battle-timeline-domain";

export function battleRaceEngineMode(): BattleRaceEngineMode {
	if (isBattleDesignView()) return "design_fixture";
	if (isBattleReceiptReplayView()) return "receipt_replay";
	const mode = activeBattleFixture().battle_clock?.mode;
	if (mode === "live_stream") return "live";
	return "receipt_replay";
}

export function buildRaceEngineRowLayout(lanes: Lane[]): BattleRaceEngineRowLayout[] {
	const childIds = new Set(lanes.filter((lane) => lane.parentId).map((lane) => lane.id));
	const rowScale = isBattleReceiptReplayView() && lanes.length >= 4 ? 0.8 : 1;
	let top = 0;
	return lanes.map((lane) => {
		const isChild = childIds.has(lane.id);
		const baseHeightPx = isChild ? BATTLE_MOCKUP_LANE_ROW_CHILD_PX : BATTLE_MOCKUP_LANE_ROW_ROOT_PX;
		const heightPx = Math.floor(baseHeightPx * rowScale);
		const layout = { laneId: lane.id, topPx: top, heightPx, isChild };
		top += heightPx;
		return layout;
	});
}

export function buildDefaultViewportState(
	allottedSeconds: number,
	currentSeconds: number,
	zoom = 1,
): BattleTimelineViewportState {
	return {
		zoom,
		worldLeftSeconds: 0,
		worldRightSeconds: allottedSeconds,
		currentSeconds,
		followMode: "scroll_after_threshold",
		labelWidthPx: BATTLE_LANE_LABEL_PX,
		rowHeightPx: BATTLE_MOCKUP_LANE_ROW_ROOT_PX,
	};
}

export function buildRaceEngineInput(args: {
	lanes: Lane[];
	selectedLaneId: string | null;
	zoom: number;
	currentSeconds: number;
	allottedSeconds?: number;
	onSelectLane(id: string): void;
	onSelectEvent(id: string): void;
	onEffectCue?: BattleRaceEngineInput["onEffectCue"];
	activeReceiptBeat?: BattleRaceEngineInput["activeReceiptBeat"];
	fixture?: BattleNormalizedUxFixture;
}): BattleRaceEngineInput {
	const fixture = args.fixture ?? activeBattleFixture();
	const domain = battleTimelineDomain(fixture, isBattleDesignView());
	const allotted = args.allottedSeconds ?? domain.allottedSeconds;
	const testMode = battlePixiTestModeFromUrl();
	const currentSeconds = testMode?.currentSeconds ?? args.currentSeconds;
	return {
		fixture,
		mode: battleRaceEngineMode(),
		selectedLaneId: args.selectedLaneId,
		viewport: buildDefaultViewportState(allotted, currentSeconds, args.zoom),
		onSelectLane: args.onSelectLane,
		onSelectEvent: args.onSelectEvent,
		onEffectCue: args.onEffectCue,
		activeReceiptBeat: args.activeReceiptBeat ?? null,
		testMode,
	};
}

export function defaultPixiPlayheadSeconds(): number {
	return battleTimelineDomain(activeBattleFixture(), isBattleDesignView()).currentSeconds;
}
