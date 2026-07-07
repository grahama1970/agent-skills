import type {
	BattleEffectCue,
	BattleEffectCueKind,
	BattleEvent,
	BattleNormalizedUxFixture,
	Lane,
	LaneEvent,
	SoundCue,
} from "./battle-types";
import { KILL_SHOT_TRAVEL_SECONDS, killShotVariant, resolveKillShotImpact } from "../engine/battle-pixi-kill-shot";
import { eventElapsedSeconds, fixtureUsesElapsedAxis } from "./battle-elapsed-axis";
import { battleTimelineDomain } from "./battle-timeline-domain";
import { hungerGamesNotification, type HungerGamesTicker } from "./battle-hunger-games-notifications";

export type ReplayCueCrossing = BattleEffectCue & HungerGamesTicker & {
	soundCue: SoundCue;
};

function laneEventSeconds(
	fixture: BattleNormalizedUxFixture,
	allottedSeconds: number,
	event: LaneEvent,
	useElapsed: boolean,
): number {
	return eventElapsedSeconds(event, allottedSeconds, useElapsed);
}

function crossedForward(prevSeconds: number, nextSeconds: number, atSeconds: number): boolean {
	return prevSeconds + 0.0001 < atSeconds && nextSeconds + 0.0001 >= atSeconds;
}

export function battleEventForLaneEvent(battleEvents: BattleEvent[], laneId: string, laneEvent: LaneEvent): BattleEvent | undefined {
	if (laneEvent.kind === "blocked") {
		return battleEvents.find(
			(event) => event.red_lane_id === laneId && (event.event_type?.includes("blocked") || event.ui?.runner_state === "blocked"),
		);
	}
	if (laneEvent.kind === "killed") {
		return battleEvents.find(
			(event) => event.red_lane_id === laneId && (event.event_type?.includes("kill") || event.ui?.runner_state === "killed"),
		);
	}
	if (laneEvent.kind === "blue_blast") {
		return battleEvents.find(
			(event) =>
				(event.target_actor_ids?.includes(laneId) || event.red_lane_id === laneId) &&
				(event.ui?.blue_animation || event.event_type?.includes("blue")),
		);
	}
	return battleEvents.find((event) => event.id === laneEvent.id || event.red_lane_id === laneId);
}


function soundForBlueBlast(laneEvent: LaneEvent): SoundCue {
	return killShotVariant(laneEvent) === "kill_cannon" ? "kill_cannon" : "blue_blast";
}

function baseCue(
	fixture: BattleNormalizedUxFixture,
	lane: Lane,
	laneEvent: LaneEvent,
	atSeconds: number,
	cue: BattleEffectCueKind,
	soundCue: SoundCue,
	ticker: HungerGamesTicker,
): ReplayCueCrossing {
	return {
		eventId: laneEvent.id,
		laneId: lane.id,
		cue,
		atSeconds,
		receiptId: laneEvent.receiptId ?? "",
		proofMode: fixture.proof_mode === "receipt_backed_fixture" ? "receipt_backed" : "design_fixture",
		soundCue,
		...ticker,
	};
}

export function collectReplayCueCrossings(args: {
	prevSeconds: number;
	nextSeconds: number;
	fixture: BattleNormalizedUxFixture;
	lanes: Lane[];
	battleEvents: BattleEvent[];
}): ReplayCueCrossing[] {
	const { prevSeconds, nextSeconds, fixture, lanes, battleEvents } = args;
	if (nextSeconds <= prevSeconds) return [];

	const domain = battleTimelineDomain(fixture, false);
	const allottedSeconds = domain.allottedSeconds;
	const useElapsed = fixtureUsesElapsedAxis(fixture);
	const crossings: ReplayCueCrossing[] = [];

	for (const lane of lanes) {
		for (const laneEvent of lane.events) {
			if (!laneEvent.proven) continue;
			const atSeconds = laneEventSeconds(fixture, allottedSeconds, laneEvent, useElapsed);
			const battleEvent = battleEventForLaneEvent(battleEvents, lane.id, laneEvent);

			if (laneEvent.kind === "blue_blast") {
				if (crossedForward(prevSeconds, nextSeconds, atSeconds)) {
					crossings.push(
						baseCue(
							fixture,
							lane,
							laneEvent,
							atSeconds,
							"blue_blast",
							soundForBlueBlast(laneEvent),
							hungerGamesNotification("blue_blast", lane),
						),
					);
				}

				const impactAt = atSeconds + KILL_SHOT_TRAVEL_SECONDS;
				if (crossedForward(prevSeconds, nextSeconds, impactAt)) {
					const impactKind = resolveKillShotImpact(lane, laneEvent, allottedSeconds, useElapsed);
					const impactLaneEvent =
						lane.events.find((event) => event.proven && (event.kind === "killed" || event.kind === "blocked")) ?? laneEvent;
					const impactBattleEvent = battleEventForLaneEvent(battleEvents, lane.id, impactLaneEvent);
					if (impactKind === "killed") {
						crossings.push({
							...baseCue(
								fixture,
								lane,
								impactLaneEvent,
								impactAt,
								"killed",
								"kill_cannon",
								hungerGamesNotification("killed", lane),
							),
							eventId: `${laneEvent.id}:impact-killed`,
						});
					} else if (impactKind === "blocked") {
						crossings.push({
							...baseCue(
								fixture,
								lane,
								impactLaneEvent,
								impactAt,
								"blocked",
								"blue_blast",
								hungerGamesNotification("blocked", lane),
							),
							eventId: `${laneEvent.id}:impact-blocked`,
						});
					}
				}
				continue;
			}

			if ((laneEvent.kind === "blocked" || laneEvent.kind === "killed") && crossedForward(prevSeconds, nextSeconds, atSeconds)) {
				const hasBlueBlast = lane.events.some(
					(event) => event.proven && event.kind === "blue_blast" && laneEventSeconds(fixture, allottedSeconds, event, useElapsed) <= atSeconds,
				);
				if (hasBlueBlast) continue;
				crossings.push(
					baseCue(
						fixture,
						lane,
						laneEvent,
						atSeconds,
						laneEvent.kind,
						laneEvent.kind === "killed" ? "kill_cannon" : "blue_blast",
						hungerGamesNotification(laneEvent.kind === "killed" ? "killed" : "blocked", lane),
					),
				);
			}
		}
	}

	return crossings.sort((a, b) => a.atSeconds - b.atSeconds);
}

