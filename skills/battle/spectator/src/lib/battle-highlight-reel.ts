import type { BattleNormalizedUxFixture, Lane } from "./battle-types";
import {
	collectReceiptBeats,
	heroReceiptBeats,
	nextReceiptBeat,
	type ReceiptBeat,
} from "./battle-receipt-beats";

/** @deprecated use ReceiptBeat */
export type BattleHighlightBeat = {
	seconds: number;
	laneId: string;
	eventId: string;
	kind: string;
};

export function collectHighlightBeats(fixture: BattleNormalizedUxFixture, lanes: Lane[]): BattleHighlightBeat[] {
	return heroReceiptBeats(collectReceiptBeats(fixture, lanes)).map((beat) => ({
		seconds: beat.camera.focusSeconds,
		laneId: beat.laneId,
		eventId: beat.eventId,
		kind: beat.kind,
	}));
}

export function nextHighlightBeat(fixture: BattleNormalizedUxFixture, lanes: Lane[], currentSeconds: number): BattleHighlightBeat | null {
	const beat = nextReceiptBeat(heroReceiptBeats(collectReceiptBeats(fixture, lanes)), currentSeconds);
	if (!beat) return null;
	return { seconds: beat.camera.focusSeconds, laneId: beat.laneId, eventId: beat.eventId, kind: beat.kind };
}

export function focusSecondsForHighlightBeat(beat: Pick<BattleHighlightBeat, "seconds">): number {
	return beat.seconds;
}

export function receiptBeatManifest(fixture: BattleNormalizedUxFixture, lanes: Lane[]): ReceiptBeat[] {
	return collectReceiptBeats(fixture, lanes);
}
