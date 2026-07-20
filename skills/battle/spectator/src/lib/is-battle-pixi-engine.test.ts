import { describe, expect, it } from "vitest";
import { battleRaceEngineFromHash, isBattlePixiEngine } from "./is-battle-pixi-engine";

describe("battleRaceEngineFromHash", () => {
	it("defaults to pixi on receipt replay routes", () => {
		expect(battleRaceEngineFromHash("#battle/receipt")).toBe("pixi");
		expect(battleRaceEngineFromHash("#battle/receipt?fixture=battle-004-kill-shot")).toBe("pixi");
	});

	it("opts out with engine=dom on receipt routes", () => {
		expect(battleRaceEngineFromHash("#battle/receipt?engine=dom")).toBe("dom");
	});

	it("defaults to pixi on the top-level battle UX route", () => {
		expect(battleRaceEngineFromHash("#battle")).toBe("pixi");
		expect(battleRaceEngineFromHash("#battle?engine=dom")).toBe("dom");
		expect(battleRaceEngineFromHash("#battle?engine=pixi")).toBe("pixi");
	});

	it("isBattlePixiEngine is a thin wrapper", () => {
		expect(typeof isBattlePixiEngine()).toBe("boolean");
	});
});
