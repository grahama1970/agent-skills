import type { BattleNormalizedUxFixture } from "./battle-types";
import type { CampaignStoryViewModel } from "./battle-campaign-story";
import { BATTLE_LEGACY_GENESIS_INTRO_MIDI, BATTLE_SCORE_CUES } from "./battle-music-catalog";

export type BattleRoundIntroPage = {
	id: string;
	kind: "logo" | "crawl" | "round" | "ready";
	eyebrow: string;
	lines: string[];
	footer?: string;
};

export type BattleRoundIntroViewModel = {
	schema: "battle.death_clock_round_intro.v1";
	battleId: string;
	fixtureId: string;
	roundLabel: string;
	scenarioTitle: string;
	/** Production intro audio — provisional GM OGG. */
	audioUrl: string;
	audioCueId: "death_clock_overture";
	provisionalGmRender: true;
	/** Legacy Genesis MIDI path — reference only; not selectable in production UI. */
	legacyGenesisMidiUrl: string;
	legacyIntroSelectable: false;
	pages: BattleRoundIntroPage[];
	graphicStyle: "death_clock_round_intro";
	researchRefs: string[];
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
	};
};

/**
 * Round intro gate: logo → premise crawl → ROUND → PRESS START.
 * Production music is Death Clock Overture (OGG). Genesis MIDI is legacy only.
 */
export function buildBattleRoundIntro(
	fixture: BattleNormalizedUxFixture,
	story?: CampaignStoryViewModel | null,
): BattleRoundIntroViewModel {
	const scenario = fixture.scenario;
	const title = scenario?.title ?? "Battle Arena";
	const entry = scenario?.public_entrypoint ?? "/api";
	const cwe = scenario?.cwe ?? "CWE-UNKNOWN";
	const family = scenario?.hidden_vulnerability_family ?? "unknown vulnerability";
	const battleId = fixture.battle_id;
	const chapterHint = story?.chapterCount
		? `${story.chapterCount} genetic chapters await after the gate.`
		: "Receipt-backed genetic chapters await after the gate.";

	const pages: BattleRoundIntroPage[] = [
		{
			id: "logo",
			kind: "logo",
			eyebrow: "DEATH CLOCK",
			lines: ["BATTLE", "ARENA"],
			footer: "ORIGINAL SCORE · PROVISIONAL GM RENDER",
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
			footer: "DEATH CLOCK ROUND GATE",
		},
		{
			id: "ready",
			kind: "ready",
			eyebrow: "PLAYER 1",
			lines: ["PRESS START", "ENTER THE ARENA"],
			footer: "OVERTURE ARMED ON PLAY",
		},
	];

	return {
		schema: "battle.death_clock_round_intro.v1",
		battleId,
		fixtureId: story?.fixtureId ?? "battle-004-pr6-genetic-pixi",
		roundLabel: "ROUND 1",
		scenarioTitle: title,
		audioUrl: BATTLE_SCORE_CUES.death_clock_overture.ogg,
		audioCueId: "death_clock_overture",
		provisionalGmRender: true,
		legacyGenesisMidiUrl: BATTLE_LEGACY_GENESIS_INTRO_MIDI,
		legacyIntroSelectable: false,
		pages,
		graphicStyle: "death_clock_round_intro",
		researchRefs: [
			"Battle music style guide v1 — Death Clock Overture",
			"Streets of Rage-inspired intro flow (logo → premise → title) as UX pacing only",
			"GM / TimGM6mb provisional render — not final synth mix",
		],
		claimBoundary: {
			mayClaim: [
				"death_clock_round_intro_presented",
				"provisional_gm_overture_playable",
				"scenario_premise_from_normalized_fixture",
			],
			mustNotClaim: [
				"sega_licensed_assets",
				"commercial_vgm_redistribution",
				"intro_music_proves_exploit_success",
				"gm_render_is_final_mix",
				"legacy_genesis_midi_is_production_intro",
			],
		},
	};
}