export function battleEventsForPlayhead(
	battleEvents: BattleEvent[],
	fixture: BattleNormalizedUxFixture,
	lanes: Lane[],
	playheadSeconds: number,
): BattleEvent[] {
	const domain = battleTimelineDomain(fixture, false);
	const allottedSeconds = domain.allottedSeconds;
	const useElapsed = fixtureUsesElapsedAxis(fixture);
	const visible: BattleEvent[] = [];
	const seen = new Set<string>();

	for (const lane of lanes) {
		for (const laneEvent of lane.events) {
			if (!laneEvent.proven) continue;
			const atSeconds = laneEventSeconds(fixture, allottedSeconds, laneEvent, useElapsed);
			if (atSeconds > playheadSeconds + 0.001) continue;
			const battleEvent = battleEventForLaneEvent(battleEvents, lane.id, laneEvent);
			if (battleEvent && !seen.has(battleEvent.id)) {
				seen.add(battleEvent.id);
				visible.push(battleEvent);
			}
		}
	}

	return visible.slice(-3);
}


export function replayTickerEventsForPlayhead(
	battleEvents: BattleEvent[],
	fixture: BattleNormalizedUxFixture,
	lanes: Lane[],
	playheadSeconds: number,
): BattleEvent[] {
	const crossings = collectReplayCueCrossings({
		prevSeconds: 0,
		nextSeconds: playheadSeconds,
		fixture,
		lanes,
		battleEvents,
	});
	if (crossings.length === 0) {
		return battleEventsForPlayhead(battleEvents, fixture, lanes, playheadSeconds);
	}

	return crossings.slice(-3).map((cue) => {
		const laneEvent = lanes
			.flatMap((lane) => lane.events.map((event) => ({ lane, event })))
			.find(({ event }) => event.id === cue.eventId || `${event.id}:impact-killed` === cue.eventId || `${event.id}:impact-blocked` === cue.eventId);
		const matched = laneEvent
			? battleEventForLaneEvent(battleEvents, laneEvent.lane.id, laneEvent.event)
			: undefined;
		if (matched) {
			return {
				...matched,
				event_type: `replay.${cue.cue}`,
				ui: {
					...matched.ui,
					notification: cue.notification,
					notification_prefix: cue.prefix,
					notification_highlight: cue.highlight,
					notification_highlight_tone: cue.highlightTone,
					sound_cue: cue.soundCue,
				},
			};
		}
		return {
			id: cue.eventId,
			ts: new Date(0).toISOString(),
			battle_id: fixture.battle_id,
			team: cue.cue === "blue_blast" || cue.cue === "blocked" ? "blue" : "red",
			actor_id: cue.laneId,
			actor_kind: cue.cue === "blue_blast" || cue.cue === "blocked" ? "patch_agent" : "exploit_agent",
			event_type: `replay.${cue.cue}`,
			summary: cue.notification,
			proof_mode: fixture.proof_mode,
			ui: {
				notification: cue.notification,
				notification_prefix: cue.prefix,
				notification_highlight: cue.highlight,
				notification_highlight_tone: cue.highlightTone,
				sound_cue: cue.soundCue,
				importance: "hero",
			},
		} as unknown as BattleEvent;
	});
}
