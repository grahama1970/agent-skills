import type {
	BattleEffectCueKind,
	BattleEvent,
	BattleNormalizedUxFixture,
	Lane,
	LaneEvent,
	LaneEventKind,
} from "./battle-types";

/** Backend presentation.pixi_effect vocabulary for UX7. */
export type GeneticPixiEffect =
	| "research_scan"
	| "research_receipt"
	| "genome_lock"
	| "gene_shard_join"
	| "gene_shard_fade"
	| "code_authoring"
	| "code_glyph"
	| "compile_error"
	| "compile_lock"
	| "endpoint_pulse"
	| "judge_pending"
	| "branch_fade"
	| "repair_pulse"
	| "repair_glyph"
	| "judge_victory"
	| "genome_promote";

export type GeneticEventType =
	| "research_started"
	| "research_receipt_materialized"
	| "genome_selected"
	| "method_added"
	| "method_rejected"
	| "code_author_started"
	| "specimen_materialized"
	| "compile_failed"
	| "repair_started"
	| "repair_materialized"
	| "compile_passed"
	| "target_contact_unproven"
	| "judge_pending"
	| "judge_exploit_success"
	| "genome_promoted"
	| "branch_abandoned";

export const GENETIC_EVENT_TYPES = [
	"research_started",
	"research_receipt_materialized",
	"genome_selected",
	"method_added",
	"method_rejected",
	"code_author_started",
	"specimen_materialized",
	"compile_failed",
	"repair_started",
	"repair_materialized",
	"compile_passed",
	"target_contact_unproven",
	"judge_pending",
	"judge_exploit_success",
	"genome_promoted",
	"branch_abandoned",
] as const satisfies readonly GeneticEventType[];

export const GENETIC_EVENT_TYPE_SET = new Set<string>(GENETIC_EVENT_TYPES);

/** Events that may never drive victory / kill / containment VFX. */
export const GENETIC_NO_VICTORY_EVENT_TYPES = new Set<GeneticEventType>([
	"research_started",
	"research_receipt_materialized",
	"genome_selected",
	"method_added",
	"method_rejected",
	"code_author_started",
	"specimen_materialized",
	"compile_failed",
	"repair_started",
	"repair_materialized",
	"compile_passed",
	"target_contact_unproven",
	"judge_pending",
	"branch_abandoned",
]);

const EVENT_TO_EFFECT: Record<GeneticEventType, GeneticPixiEffect> = {
	research_started: "research_scan",
	research_receipt_materialized: "research_receipt",
	genome_selected: "genome_lock",
	method_added: "gene_shard_join",
	method_rejected: "gene_shard_fade",
	code_author_started: "code_authoring",
	specimen_materialized: "code_glyph",
	compile_failed: "compile_error",
	repair_started: "repair_pulse",
	repair_materialized: "repair_glyph",
	compile_passed: "compile_lock",
	target_contact_unproven: "endpoint_pulse",
	judge_pending: "judge_pending",
	judge_exploit_success: "judge_victory",
	genome_promoted: "genome_promote",
	branch_abandoned: "branch_fade",
};

const EFFECT_MARKER_FRAME: Record<GeneticPixiEffect, string> = {
	research_scan: "marker-useful",
	research_receipt: "marker-useful",
	genome_lock: "marker-handoff",
	gene_shard_join: "marker-handoff",
	gene_shard_fade: "marker-blocked",
	code_authoring: "marker-useful",
	code_glyph: "marker-useful",
	compile_error: "marker-blocked",
	compile_lock: "marker-useful",
	endpoint_pulse: "marker-blue_blast",
	judge_pending: "marker-useful",
	branch_fade: "marker-blocked",
	repair_pulse: "marker-useful",
	repair_glyph: "marker-useful",
	judge_victory: "marker-promoted",
	genome_promote: "marker-promoted",
};

