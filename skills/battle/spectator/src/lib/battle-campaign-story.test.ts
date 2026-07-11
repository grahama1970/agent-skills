import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { BattleNormalizedUxFixture } from "./battle-types";
import {
	buildCampaignStory,
	campaignChapterAtPlayhead,
	soundCueForGeneticEventType,
} from "./battle-campaign-story";
import { isBattleCampaignView } from "./battle-campaign-registry";
import { battleReceiptReplayFixtureKey } from "./battle-receipt-replay";

const fixturePath = resolve(
	import.meta.dirname,
	"../../public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json",
);

function loadFixture(): BattleNormalizedUxFixture {
	return JSON.parse(readFileSync(fixturePath, "utf8")) as BattleNormalizedUxFixture;
}

describe("UX9 campaign storytelling", () => {
	it("routes #battle/campaign to genetic fixture by default", () => {
		const hash = "#battle/campaign?engine=pixi";
		expect(isBattleCampaignView(hash)).toBe(true);
		expect(battleReceiptReplayFixtureKey(hash)).toBe("battle-004-pr6-genetic-pixi");
	});

	it("builds ordered receipt-backed chapters without victory claims", () => {
		const story = buildCampaignStory(loadFixture());
		expect(story).toBeTruthy();
		expect(story!.schema).toBe("battle.campaign_story.v1");
		expect(story!.mocked).toBe(false);
		expect(story!.chapterCount).toBe(12);
		expect(story!.chapters[0]?.eventType).toBe("research_started");
		expect(story!.chapters.every((chapter) => chapter.mayClaimVictory === false)).toBe(true);
		expect(story!.chapters.every((chapter) => chapter.victoryAllowed === false)).toBe(true);
		expect(story!.claimBoundary.mustNotClaim.join(" ")).toMatch(/exploit success|not_runnable|sound_is_not_proof/i);
		expect(soundCueForGeneticEventType("genome_selected")).toBe("mutate_chirp");
		expect(soundCueForGeneticEventType("compile_failed")).toBe("retry_tick");
	});

	it("selects the latest chapter at playhead", () => {
		const story = buildCampaignStory(loadFixture());
		expect(campaignChapterAtPlayhead(story, 85)?.eventType).toBeUndefined();
		expect(campaignChapterAtPlayhead(story, 86)?.eventType).toBe("research_started");
		expect(campaignChapterAtPlayhead(story, 114)?.eventType).toBe("compile_passed");
		expect(campaignChapterAtPlayhead(story, 200)?.eventType).toBe("branch_abandoned");
	});
});
