import type { BattleNormalizedUxFixture } from "./battle-types";
import type { CampaignStoryViewModel } from "./battle-campaign-story";

export type GenesisIntroPage = {
	id: string;
	kind: "logo" | "crawl" | "round" | "ready";
	eyebrow: string;
	lines: string[];
	footer?: string;
};

export type GenesisIntroViewModel = {
	schema: "battle.genesis_round_intro.v1";
	battleId: string;
	fixtureId: string;
	roundLabel: string;
	scenarioTitle: string;
	midiUrl: string;
	pages: GenesisIntroPage[];
	graphicStyle: "sega_genesis_round_intro";
	researchRefs: string[];
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
	};
};

/**
 * @deprecated Legacy / reference only — production intro is buildBattleRoundIntro (Death Clock).
 * Build a Streets-of-Rage-inspired intro sequence (logo → premise crawl → ROUND → PRESS START)
 * with Battle receipt-backed scenario text. Original prose — not a SoR transcript.
 */
export function buildGenesisRoundIntro(
	fixture: BattleNormalizedUxFixture,
	story?: CampaignStoryViewModel | null,
): GenesisIntroViewModel {
	const scenario = fixture.scenario;
	const title = scenario?.title ?? "Battle Arena";
	const entry = scenario?.public_entrypoint ?? "/api";
	const cwe = scenario?.cwe ?? "CWE-UNKNOWN";
	const family = scenario?.hidden_vulnerability_family ?? "unknown vulnerability";
	const battleId = fixture.battle_id;
	const chapterHint = story?.chapterCount
		? `${story.chapterCount} genetic chapters await after the gate.`
		: "Receipt-backed genetic chapters await after the gate.";

	const pages: GenesisIntroPage[] = [
		{
			id: "logo",
			kind: "logo",
			eyebrow: "16-BIT SPECTATOR",
			lines: ["BATTLE", "ARENA"],
			footer: "ORIGINAL INTRO · NOT A SEGA DUMP",
		},
		{
			id: "crawl",
			kind: "crawl",
			eyebrow: "PREMISE",
			lines: [
				`IN THE NET OF ${battleId.toUpperCase()}…`,
				`A CORRUPT ARCHIVE GATE OPENS AT ${entry}.`,
				`FAMILY: ${family.toUpperCase()} (${cwe}).`,
				"RED AGENTS MUTATE EXPLOIT GENOMES.",
				"BLUE PATCHES HOLD THE LINE.",
				"ONLY JUDGE RECEIPTS PROVE A KILL.",
				chapterHint.toUpperCase(),
			],
			footer: "START SKIP",
		},
		{
			id: "round",
			kind: "round",
			eyebrow: title.toUpperCase(),
			lines: ["ROUND 1", "FIGHT FOR THE RECEIPT"],
			footer: "GENESIS-STYLE ROUND GATE",
		},
		{
			id: "ready",
			kind: "ready",
			eyebrow: "PLAYER 1",
			lines: ["PRESS START", "ENTER THE ARENA"],
			footer: "MIDI INTRO ARMED ON START",
		},
	];

	return {
		schema: "battle.genesis_round_intro.v1",
		battleId,
		fixtureId: story?.fixtureId ?? "battle-004-pr6-genetic-pixi",
		roundLabel: "ROUND 1",
		scenarioTitle: title,
		midiUrl: "/battle-audio/legacy/battle-004-round-intro.mid",
		pages,
		graphicStyle: "sega_genesis_round_intro",
		researchRefs: [
			"Streets of Rage Genesis intro flow (logo → premise → title)",
			"VGMusic / Project2612 listening references (not redistributed)",
			"CC0 Mega Drive packs: Safety Stoat free_vgms",
		],
		claimBoundary: {
			mayClaim: [
				"genesis_style_round_intro_presented",
				"original_midi_intro_playable",
				"scenario_premise_from_normalized_fixture",
			],
			mustNotClaim: [
				"sega_licensed_assets",
				"commercial_vgm_redistribution",
				"intro_music_proves_exploit_success",
			],
		},
	};
}
