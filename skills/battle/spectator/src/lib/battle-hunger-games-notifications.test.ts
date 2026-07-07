import { describe, expect, it } from "vitest";
import { hungerGamesNotification } from "./battle-hunger-games-notifications";
import type { Lane } from "./battle-types";

const lane: Lane = {
	id: "payload-857-receipt",
	name: "Red-0",
	payloadId: "payload-857-receipt",
	generation: 1,
	team: "red",
	xStart: 0,
	xEnd: 100,
	runnerX: 50,
	runnerState: "advance",
	lineColor: "red",
	terminal: "killed",
	events: [],
};

describe("hungerGamesNotification", () => {
	it("formats elimination like arena cannon announcements", () => {
		const ticker = hungerGamesNotification("killed", lane);
		expect(ticker.prefix).toBe("BOOM — ");
		expect(ticker.highlight).toBe("RED-0 ELIMINATED");
		expect(ticker.highlightTone).toBe("red");
	});

	it("formats survival after a block", () => {
		const ticker = hungerGamesNotification("blocked", lane);
		expect(ticker.highlight).toBe("RED-0 SURVIVES");
	});
});
