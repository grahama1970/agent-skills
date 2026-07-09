import type {
	BattleEffectCue,
	BattleEvent,
	BattleNormalizedUxFixture,
	Lane,
} from "./battle-types";
import { battleTimelineDomain } from "./battle-timeline-domain";
import {
	collectReceiptBeatCrossings,
	collectReceiptBeats,
	receiptBeatToBattleEvent,
	receiptBeatToEffectCue,
	receiptBeatsVisibleAtPlayhead,
} from "./battle-receipt-beats";
import type { HungerGamesTicker } from "./battle-hunger-games-notifications";

export type ReplayCueCrossing = BattleEffectCue & HungerGamesTicker & {
	soundCue: NonNullable<BattleEffectCue["soundCue"]>;
};

export function battleEventForLaneEvent() {
	return undefined;
}

export function collectReplayCueCrossings(args: {
	prevSeconds: number;
	nextSeconds: number;
	fixture: BattleNormalizedUxFixture;
	lanes: Lane[];
	battleEvents: BattleEvent[];
}): ReplayCueCrossing[] {
	const beats = collectReceiptBeats(args.fixture, args.lanes);
	return collectReceiptBeatCrossings({
		prevSeconds: args.prevSeconds,
		nextSeconds: args.nextSeconds,
		beats,
	}).map((beat) => ({
		...receiptBeatToEffectCue(beat),
		...beat.react.liveEvent,
		soundCue: beat.react.soundCue,
	}));
}

export function battleEventsForPlayhead(
	battleEvents: BattleEvent[],
	fixture: BattleNormalizedUxFixture,
	lanes: Lane[],
	playheadSeconds: number,
): BattleEvent[] {
	void battleEvents;
	const beats = collectReceiptBeats(fixture, lanes);
	return receiptBeatsVisibleAtPlayhead(beats, playheadSeconds).map((beat) => receiptBeatToBattleEvent(beat, fixture));
}

export function replayTickerEventsForPlayhead(
	battleEvents: BattleEvent[],
	fixture: BattleNormalizedUxFixture,
	lanes: Lane[],
	playheadSeconds: number,
): BattleEvent[] {
	void battleEvents;
	const beats = collectReceiptBeats(fixture, lanes);
	const visible = receiptBeatsVisibleAtPlayhead(beats, playheadSeconds, 3);
	if (!visible.length) return battleEventsForPlayhead(battleEvents, fixture, lanes, playheadSeconds);
	return visible.map((beat) => receiptBeatToBattleEvent(beat, fixture));
}