const EFFECT_ATLAS_FX: Record<GeneticPixiEffect, string> = {
	research_scan: "fx-useful",
	research_receipt: "fx-useful",
	genome_lock: "fx-spawn",
	gene_shard_join: "fx-spawn",
	gene_shard_fade: "fx-blocked",
	code_authoring: "fx-useful",
	code_glyph: "fx-useful",
	compile_error: "fx-blocked",
	compile_lock: "fx-useful",
	endpoint_pulse: "fx-useful",
	judge_pending: "fx-useful",
	branch_fade: "fx-blocked",
	repair_pulse: "fx-useful",
	repair_glyph: "fx-useful",
	judge_victory: "fx-promoted",
	genome_promote: "fx-promoted",
};

export type GeneticLifecycleBlock = {
	schema: "battle.genetic_lifecycle_events.v1";
	fixture_id?: string;
	fixture_url?: string;
	route?: string;
	required_event_types?: string[];
	present_event_types: string[];
	not_emitted_event_types: string[];
	not_emitted_reasons?: Record<string, string>;
	claim_boundary: {
		may_claim: string[];
		must_not_claim: string[];
		compile_passed_is_not_runnable?: boolean;
		target_contact_is_not_exploit_success?: boolean;
		victory_requires_judge_receipt?: boolean;
	};
};

export type GeneticLifecycleViewModel = {
	present: string[];
	notEmitted: string[];
	notEmittedReasons: Record<string, string>;
	mayClaim: string[];
	mustNotClaim: string[];
	compilePassedNotRunnable: boolean;
	targetContactNotExploit: boolean;
	victoryRequiresJudge: boolean;
	fixtureId: string;
	route: string;
};

type GeneticPresentation = {
	pixi_effect?: string;
	victory_allowed?: boolean;
	kill_allowed?: boolean;
	containment_allowed?: boolean;
	must_not_render_as?: string[];
};

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function isGeneticEventType(value: string | undefined | null): value is GeneticEventType {
	return Boolean(value && GENETIC_EVENT_TYPE_SET.has(value));
}

export function isGeneticLaneEventKind(kind: string | undefined | null): kind is GeneticEventType {
	return isGeneticEventType(kind);
}

export function geneticLifecycleOf(fixture: BattleNormalizedUxFixture | null | undefined): GeneticLifecycleBlock | null {
	const block = asRecord((fixture as { genetic_lifecycle?: unknown } | null | undefined)?.genetic_lifecycle);
	if (!block) return null;
	if (block.schema !== "battle.genetic_lifecycle_events.v1") return null;
	const claim = asRecord(block.claim_boundary);
	if (!claim) return null;
	return {
		schema: "battle.genetic_lifecycle_events.v1",
		fixture_id: typeof block.fixture_id === "string" ? block.fixture_id : undefined,
		fixture_url: typeof block.fixture_url === "string" ? block.fixture_url : undefined,
		route: typeof block.route === "string" ? block.route : undefined,
		required_event_types: Array.isArray(block.required_event_types)
			? block.required_event_types.filter((item): item is string => typeof item === "string")
			: undefined,
		present_event_types: Array.isArray(block.present_event_types)
			? block.present_event_types.filter((item): item is string => typeof item === "string")
			: [],
		not_emitted_event_types: Array.isArray(block.not_emitted_event_types)
			? block.not_emitted_event_types.filter((item): item is string => typeof item === "string")
			: [],
		not_emitted_reasons: asRecord(block.not_emitted_reasons)
			? Object.fromEntries(
					Object.entries(asRecord(block.not_emitted_reasons)!).filter(
						(entry): entry is [string, string] => typeof entry[1] === "string",
					),
				)
			: undefined,
		claim_boundary: {
			may_claim: Array.isArray(claim.may_claim) ? claim.may_claim.filter((item): item is string => typeof item === "string") : [],
			must_not_claim: Array.isArray(claim.must_not_claim)
				? claim.must_not_claim.filter((item): item is string => typeof item === "string")
				: [],
			compile_passed_is_not_runnable: claim.compile_passed_is_not_runnable === true,
			target_contact_is_not_exploit_success: claim.target_contact_is_not_exploit_success === true,
			victory_requires_judge_receipt: claim.victory_requires_judge_receipt === true,
		},
	};
}

