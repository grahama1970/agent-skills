import type { BattleEvent, Lane, LaneEvent } from "./battle-types";
import type { MockupLiveEvent } from "./mockup-design-fixture";
import { isIconEvent } from "./layout-lane-events";
import { hungerGamesNotification } from "./battle-hunger-games-notifications";

type EventBand = "top" | "bottom" | "above" | "icon";

const TOP_KINDS = new Set<LaneEvent["kind"]>(["research", "payload", "mutate", "retry"]);
const BOTTOM_LABEL_KINDS = new Set<LaneEvent["kind"]>(["blocked", "killed", "fastest_crash", "promoted"]);

function hasMockupBandSuffix(id: string) {
	return /:(top|bottom|above|icon):/.test(id);
}

function bandForReceiptEvent(event: LaneEvent): EventBand {
	if (hasMockupBandSuffix(event.id)) {
		if (event.id.includes(":top:")) return "top";
		if (event.id.includes(":bottom:")) return "bottom";
		if (event.id.includes(":above:")) return "above";
		return "icon";
	}
	if (event.label_band === "upper") return "above";
	if (event.label_band === "lower") return "bottom";
	if (isIconEvent(event)) return "icon";
	if (TOP_KINDS.has(event.kind)) return "top";
	if (BOTTOM_LABEL_KINDS.has(event.kind)) return "bottom";
	if (event.kind === "useful" || event.kind === "handoff") return "above";
	return "icon";
}

/** Remap receipt lane events to mockup partition ID suffixes (`:top:`, `:icon:`, etc.). */
export function normalizeReceiptLaneEvents(lane: Lane): Lane {
	const events = lane.events.map((event, index) => {
		if (hasMockupBandSuffix(event.id)) return event;
		const band = bandForReceiptEvent(event);
		return { ...event, id: `${lane.id}:${band}:${index}` };
	});
	return { ...lane, events };
}

export function adaptReceiptLanesForDesignPartition(lanes: Lane[]): Lane[] {
	return lanes.map(normalizeReceiptLaneEvents);
}

function liveEventTone(event: BattleEvent): MockupLiveEvent["iconTone"] {
	if (event.event_type === "tau.fastest_crash" || event.event_type === "tau.promoted") return "green";
	if (event.team === "blue" || event.event_type.startsWith("blue.")) return "blue";
	if (event.team === "red") return "red";
	return "green";
}

function liveEventIcon(event: BattleEvent): MockupLiveEvent["icon"] {
	if (event.event_type === "tau.fastest_crash") return "rocket";
	if (event.event_type === "tau.promoted") return "shield";
	if (event.event_type.startsWith("blue.")) return "shield";
	return "bug";
}

/** Map receipt-backed battle events to mockup live-event row shape (newest first). */
export function liveEventsFromBattleEvents(events: BattleEvent[], limit = 3): MockupLiveEvent[] {
	return events
		.filter((event) => event.ui.importance !== "background")
		.slice(-limit)
		.reverse()
		.map((event) => {
			const ticker =
				event.ui.notification_prefix && event.ui.notification_highlight
					? {
							prefix: event.ui.notification_prefix,
							highlight: event.ui.notification_highlight,
							highlightTone: event.ui.notification_highlight_tone ?? "green",
						}
					: event.event_type === "replay.killed"
						? hungerGamesNotification("killed", { id: event.actor_id, name: event.actor_id, payloadId: event.actor_id, generation: 1, team: "red", xStart: 0, xEnd: 0, runnerX: 0, runnerState: "advance", lineColor: "red", terminal: "killed", events: [] })
					: event.event_type === "replay.blocked" || event.event_type === "blue.blocked_red"
						? hungerGamesNotification("blocked", { id: event.red_lane_id ?? event.actor_id, name: event.red_lane_id ?? event.actor_id, payloadId: event.red_lane_id ?? event.actor_id, generation: 1, team: "red", xStart: 0, xEnd: 0, runnerX: 0, runnerState: "advance", lineColor: "red", terminal: "blocked", events: [] })
					: null;
			const summary = event.ui.notification ?? event.summary;
			const highlightMatch = summary.match(/\b([A-Z][A-Z0-9_ ]{3,})\b/);
			const highlight = ticker?.highlight ?? highlightMatch?.[1] ?? summary.split(" ").slice(-2).join(" ").toUpperCase();
			const prefix = ticker?.prefix ?? (highlightMatch ? summary.slice(0, summary.indexOf(highlightMatch[0])) : `${summary.slice(0, 24)} `);
			const highlightTone = ticker?.highlightTone ?? (liveEventTone(event) === "blue" ? "blue" : "green");
			return {
				id: event.id,
				time: new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
				icon: liveEventIcon(event),
				iconTone: liveEventTone(event),
				prefix,
				highlight,
				highlightTone,
			} satisfies MockupLiveEvent;
		});
}
