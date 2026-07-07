import type { Lane, LaneEvent, LaneEventKind } from "./battle-types";

const T_MAX = 30;

/** Mockup timeline units (0–30) → lane track percent (0–100). */
export function mockupT(t: number) {
	return +((t / T_MAX) * 100).toFixed(2);
}

function phaseKind(label: string): LaneEventKind {
	const token = label.toUpperCase();
	if (token.includes("RESEARCH")) return "research";
	if (token.includes("MUTATE")) return "mutate";
	if (token.includes("RETRY") || token.includes("OBSERVE") || token.includes("INHERIT")) return "retry";
	if (token.includes("PAYLOAD") || token.includes("SEND") || token.includes("TRIGGER")) return "payload";
	return "research";
}

function iconKind(icon?: string, label?: string): LaneEventKind {
	if (icon === "rocket") return label?.toUpperCase().includes("PROMOT") ? "promoted" : "fastest_crash";
	if (icon === "skull") return "killed";
	if (icon === "shield" || icon === "shieldx") return "blocked";
	return "useful";
}

type MockPhase = { t: number; label: string };
type MockIcon = { t: number; icon?: string; label?: string; layer?: string };

type MockExploit = {
	hasReplay?: boolean;
	id: string;
	name: string;
	gen: number;
	parent?: string | null;
	start: number;
	end: number;
	line: "red" | "green" | "purple";
	status: string;
	expanded?: boolean;
	selected?: boolean;
	topPhases?: MockPhase[];
	bottomPhases?: MockPhase[];
	events?: MockIcon[];
	spawnT?: number;
	children?: string[];
	context?: string;
};

function phasesToEvents(phases: MockPhase[] | undefined, id: string, band: "top" | "bottom"): LaneEvent[] {
	return (phases ?? []).map((phase, index) => ({
		id: `${id}:${band}:${index}`,
		kind:
			band === "top"
				? phaseKind(phase.label)
				: phase.label.toUpperCase().includes("BLOCK") ||
						phase.label.toUpperCase().includes("PATCH") ||
						phase.label.toUpperCase().includes("GATE")
					? "blocked"
					: phase.label.toUpperCase().includes("PROMOT") || phase.label.toUpperCase().includes("CRASH")
						? "fastest_crash"
						: phase.label.toUpperCase().includes("SPAWN")
							? "handoff"
							: "killed",
		x: mockupT(phase.t),
		label: phase.label,
	}));
}

function iconsToEvents(events: MockIcon[] | undefined, id: string): LaneEvent[] {
	return (events ?? [])
		.filter((event) => event.layer === "icon" || event.icon)
		.map((event, index) => ({
			id: `${id}:icon:${index}`,
			kind: iconKind(event.icon, event.label),
			x: mockupT(event.t),
			label: event.label,
		}));
}

function aboveToEvents(events: MockIcon[] | undefined, id: string): LaneEvent[] {
	return (events ?? [])
		.filter((event) => event.layer === "above")
		.map((event, index) => ({
			id: `${id}:above:${index}`,
			kind: event.label?.toUpperCase().includes("SPAWN") ? "handoff" : "useful",
			x: mockupT(event.t),
			label: event.label,
		}));
}

function terminalFor(status: string): Lane["terminal"] {
	if (status === "fastest_crash") return "fastest_crash";
	if (status === "promoted") return "promoted";
	if (status === "blocked") return "blocked";
	if (status.includes("killed")) return "killed";
	return "none";
}

