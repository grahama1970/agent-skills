import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { buildCampaignStory } from "./battle-campaign-story";
import { buildBattleRoundIntro } from "./battle-round-intro";
import { BATTLE_LEGACY_GENESIS_INTRO_MIDI, BATTLE_SCORE_CUES } from "./battle-music-catalog";
import { parseMidiBytes } from "./battle-genesis-midi";

const fixturePath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
);
const legacyMidiPath = resolve(import.meta.dirname, "../../public/battle-audio/legacy/battle-004-round-intro.mid");

describe("Death Clock round intro", () => {
	it("builds production intro on Death Clock OGG and marks Genesis MIDI legacy-only", () => {
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
		const story = buildCampaignStory(fixture);
		const intro = buildBattleRoundIntro(fixture, story);
		expect(intro.schema).toBe("battle.death_clock_round_intro.v1");
		expect(intro.graphicStyle).toBe("death_clock_round_intro");
		expect(intro.audioUrl).toBe(BATTLE_SCORE_CUES.death_clock_overture.ogg);
		expect(intro.provisionalGmRender).toBe(true);
		expect(intro.legacyIntroSelectable).toBe(false);
		expect(intro.legacyGenesisMidiUrl).toBe(BATTLE_LEGACY_GENESIS_INTRO_MIDI);
		expect(intro.claimBoundary.mustNotClaim).toEqual(
			expect.arrayContaining(["legacy_genesis_midi_is_production_intro", "gm_render_is_final_mix"]),
		);
	});

	it("keeps legacy Genesis MIDI as a parseable reference asset only", () => {
		const bytes = readFileSync(legacyMidiPath);
		const song = parseMidiBytes(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, legacyMidiPath);
		expect(song.ticksPerQuarter).toBe(480);
		expect(song.events.some((event) => event.type === "on")).toBe(true);
	});
});