export function hasGeneticLifecycle(fixture: BattleNormalizedUxFixture | null | undefined): boolean {
	return geneticLifecycleOf(fixture) != null;
}

export function geneticLifecycleViewModel(fixture: BattleNormalizedUxFixture): GeneticLifecycleViewModel | null {
	const genetic = geneticLifecycleOf(fixture);
	if (!genetic) return null;
	return {
		present: genetic.present_event_types,
		notEmitted: genetic.not_emitted_event_types,
		notEmittedReasons: genetic.not_emitted_reasons ?? {},
		mayClaim: genetic.claim_boundary.may_claim,
		mustNotClaim: genetic.claim_boundary.must_not_claim,
		compilePassedNotRunnable: genetic.claim_boundary.compile_passed_is_not_runnable === true,
		targetContactNotExploit: genetic.claim_boundary.target_contact_is_not_exploit_success === true,
		victoryRequiresJudge: genetic.claim_boundary.victory_requires_judge_receipt === true,
		fixtureId: genetic.fixture_id ?? "battle-004-pr6-genetic-pixi",
		route: genetic.route ?? "#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi",
	};
}

export function geneticEventsFromFixture(fixture: BattleNormalizedUxFixture): BattleEvent[] {
	return (fixture.events ?? []).filter((event) => isGeneticEventType(String(event.event_type)));
}

function presentationOf(event: BattleEvent): GeneticPresentation {
	return (asRecord((event as { presentation?: unknown }).presentation) as GeneticPresentation | null) ?? {};
}

function payloadOf(event: BattleEvent): Record<string, unknown> {
	return asRecord((event as { payload?: unknown }).payload) ?? {};
}

export function geneticPixiEffectForEvent(event: BattleEvent): GeneticPixiEffect | null {
	if (!isGeneticEventType(String(event.event_type))) return null;
	const presentation = presentationOf(event);
	const fromPresentation = presentation.pixi_effect;
	if (typeof fromPresentation === "string" && fromPresentation in EFFECT_MARKER_FRAME) {
		return fromPresentation as GeneticPixiEffect;
	}
	return EVENT_TO_EFFECT[event.event_type as GeneticEventType];
}

/** Fail-closed: victory/kill/containment only when presentation explicitly allows and event is Judge success / promote. */
export function geneticVictoryAllowed(event: BattleEvent): boolean {
	if (!isGeneticEventType(String(event.event_type))) return false;
	const eventType = event.event_type as GeneticEventType;
	if (GENETIC_NO_VICTORY_EVENT_TYPES.has(eventType)) return false;
	const presentation = presentationOf(event);
	if (presentation.victory_allowed !== true) return false;
	if (presentation.must_not_render_as?.includes("victory")) return false;
	return eventType === "judge_exploit_success" || eventType === "genome_promoted";
}

export function geneticCueKindForEvent(event: BattleEvent): BattleEffectCueKind {
	const eventType = String(event.event_type);
	if (!isGeneticEventType(eventType)) return "useful";
	if (geneticVictoryAllowed(event)) return "promoted";
	return eventType as BattleEffectCueKind;
}

export function geneticMarkerAtlasFrame(effect: GeneticPixiEffect): string {
	return EFFECT_MARKER_FRAME[effect];
}

export function geneticEffectAtlasFrame(effect: GeneticPixiEffect): string {
	return EFFECT_ATLAS_FX[effect];
}