function laneFromMock(spec: MockExploit): Lane {
	const events = [
		...phasesToEvents(spec.topPhases, spec.id, "top"),
		...phasesToEvents(spec.bottomPhases, spec.id, "bottom"),
		...aboveToEvents(spec.events, spec.id),
		...iconsToEvents(spec.events, spec.id),
	];
	if (spec.children?.length) {
		const spawnT = spec.spawnT ?? spec.end;
		events.push({ id: `${spec.id}:spawn`, kind: "handoff", x: mockupT(spawnT), label: "SPAWN" });
	}
	events.sort((a, b) => a.x - b.x);
	return {
		id: spec.id,
		name: spec.name,
		payloadId: spec.id,
		generation: spec.gen,
		team: "red",
		parentId: spec.parent ?? undefined,
		expanded: spec.expanded,
		children: spec.children,
		xStart: mockupT(spec.start),
		xEnd: mockupT(spec.end),
		runnerX: mockupT(spec.end),
		runnerState: spec.status,
		runnerVerb: spec.status.replace(/_/g, " "),
		lineColor: spec.line,
		terminal: terminalFor(spec.status),
		inheritedContext: spec.context ? [spec.context] : undefined,
		events,
		proofMode: "receipt_backed_fixture",
	};
}

const MOCK_SPECS: MockExploit[] = [
	{
		id: "payload-857",
		hasReplay: true,
		name: "Archive Escape",
		gen: 1,
		start: 2,
		end: 20.4,
		line: "red",
		status: "useful_killed",
		children: ["payload-857-A"],
		spawnT: 20.4,
		context: "ZIP_SLIP_CONFIRMED",
		topPhases: [
			{ t: 3, label: "RESEARCH" },
			{ t: 8, label: "PAYLOAD" },
			{ t: 12, label: "TRIGGER" },
		],
		bottomPhases: [{ t: 20.4, label: "KILLED" }],
		events: [
			{ t: 10.8, layer: "above", label: "USEFUL" },
			{ t: 20.4, layer: "icon", icon: "shield" },
		],
	},
	{
		id: "payload-857-A",
		hasReplay: true,
		name: "Replay Fork",
		gen: 2,
		parent: "payload-857",
		start: 21,
		end: 23.1,
		line: "green",
		status: "fastest_crash",
		selected: true,
		context: "ZIP_SLIP_CONFIRMED",
		topPhases: [
			{ t: 21.2, label: "MUTATE" },
			{ t: 22.0, label: "INHERIT" },
			{ t: 22.8, label: "SEND" },
		],
		bottomPhases: [{ t: 24.5, label: "FASTEST CRASH" }],
		events: [{ t: 23.1, layer: "icon", icon: "rocket" }],
	},
	{
		id: "payload-231",
		name: "Tar Tunnel",
		gen: 1,
		start: 1,
		end: 5.8,
		line: "red",
		status: "killed",
		topPhases: [
			{ t: 1.5, label: "RESEARCH" },
			{ t: 3, label: "PAYLOAD" },
		],
		bottomPhases: [{ t: 5.8, label: "KILLED" }],
		events: [{ t: 5.8, layer: "icon", icon: "skull" }],
	},
	{
		id: "payload-404",
		name: "DotDot Drip",
		gen: 1,
		start: 3,
		end: 14.8,
		line: "red",
		status: "killed",
		topPhases: [
			{ t: 4, label: "RESEARCH" },
			{ t: 8, label: "PAYLOAD" },
			{ t: 11, label: "TRIGGER" },
		],
		bottomPhases: [{ t: 15.5, label: "KILLED" }],
		events: [
			{ t: 13, layer: "icon", icon: "shieldx" },
			{ t: 14.8, layer: "icon", icon: "skull" },
		],
	},
	{
		id: "payload-118",
		name: "Symlink Shuffle",
		gen: 1,
		start: 5,
		end: 21.2,
		line: "red",
		status: "killed",
		topPhases: [
			{ t: 6, label: "RESEARCH" },
			{ t: 12, label: "PAYLOAD" },
			{ t: 16, label: "OBSERVE" },
		],
		bottomPhases: [{ t: 21.2, label: "KILLED" }],
		events: [
			{ t: 18.9, layer: "icon", icon: "shieldx" },
			{ t: 21.2, layer: "icon", icon: "skull" },
		],
	},
	{
		id: "payload-620",
		name: "Boundary Nudge",
		gen: 1,
		start: 6,
		end: 27,
		line: "red",
		status: "killed",
		topPhases: [
			{ t: 8, label: "RESEARCH" },
			{ t: 14, label: "PAYLOAD" },
			{ t: 20, label: "RETRY" },
		],
		bottomPhases: [{ t: 27, label: "KILLED" }],
		events: [
			{ t: 24.6, layer: "icon", icon: "shield" },
			{ t: 27, layer: "icon", icon: "skull" },
		],
	},
	{
		id: "payload-912",
		name: "Boundary Fray",
		gen: 1,
		start: 2,
		end: 18.7,
		line: "red",
		status: "useful_killed",
		expanded: true,
		spawnT: 19.8,
		children: ["payload-912-A", "payload-912-B", "payload-912-C", "payload-912-D"],
		context: "BOUNDARY_LEAK",
		topPhases: [
			{ t: 4, label: "RESEARCH" },
			{ t: 9, label: "PAYLOAD" },
			{ t: 14, label: "TRIGGER" },
		],
		bottomPhases: [{ t: 18.7, label: "KILLED" }],
		events: [
			{ t: 11.4, layer: "above", label: "LEAK" },
			{ t: 18.7, layer: "icon", icon: "skull" },
			{ t: 19.8, layer: "above", label: "SPAWN" },
		],
	},
	{
		id: "payload-912-A",
		name: "Boundary Fray A",
		gen: 2,
		parent: "payload-912",
		start: 19,
		end: 20.6,
		line: "purple",
		status: "killed",
		context: "BOUNDARY_LEAK",
		topPhases: [
			{ t: 19.2, label: "MUTATE" },
			{ t: 20.4, label: "RETRY" },
		],
		bottomPhases: [{ t: 20.6, label: "KILLED" }],
		events: [{ t: 20.6, layer: "icon", icon: "skull" }],
	},
	{
		id: "payload-912-B",
		name: "Boundary Fray B",
		gen: 2,
		parent: "payload-912",
		start: 19,
		end: 19.5,
		line: "purple",
		status: "blocked",
		context: "BOUNDARY_LEAK",
		topPhases: [
			{ t: 19.2, label: "MUTATE" },
			{ t: 20.5, label: "TRIGGER" },
		],
		bottomPhases: [{ t: 19.5, label: "BLUE BLOCK" }],
		events: [{ t: 19.5, layer: "icon", icon: "shieldx" }],
	},
	{
		id: "payload-912-C",
		name: "Boundary Fray C",
		gen: 2,
		parent: "payload-912",
		start: 19,
		end: 24.1,
		line: "purple",
		status: "killed",
		context: "BOUNDARY_LEAK",
		topPhases: [
			{ t: 19.5, label: "MUTATE" },
			{ t: 21.2, label: "RETRY" },
		],
		bottomPhases: [{ t: 24.1, label: "KILLED" }],
		events: [{ t: 24.1, layer: "icon", icon: "skull" }],
	},
	{
		id: "payload-912-D",
		hasReplay: true,
		name: "Boundary Fray D",
		gen: 2,
		parent: "payload-912",
		start: 19,
		end: 28.4,
		line: "purple",
		status: "promoted",
		context: "BOUNDARY_LEAK",
		topPhases: [
			{ t: 19.5, label: "MUTATE" },
			{ t: 22.2, label: "RETRY" },
			{ t: 25.5, label: "OBSERVE" },
		],
		bottomPhases: [{ t: 28.4, label: "PROMOTED" }],
		events: [{ t: 28.4, layer: "icon", icon: "rocket" }],
	},
];

export const mockupDesignLanes: Lane[] = MOCK_SPECS.map(laneFromMock);

import { isBattleReceiptReplayView } from "./battle-receipt-replay";

export function isBattleDesignView() {
	if (typeof window === "undefined") return false;
	if (isBattleReceiptReplayView()) return false;
	const path = window.location.hash.split("?")[0];
	return path === "#battle" || path === "#battle/isolation";
}

export { isBattleReceiptReplayView } from "./battle-receipt-replay";

export { mockupDefaultSelectedLaneId } from "./mockup-design-fixture";
