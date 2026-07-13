import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { battleLanesForView } from "../lib/battle-data";
import { buildRaceEngineRowLayout } from "../lib/build-race-engine-input";
import { fixtureUsesElapsedAxis } from "../lib/battle-elapsed-axis";
import { createPixiLineageLayer, syncPixiLineage } from "./battle-pixi-lineage";

describe("syncPixiLineage", () => {
	it("draws a branch for parent spawn fixture", async () => {
		const fixture = JSON.parse(
			await readFile(
				resolve(import.meta.dirname, "../../public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json"),
				"utf8",
			),
		);
		const lanes = battleLanesForView(fixture.lanes, fixture);
		const rowLayout = buildRaceEngineRowLayout(lanes);
		const layer = createPixiLineageLayer();
		syncPixiLineage({
			layer,
			lanes,
			rowLayout,
			collapsedParentIds: new Set(),
			allottedSeconds: 1200,
			currentSeconds: 0,
			contentWidth: 1200,
			useElapsed: fixtureUsesElapsedAxis(fixture),
		});
		expect(layer.signature.length).toBeGreaterThan(10);
		expect(layer.graphics.bounds.maxX).toBeGreaterThan(layer.graphics.bounds.minX);
	});
});
