import type { BattleNormalizedUxFixture, SoundCue } from "./battle-types";
import {
	geneticEventsFromFixture,
	geneticLifecycleOf,
	geneticPixiEffectForEvent,
	geneticVictoryAllowed,
	isGeneticEventType,
	type GeneticEventType,
	type GeneticPixiEffect,
} from "./battle-genetic-lifecycle";

export type CampaignStoryChapter = {
	id: string;
	seq: number;
	eventType: GeneticEventType;
	atSeconds: number;
	laneId: string | null;
	title: string;
	caption: string;
	soundCue: SoundCue;
	soundCaption: string;
	pixiEffect: GeneticPixiEffect | null;
	receiptId: string | null;
	victoryAllowed: boolean;
	mayClaimVictory: false;
};

export type CampaignStoryViewModel = {
	schema: "battle.campaign_story.v1";
	battleId: string;
	fixtureId: string;
	route: string;
	mocked: false;
	live: "receipt_replay_campaign";
	chapterCount: number;
	chapters: CampaignStoryChapter[];
	pulse: {
		activeLineages: number;
		geneticPresent: number;
		geneticNotEmitted: number;
		spawns: number;
		compilePassedChapters: number;
		targetContactChapters: number;
		abandonedBranches: number;
	};
	claimBoundary: {
		mayClaim: string[];
		mustNotClaim: string[];
	};
};

const CHAPTER_TITLE: Record<GeneticEventType, string> = {
	research_started: "Research opens",
	research_receipt_materialized: "Research receipt lands",
	genome_selected: "Genome locks",
	method_added: "Method joins genome",
	method_rejected: "Method rejected",
	code_author_started: "Code authoring starts",
	specimen_materialized: "Specimen materialized",
	compile_failed: "Compile fails",
	repair_started: "Repair starts",
	repair_materialized: "Repair materialized",
	compile_passed: "Compile passes",
	target_contact_unproven: "Target contact unproven",
	judge_pending: "Judge pending",
	judge_exploit_success: "Judge exploit success",
	genome_promoted: "Genome promoted",
	branch_abandoned: "Branch abandoned",
};

const CHAPTER_CAPTION: Record<GeneticEventType, string> = {
	research_started: "A research node begins shaping the attempt.",
	research_receipt_materialized: "Research evidence is receipt-backed into the campaign.",
	genome_selected: "Selected methods lock into an exploit genome candidate.",
	method_added: "A method shard joins the genome.",
	method_rejected: "A method is rejected and fades from the genome.",
	code_author_started: "Provider code authoring begins for a specimen.",
	specimen_materialized: "Generated specimen code exists as an artifact, not a win.",
	compile_failed: "Compiler evidence fails; retained as negative pressure.",
	repair_started: "Repair authoring starts after compile failure.",
	repair_materialized: "Repair artifact materialized; still not runtime proof.",
	compile_passed: "Compile passed — syntax/build only, not runnable proof.",
	target_contact_unproven: "Target contact observed without exploit success.",
	judge_pending: "Judge has not verified exploit success yet.",
	judge_exploit_success: "Judge verified exploit success.",
	genome_promoted: "Genome promoted after Judge-backed success.",
	branch_abandoned: "Failed branch kept as negative campaign evidence.",
};

export function soundCueForGeneticEventType(eventType: GeneticEventType): SoundCue {
	switch (eventType) {
		case "genome_selected":
		case "method_added":
		case "method_rejected":
			return "mutate_chirp";
		case "compile_failed":
		case "branch_abandoned":
			return "retry_tick";
		case "compile_passed":
		case "specimen_materialized":
		case "research_started":
		case "research_receipt_materialized":
		case "code_author_started":
		case "repair_started":
		case "repair_materialized":
		case "target_contact_unproven":
		case "judge_pending":
			return "scan_ping";
		case "judge_exploit_success":
		case "genome_promoted":
			return "victory_hit";
		default:
			return "scan_ping";
	}
}

