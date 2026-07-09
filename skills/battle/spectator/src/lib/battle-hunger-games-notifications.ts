import type { BattleEffectCueKind, BattleNormalizedUxFixture, Lane } from "./battle-types";
import { spriteIdForLane } from "../engine/battle-lane-variant-map";
import { BATTLE_RUNNER_SPRITE_BASE_URL } from "../engine/battle-runner-sprites";

export type HungerGamesTicker = {
	notification: string;
	prefix: string;
	highlight: string;
	highlightTone: "red" | "blue" | "green";
};

function tributeLabel(lane: Lane): string {
	return (lane.name || lane.payloadId || lane.id).toUpperCase();
}

/** Arena-style copy mirroring Hunger Games cannon / elimination announcements. */
export function hungerGamesNotification(cue: BattleEffectCueKind, lane: Lane): HungerGamesTicker {
	const tribute = tributeLabel(lane);

	switch (cue) {
		case "killed":
			return {
				prefix: "BOOM — ",
				highlight: `${tribute} ELIMINATED`,
				highlightTone: "red",
				notification: `BOOM — ${tribute} eliminated`,
			};
		case "blocked":
			return {
				prefix: "Still standing — ",
				highlight: `${tribute} SURVIVES`,
				highlightTone: "green",
				notification: `Still standing — ${tribute} survives`,
			};
		case "blue_blast":
		default:
			return {
				prefix: "Blue patch inbound — ",
				highlight: `LOCKED ON ${tribute}`,
				highlightTone: "blue",
				notification: `Blue patch inbound — locked on ${tribute}`,
			};
	}
}


export type HungerGamesDeathCard = {
	tributeName: string;
	tributeInfo: string;
	portraitSrc: string;
	districtLabel: string;
};

function formatArchetype(lane: Lane): string {
	const raw = lane.actor_visual?.archetype ?? "exploit_agent";
	return raw.replace(/_/g, " ").toUpperCase();
}

/** Full-screen tribute-down card data for Hunger Games style death announcements. */
export function hungerGamesDeathCard(lane: Lane, fixture?: BattleNormalizedUxFixture): HungerGamesDeathCard {
	const spriteId = spriteIdForLane(lane, fixture?.sprite_theme);
	const family = lane.scenario?.hidden_vulnerability_family ?? fixture?.scenario?.hidden_vulnerability_family ?? "Archive path traversal";
	const cwe = fixture?.scenario?.cwe ?? "CWE-22";
	const districtLabel = `GEN ${lane.generation}`;
	const infoLines = [
		`${formatArchetype(lane)} · ${districtLabel}`,
		`Payload ${lane.payloadId}`,
		lane.mutationRationale ?? lane.summary ?? "Receipt-backed exploit eliminated by Blue patch.",
		`${cwe} · ${family}`,
	];
	return {
		tributeName: lane.name || lane.payloadId,
		tributeInfo: infoLines.join("\n"),
		portraitSrc: `${BATTLE_RUNNER_SPRITE_BASE_URL}/${spriteId}.png`,
		districtLabel,
	};
}
