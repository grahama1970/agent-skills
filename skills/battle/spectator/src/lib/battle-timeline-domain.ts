import type { BattleNormalizedUxFixture } from "./battle-types";
import { fixtureUsesElapsedAxis } from "./battle-elapsed-axis";
import { mockupAllottedSeconds, mockupPlayheadSeconds } from "./mockup-design-fixture";

export type BattleTimelineDomain = {
	allottedSeconds: number;
	currentSeconds: number;
	source: "design_fixture" | "timeline_control" | "battle_clock" | "timeline_elapsed_axis";
};

export function battleTimelineDomain(fixture: BattleNormalizedUxFixture, designView: boolean): BattleTimelineDomain {
	if (designView) {
		return {
			allottedSeconds: mockupAllottedSeconds(),
			currentSeconds: mockupPlayheadSeconds(),
			source: "design_fixture",
		};
	}

	if (fixtureUsesElapsedAxis(fixture)) {
		const axis = fixture.timeline_elapsed_axis_model;
		const allotted =
			axis?.axis_max_elapsed_seconds ??
			fixture.battle_timeline_control?.time_domain?.allotted_seconds ??
			fixture.battle_clock?.allotted_seconds ??
			120;
		const current =
			axis?.playhead?.current_elapsed_seconds ??
			fixture.battle_timeline_control?.playhead?.current_seconds ??
			fixture.battle_clock?.elapsed_seconds ??
			0;
		return {
			allottedSeconds: allotted,
			currentSeconds: Math.min(allotted, Math.max(0, current)),
			source: "timeline_elapsed_axis",
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
