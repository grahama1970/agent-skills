import type { LaneEvent } from "./battle-types";
import { isIconEvent } from "./layout-lane-events";

/** Short uppercase label for the timeline band — mockup uses single tokens, not two-line chips. */
export function phaseLabelText(event: LaneEvent): string | null {
	if (isIconEvent(event)) return null;
	const raw = (event.label ?? "").trim();
	if (event.kind === "research") return raw === "ARENA SCENARIO" ? "RESEARCH" : raw || "RESEARCH";
	if (raw === "EXPLOIT_CONFIRMED") return "EXPLOIT OK";
	if (raw === "INSUFFICIENT_EVIDENCE") return "NO BLOCK";
	if (raw === "ARENA SCENARIO") return "ARENA";
	if (raw === "RED EXPLOIT") return "RED EXPLOIT";
	if (raw === "BLUE_SUCCESS") return "BLUE SUCCESS";
	return raw || event.kind.replace(/_/g, " ").toUpperCase();
}

export function phaseLabelTitle(event: LaneEvent): string {
	const primary = phaseLabelText(event) ?? event.label ?? event.kind;
	return event.timeLabel ? `${primary} · ${event.timeLabel}` : primary;
}

export function formatMarkerTooltip(event: LaneEvent): string {
	return phaseLabelTitle(event);
}
