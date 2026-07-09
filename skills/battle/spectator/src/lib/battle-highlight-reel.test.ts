import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { battleLanesForView } from "./battle-data";
import { collectHighlightBeats, nextHighlightBeat } from "./battle-highlight-reel";

describe("battle-highlight-reel", () => {
	it("collects proven terminal beats from kill-shot fixture", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const beats = collectHighlightBeats(fixture, lanes);
		expect(beats.length).toBeGreaterThan(2);
		expect(beats.some((beat) => beat.kind === "spawn")).toBe(true);
	});

	it("finds the next beat after the playhead", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const next = nextHighlightBeat(fixture, lanes, 0);
		expect(next?.kind).toBe("spawn");
	});
});
