import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { collectReceiptBeats } from "./battle-receipt-beats";
import { battleReceiptReplayFixtureKey, battleReceiptReplayFixtureUrl } from "./battle-receipt-replay";
import {
	GENETIC_NO_VICTORY_EVENT_TYPES,
	geneticEventsFromFixture,
	geneticLifecycleViewModel,
	geneticPixiEffectForEvent,
	geneticVictoryAllowed,
	hasGeneticLifecycle,
	lanesWithGeneticLifecycleEvents,
} from "./battle-genetic-lifecycle";
import { battleLanesForView } from "./battle-data";

const fixturePath = resolve(
	import.meta.dirname,
	"../../../local/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
);

function loadFixture(): BattleNormalizedUxFixture {
	return JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
}

describe("UX7 genetic Pixi lifecycle", () => {
	it("registers the PR6 genetic fixture on the receipt route", () => {
		const hash = "#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi";
		expect(battleReceiptReplayFixtureKey(hash)).toBe("battle-004-pr6-genetic-pixi");
		expect(battleReceiptReplayFixtureUrl(hash)).toBe(
			"/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
		);
	});

	it("reads genetic_lifecycle present and not-emitted vocabulary", () => {
		const fixture = loadFixture();
		expect(hasGeneticLifecycle(fixture)).toBe(true);
		const model = geneticLifecycleViewModel(fixture);
		expect(model?.present).toEqual(
			expect.arrayContaining([
				"research_started",
				"genome_selected",
				"compile_failed",
				"compile_passed",
				"target_contact_unproven",
				"judge_pending",
				"branch_abandoned",
			]),
		);
		expect(model?.notEmitted).toEqual(
			expect.arrayContaining([
				"repair_started",
				"repair_materialized",
				"judge_exploit_success",
				"genome_promoted",
			]),
		);
		expect(model?.victoryRequiresJudge).toBe(true);
		expect(model?.compilePassedNotRunnable).toBe(true);
		expect(model?.targetContactNotExploit).toBe(true);
	});

	it("maps genetic events to pixi effects without victory", () => {
		const fixture = loadFixture();
		const genetic = geneticEventsFromFixture(fixture);
		expect(genetic.length).toBe(12);
		for (const event of genetic) {
			const effect = geneticPixiEffectForEvent(event);
			expect(effect).toBeTruthy();
			expect(geneticVictoryAllowed(event)).toBe(false);
			expect(GENETIC_NO_VICTORY_EVENT_TYPES.has(event.event_type as never)).toBe(true);
		}
	});

	it("injects genetic markers onto lanes and emits receipt beats", () => {
		const fixture = loadFixture();
		const lanes = battleLanesForView(undefined, fixture);
		const child = lanes.find((lane) => lane.id === "payload-857-red-1");
		expect(child).toBeTruthy();
		const geneticKinds = child!.events.filter((event) => Boolean(event.geneticEffect));
		expect(geneticKinds.length).toBeGreaterThanOrEqual(8);
		expect(geneticKinds.every((event) => event.proven && event.geneticEffect)).toBe(true);
		expect(geneticKinds.every((event) => event.victoryAllowed !== true)).toBe(true);

		const beats = collectReceiptBeats(fixture, lanesWithGeneticLifecycleEvents(lanes, fixture));
		const geneticBeats = beats.filter((beat) =>
			[
				"research_started",
				"genome_selected",
				"compile_failed",
				"compile_passed",
				"target_contact_unproven",
				"judge_pending",
				"branch_abandoned",
			].includes(beat.kind),
		);
		expect(geneticBeats.length).toBeGreaterThanOrEqual(7);
		expect(geneticBeats.every((beat) => beat.react.deathCard === false)).toBe(true);
		expect(geneticBeats.every((beat) => beat.kind !== "killed" && beat.kind !== "promoted")).toBe(true);
		expect(geneticBeats.some((beat) => beat.pixi.emphasis === "research_scan")).toBe(true);
		expect(geneticBeats.some((beat) => beat.pixi.emphasis === "compile_error")).toBe(true);
		expect(geneticBeats.some((beat) => beat.pixi.emphasis === "compile_lock")).toBe(true);
		expect(geneticBeats.some((beat) => beat.pixi.emphasis === "endpoint_pulse")).toBe(true);
	});

	it("does not invent NOT_EMITTED genetic events as beats", () => {
		const fixture = loadFixture();
		const lanes = battleLanesForView(undefined, fixture);
		const beats = collectReceiptBeats(fixture, lanes);
		expect(beats.some((beat) => beat.kind === "judge_exploit_success")).toBe(false);
		expect(beats.some((beat) => beat.kind === "genome_promoted")).toBe(false);
		expect(beats.some((beat) => beat.kind === "repair_started")).toBe(false);
		expect(lanes.some((lane) => lane.events.some((event) => event.kind === "judge_exploit_success"))).toBe(false);
	});
});
