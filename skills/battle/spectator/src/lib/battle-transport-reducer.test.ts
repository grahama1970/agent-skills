import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleLiveEventV1, BattleTransportPackage } from "./battle-transport-types";
import {
	applyTransportEvent,
	bootstrapTransportState,
	createIdleTransportState,
	setTransportCursorSeconds,
	setTransportFollowLive,
	transportViewModel,
} from "./battle-transport-reducer";
import { validateLiveEvent, validateSnapshot, validateTransportManifest, validateTransportStreamSemantics } from "./battle-transport-validator";
import { battleLiveTransportFixtureKey, isBattleLiveView, isRegisteredLiveTransportFixture } from "./battle-transport-registry";

const streamDir = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream",
);

function loadPack(): BattleTransportPackage {
	const manifest = JSON.parse(readFileSync(resolve(streamDir, "manifest.json"), "utf8"));
	const snapshot = JSON.parse(readFileSync(resolve(streamDir, "latest-snapshot.json"), "utf8"));
	const events = readFileSync(resolve(streamDir, "events.jsonl"), "utf8")
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
		.map((line) => JSON.parse(line) as BattleLiveEventV1);
	return {
		manifest,
		snapshot,
		events,
		streamBaseUrl: "/battle-fixtures/battle-004-parent-spawn-pixi-replay/stream",
		companionFixtureUrl: "/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json",
	};
}

describe("UX8 live transport", () => {
	it("registers live route and parent-spawn stream fixture", () => {
		expect(isBattleLiveView("#battle/live?engine=pixi&fixture=battle-004-parent-spawn")).toBe(true);
		expect(isBattleLiveView("#battle/receipt?engine=pixi")).toBe(false);
		expect(battleLiveTransportFixtureKey("#battle/live?fixture=battle-004-parent-spawn")).toBe("battle-004-parent-spawn");
		expect(battleLiveTransportFixtureKey("#battle/live?fixture=not-a-registered-stream")).toBeNull();
		expect(isRegisteredLiveTransportFixture("not-real")).toBe(false);
	});

	it("validates published stream package semantics", () => {
		const pack = loadPack();
		expect(validateTransportManifest(pack.manifest).ok).toBe(true);
		expect(validateSnapshot(pack.snapshot).ok).toBe(true);
		for (const event of pack.events) {
			expect(validateLiveEvent(event).ok).toBe(true);
		}
		const semantics = validateTransportStreamSemantics({
			manifest: pack.manifest,
			snapshot: pack.snapshot,
			events: pack.events,
			companionBattleId: "battle-004",
		});
		expect(semantics.ok).toBe(true);
		expect(pack.manifest.mocked).toBe(false);
		expect(pack.manifest.stream_contract.transport).toBe("append_only_jsonl");
		expect(pack.manifest.mode).toBe("file_backed_replay_stream");
	});

	it("bootstraps applied seq and follow-live cursor from package", () => {
		const pack = loadPack();
		const state = bootstrapTransportState(pack);
		const model = transportViewModel(state);
		expect(state.appliedSeq).toBe(24);
		expect(model?.followLive).toBe(true);
		expect(model?.status).toBe("ended");
		expect(model?.liveSeconds).toBeGreaterThan(90);
		expect(model?.eventCount).toBe(24);
	});

	it("deduplicates events and fails closed on sequence gaps", () => {
		const pack = loadPack();
		let state = createIdleTransportState();
		state = {
			...state,
			pack,
			status: "ready",
			followLive: true,
		};
		state = applyTransportEvent(state, pack.events[0]!);
		expect(state.appliedSeq).toBe(1);
		const dup = applyTransportEvent(state, pack.events[0]!);
		expect(dup.appliedSeq).toBe(1);
		expect(dup.appliedBySeq.size).toBe(1);

		const gap = applyTransportEvent(state, pack.events[2]!);
		expect(gap.status).toBe("gap_recovery");
		expect(gap.gapExpectedSeq).toBe(2);
		expect(gap.error).toMatch(/Sequence gap/i);
	});

	it("supports scrub then return-to-live", () => {
		const pack = loadPack();
		let state = bootstrapTransportState(pack);
		state = setTransportCursorSeconds(state, 10);
		expect(state.followLive).toBe(false);
		expect(state.status).toBe("scrubbing");
		expect(state.cursorSeconds).toBe(10);
		state = setTransportFollowLive(state, true);
		expect(state.followLive).toBe(true);
		expect(state.cursorSeconds).toBe(transportViewModel(state)?.liveSeconds);
	});

	it("rejects companion battle_id mismatch", () => {
		const pack = loadPack();
		const semantics = validateTransportStreamSemantics({
			manifest: pack.manifest,
			snapshot: pack.snapshot,
			events: pack.events,
			companionBattleId: "battle-999",
		});
		expect(semantics.ok).toBe(false);
		if (!semantics.ok) expect(semantics.error.code).toBe("FIXTURE_MISMATCH");
	});
});
