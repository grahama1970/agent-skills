import type { BattleEffectCueKind, Lane } from "./battle-types";

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
