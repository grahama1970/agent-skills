import { describe, expect, it } from "vitest";
import { receiptBackedFixture } from "./battle-data";
import { battleTimelineDomain } from "./battle-timeline-domain";

describe("battleTimelineDomain", () => {
	it("uses battle_timeline_control in receipt mode", () => {
		const domain = battleTimelineDomain(receiptBackedFixture, false);
		expect(domain.source).toBe("timeline_control");
		expect(domain.allottedSeconds).toBe(1200);
		expect(domain.currentSeconds).toBeGreaterThan(0);
	});
});