export function geneticEventToLaneEvent(event: BattleEvent, allottedSeconds: number): LaneEvent | null {
	if (!isGeneticEventType(String(event.event_type))) return null;
	const effect = geneticPixiEffectForEvent(event);
	if (!effect) return null;
	if (!geneticVictoryAllowed(event) && (effect === "judge_victory" || effect === "genome_promote")) {
		return null;
	}
	const payload = payloadOf(event);
	const elapsed =
		typeof event.elapsed_seconds === "number"
			? event.elapsed_seconds
			: typeof event.at_seconds === "number"
				? event.at_seconds
				: null;
	if (elapsed == null) return null;
	const receiptId =
		(typeof payload.receipt_id === "string" && payload.receipt_id) ||
		(typeof event.evidence?.receipt_id === "string" ? event.evidence.receipt_id : undefined) ||
		event.id;
	const x = Math.max(0, Math.min(100, (elapsed / Math.max(1, allottedSeconds)) * 100));
	return {
		id: event.id,
		kind: event.event_type as LaneEventKind,
		x,
		label: event.summary?.toUpperCase?.() ?? String(event.event_type).toUpperCase(),
		timeLabel: "genetic",
		proven: true,
		proofMode: event.proof_mode ?? "receipt_backed_fixture",
		receiptId,
		elapsed_seconds: elapsed,
		at_seconds: elapsed,
		order_index:
			typeof (event as { order_index?: number }).order_index === "number"
				? (event as { order_index: number }).order_index
				: null,
		label_band: "upper",
		marker_priority: 70,
		collision_group: `genetic:${event.event_type}`,
		geneticEffect: effect,
		geneticEventType: event.event_type as GeneticEventType,
		victoryAllowed: geneticVictoryAllowed(event),
	};
}

export function laneIdForGeneticEvent(event: BattleEvent): string | null {
	const payload = payloadOf(event);
	if (typeof payload.lane_id === "string" && payload.lane_id) return payload.lane_id;
	if (typeof event.red_lane_id === "string" && event.red_lane_id) return event.red_lane_id;
	if (typeof event.actor_id === "string" && event.actor_id.startsWith("payload")) return event.actor_id;
	return null;
}

/** Inject receipt-backed genetic markers onto matching lanes (immutable copy). */
export function lanesWithGeneticLifecycleEvents(lanes: Lane[], fixture: BattleNormalizedUxFixture): Lane[] {
	const genetic = geneticLifecycleOf(fixture);
	if (!genetic) return lanes;
	const allotted =
		fixture.timeline_elapsed_axis_model?.axis_max_elapsed_seconds ??
		fixture.battle_clock?.allotted_seconds ??
		fixture.battle_timeline_control?.time_domain?.allotted_seconds ??
		180;
	const byLane = new Map<string, LaneEvent[]>();
	for (const event of geneticEventsFromFixture(fixture)) {
		const present = genetic.present_event_types.includes(String(event.event_type));
		if (!present) continue;
		if (genetic.not_emitted_event_types.includes(String(event.event_type))) continue;
		const laneId = laneIdForGeneticEvent(event);
		if (!laneId) continue;
		const laneEvent = geneticEventToLaneEvent(event, allotted);
		if (!laneEvent) continue;
		const list = byLane.get(laneId) ?? [];
		list.push(laneEvent);
		byLane.set(laneId, list);
	}
	if (!byLane.size) return lanes;
	return lanes.map((lane) => {
		const extras = byLane.get(lane.id);
		if (!extras?.length) return lane;
		const existingIds = new Set(lane.events.map((item) => item.id));
		const merged = [...lane.events, ...extras.filter((item) => !existingIds.has(item.id))];
		merged.sort(
			(a, b) =>
				(a.elapsed_seconds ?? a.at_seconds ?? a.x) - (b.elapsed_seconds ?? b.at_seconds ?? b.x) ||
				a.id.localeCompare(b.id),
		);
		return { ...lane, events: merged };
	});
}

export function humanizeGeneticClaimKey(key: string): string {
	return key.replace(/_/g, " ");
}

/** Paths that must never appear in genetic UX chrome. */
export function geneticFixtureLeaksRawPaths(text: string): boolean {
	return (
		text.includes("tau-dag-run/") ||
		text.includes("command-loop/command-artifacts") ||
		text.includes("/tmp/") ||
		text.includes("provider-workspace")
	);
}