export function soundCaptionForCue(cue: SoundCue, eventType?: GeneticEventType): string {
	if (cue === "none") return "";
	if (eventType) return CHAPTER_CAPTION[eventType];
	switch (cue) {
		case "mutate_chirp":
			return "Genome or method mutation cue.";
		case "retry_tick":
			return "Failure / abandon pressure cue.";
		case "scan_ping":
			return "Research or progress scan cue.";
		case "spawn_rise":
			return "Child spawn cue.";
		case "blue_blast":
		case "blue_patch_deploy":
			return "Blue defense cue.";
		case "kill_cannon":
			return "Kill impact cue.";
		case "victory_hit":
			return "Judge-backed victory cue only.";
		default:
			return "";
	}
}

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function buildCampaignStory(fixture: BattleNormalizedUxFixture): CampaignStoryViewModel | null {
	const genetic = geneticLifecycleOf(fixture);
	if (!genetic) return null;
	const present = new Set(genetic.present_event_types);
	const notEmitted = new Set(genetic.not_emitted_event_types);
	const chapters: CampaignStoryChapter[] = [];
	for (const event of geneticEventsFromFixture(fixture)) {
		const eventType = String(event.event_type);
		if (!isGeneticEventType(eventType)) continue;
		if (!present.has(eventType) || notEmitted.has(eventType)) continue;
		const elapsed =
			typeof event.elapsed_seconds === "number"
				? event.elapsed_seconds
				: typeof event.at_seconds === "number"
					? event.at_seconds
					: null;
		if (elapsed == null) continue;
		const payload = asRecord((event as { payload?: unknown }).payload) ?? {};
		const soundCue = soundCueForGeneticEventType(eventType);
		const victoryAllowed = geneticVictoryAllowed(event);
		chapters.push({
			id: event.id,
			seq: chapters.length + 1,
			eventType,
			atSeconds: elapsed,
			laneId:
				(typeof payload.lane_id === "string" && payload.lane_id) ||
				(typeof event.actor_id === "string" ? event.actor_id : null),
			title: CHAPTER_TITLE[eventType],
			caption: event.summary?.trim() || CHAPTER_CAPTION[eventType],
			soundCue,
			soundCaption: soundCaptionForCue(soundCue, eventType),
			pixiEffect: geneticPixiEffectForEvent(event),
			receiptId:
				(typeof payload.receipt_id === "string" && payload.receipt_id) ||
				(typeof event.evidence?.receipt_id === "string" ? event.evidence.receipt_id : null),
			victoryAllowed,
			mayClaimVictory: false,
		});
	}
	chapters.sort((a, b) => a.atSeconds - b.atSeconds || a.seq - b.seq);
	chapters.forEach((chapter, index) => {
		chapter.seq = index + 1;
	});

	return {
		schema: "battle.campaign_story.v1",
		battleId: fixture.battle_id,
		fixtureId: genetic.fixture_id ?? "battle-004-pr6-genetic-pixi",
		route: "#battle/campaign?engine=pixi&fixture=battle-004-pr6-genetic-pixi",
		mocked: false,
		live: "receipt_replay_campaign",
		chapterCount: chapters.length,
		chapters,
		pulse: {
			activeLineages: fixture.lanes?.length ?? 0,
			geneticPresent: genetic.present_event_types.length,
			geneticNotEmitted: genetic.not_emitted_event_types.length,
			spawns: fixture.lineage?.spawns?.length ?? 0,
			compilePassedChapters: chapters.filter((item) => item.eventType === "compile_passed").length,
			targetContactChapters: chapters.filter((item) => item.eventType === "target_contact_unproven").length,
			abandonedBranches: chapters.filter((item) => item.eventType === "branch_abandoned").length,
		},
		claimBoundary: {
			mayClaim: [
				"campaign_story_chapters_from_genetic_events",
				"sound_captions_for_armed_cues",
				"pixi_polish_controls",
				...genetic.claim_boundary.may_claim,
			],
			mustNotClaim: [
				"campaign_story_is_not_exploit_success",
				"sound_is_not_proof",
				"compile_passed_is_not_runnable",
				"target_contact_is_not_exploit_success",
				...genetic.claim_boundary.must_not_claim,
			],
		},
	};
}

export function campaignChapterAtPlayhead(
	story: CampaignStoryViewModel | null,
	playheadSeconds: number,
): CampaignStoryChapter | null {
	if (!story?.chapters.length) return null;
	const visible = story.chapters.filter((chapter) => chapter.atSeconds <= playheadSeconds + 0.001);
	return visible.at(-1) ?? null;
}
