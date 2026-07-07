import type { BattleNormalizedUxFixture } from "./battle-types";
import { mockupAllottedSeconds, mockupPlayheadSeconds } from "./mockup-design-fixture";

export type BattleTimelineDomain = {
	allottedSeconds: number;
	currentSeconds: number;
	source: "design_fixture" | "timeline_control" | "battle_clock";
};

export function battleTimelineDomain(fixture: BattleNormalizedUxFixture, designView: boolean): BattleTimelineDomain {
	if (designView) {
		return {
			allottedSeconds: mockupAllottedSeconds(),
			currentSeconds: mockupPlayheadSeconds(),
			source: "design_fixture",
		};
	}

	const control = fixture.battle_timeline_control;
	if (control?.time_domain) {
		const start = control.time_domain.start_seconds ?? 0;
		const allotted = control.time_domain.allotted_seconds ?? control.time_domain.end_seconds ?? 120;
		const current = control.playhead?.current_seconds ?? fixture.battle_clock?.elapsed_seconds ?? 0;
		return {
			allottedSeconds: allotted,
			currentSeconds: Math.min(allotted, Math.max(start, current)),
			source: "timeline_control",
		};
	}

	const allotted = fixture.battle_clock?.allotted_seconds ?? 120;
	const current = fixture.battle_clock?.elapsed_seconds ?? 0;
	return {
		allottedSeconds: allotted,
		currentSeconds: Math.min(allotted, Math.max(0, current)),
		source: "battle_clock",
	};
}
