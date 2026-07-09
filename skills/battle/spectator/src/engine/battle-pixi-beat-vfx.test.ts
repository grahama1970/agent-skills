import { describe, expect, it } from "vitest";
import { createBeatVfxLayer, syncBeatEmphasisVfx, SPAWN_PULSE_SECONDS } from "./battle-pixi-beat-vfx";
import type { ReceiptBeat } from "../lib/battle-receipt-beats";
import type { Lane } from "../lib/battle-types";

function beat(overrides: Partial<ReceiptBeat> & Pick<ReceiptBeat, "kind" | "atSeconds" | "laneId">): ReceiptBeat {
	return {
		id: "lane:spawn:1",
		importance: "hero",
		proofStatus: "receipt_backed",
		branchIds: [overrides.laneId],
		eventId: "evt",
		receiptId: "rcpt",
		camera: { focusSeconds: overrides.atSeconds, preRollMs: 300, postRollMs: 1000, follow: true },
		react: {
			liveEvent: { prefix: "", highlight: "", highlightTone: "red", notification: "spawn" },
			deathCard: false,
			soundCue: "spawn_rise",
		},
		pixi: { emphasis: overrides.kind === "spawn" ? "spawn" : "block_impact" },
		...overrides,
	} as ReceiptBeat;
}

const lane: Lane = {
	id: "payload-857-red-1",
	name: "red-1",
	payloadId: "payload-857-red-1",
	generation: 2,
	team: "red",
	xStart: 0,
	xEnd: 100,
	runnerX: 50,
	runnerState: "spawn",
	lineColor: "red",
	terminal: "none",
	events: [],
};

describe("syncBeatEmphasisVfx", () => {
	it("renders spawn pulse during spawn emphasis window", () => {
		const layer = createBeatVfxLayer();
		const result = syncBeatEmphasisVfx({
			layer,
			markerAtlas: {},
			lanes: [lane],
			rowLayout: [{ laneId: lane.id, topPx: 0, heightPx: 40, isChild: true }],
			activeBeat: beat({ kind: "spawn", atSeconds: 10, laneId: lane.id }),
			currentSeconds: 10 + SPAWN_PULSE_SECONDS * 0.4,
			allottedSeconds: 120,
			contentWidth: 1200,
		});
		expect(result.vfx).toBe("spawn_pulse");
		expect(layer.activeKey).toContain("spawn");
	});

	it("clears vfx outside emphasis window", () => {
		const layer = createBeatVfxLayer();
		const result = syncBeatEmphasisVfx({
			layer,
			markerAtlas: {},
			lanes: [lane],
			rowLayout: [{ laneId: lane.id, topPx: 0, heightPx: 40, isChild: true }],
			activeBeat: beat({ kind: "spawn", atSeconds: 10, laneId: lane.id }),
			currentSeconds: 10 + SPAWN_PULSE_SECONDS + 0.2,
			allottedSeconds: 120,
			contentWidth: 1200,
		});
		expect(result.vfx).toBe("none");
	});
});
