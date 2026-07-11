import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
	buildMusicScheduleViewModel,
	promotedEntriesDueAtPlayhead,
	validateNormalizedMusicFixture,
	type BattleNormalizedMusicFixture,
} from "./battle-normalized-music-fixture";
import { isBattleMusicView, battleMusicFixtureUrl } from "./battle-music-registry";

const fixturePath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json",
);

describe("battle normalized music fixture M1", () => {
	it("registers the music route and public fixture URL", () => {
		expect(isBattleMusicView("#battle/music?fixture=battle-004-music-runtime")).toBe(true);
		expect(battleMusicFixtureUrl("#battle/music?fixture=battle-004-music-runtime")).toContain(
			"battle-004-music-runtime/battle.normalized_music_fixture.json",
		);
	});

	it("fail-closes invalid fixtures and accepts the published M1 fixture", () => {
		expect(validateNormalizedMusicFixture({ schema: "nope" })?.code).toBe("invalid_schema");
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedMusicFixture;
		expect(validateNormalizedMusicFixture(fixture)).toBeNull();
		const model = buildMusicScheduleViewModel(fixture);
		expect(model.mocked).toBe(false);
		expect(model.composerLive).toBe(false);
		expect(model.promotedEntries).toHaveLength(2);
		expect(model.promotedEntries.map((entry) => entry.musicId)).toEqual([
			"live_arena_loop",
			"motif:plague_nurgling",
		]);
		expect(model.eventsNotEmitted).toEqual(
			expect.arrayContaining(["exploit_death_stinger", "exploit_victory_stinger", "next_battle_arena"]),
		);
		expect(model.promotedEntries.every((entry) => entry.oggUrl.startsWith("/battle-audio/promoted/v1/"))).toBe(true);
		const dueEarly = promotedEntriesDueAtPlayhead(model, 1, new Set());
		expect(dueEarly.map((entry) => entry.musicId)).toEqual(["live_arena_loop"]);
		const dueLate = promotedEntriesDueAtPlayhead(model, 100, new Set());
		expect(dueLate.map((entry) => entry.musicId)).toEqual(["live_arena_loop", "motif:plague_nurgling"]);
	});
});
