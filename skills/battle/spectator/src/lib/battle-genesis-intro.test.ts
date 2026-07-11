import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import { buildCampaignStory } from "./battle-campaign-story";
import { buildGenesisRoundIntro } from "./battle-genesis-intro";
import { parseMidiBytes } from "./battle-genesis-midi";

const fixturePath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
);
const midiPath = resolve(import.meta.dirname, "../../public/battle-audio/battle-004-round-intro.mid");

describe("UX9 Genesis round intro", () => {
	it("builds SoR-inspired pages from normalized scenario without Sega claims", () => {
		const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
		const story = buildCampaignStory(fixture);
		const intro = buildGenesisRoundIntro(fixture, story);
		expect(intro.schema).toBe("battle.genesis_round_intro.v1");
		expect(intro.pages.map((page) => page.kind)).toEqual(["logo", "crawl", "round", "ready"]);
		expect(intro.pages[1]?.lines.join(" ")).toMatch(/ARCHIVE GATE|CWE-22|ZIP SLIP/i);
		expect(intro.roundLabel).toBe("ROUND 1");
		expect(intro.midiUrl).toBe("/battle-audio/battle-004-round-intro.mid");
		expect(intro.claimBoundary.mustNotClaim).toEqual(
			expect.arrayContaining(["sega_licensed_assets", "commercial_vgm_redistribution"]),
		);
	});

	it("parses the bundled original round-intro MIDI", () => {
		const bytes = readFileSync(midiPath);
		const song = parseMidiBytes(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), midiPath);
		expect(song.ticksPerQuarter).toBe(480);
		expect(song.tempoBpm).toBe(148);
		expect(song.events.some((event) => event.type === "on")).toBe(true);
		expect(song.durationTicks).toBeGreaterThan(1000);
	});
});
