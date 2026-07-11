/**
 * Fail-closed consumer for battle.normalized_music_fixture.v1.
 * Plays only playback_class:promoted entries with receipt authorization.
 */

export const BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA = "battle.normalized_music_fixture.v1" as const;

export type BattleMusicPlaybackClass = "promoted" | "local_preview";

export type BattleMusicAssetRef = {
	public_url: string;
	sha256: string;
};

export type BattleMusicScheduleEntry = {
	schema: "battle.music_schedule_entry.v1";
	schedule_entry_id: string;
	playback_class: BattleMusicPlaybackClass;
	promotion_id: string;
	score_id: string;
	asset_ref: {
		kind: string;
		music_id: string;
		ogg: BattleMusicAssetRef;
		midi?: BattleMusicAssetRef;
	};
	authorization: {
		permission_kind: string;
		source_receipt_id: string;
		source_receipt_kind?: string;
		source_receipt_sha256?: string;
		lane_id?: string;
		sprite_id?: string;
	};
	timing: {
		resolved_start_elapsed_seconds: number;
		source_elapsed_seconds?: number;
		timing_mode?: string;
	};
	playback?: {
		channel?: string;
		loop?: boolean;
		duck_policy?: string;
		interrupt_policy?: string;
		priority?: number;
	};
	claims?: {
		proves?: string[];
		does_not_prove?: string[];
	};
	semantic_authority?: boolean;
};

export type BattleNormalizedMusicFixture = {
	schema: typeof BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA;
	fixture_id: string;
	battle_id: string;
	generated_at: string;
	status: string;
	mocked: boolean;
	proof_mode: string;
	events_present: string[];
	events_not_emitted: string[];
	promotions: Array<{
		promotion_id: string;
		canonical_music_id: string;
		status: string;
		assets: Array<{
			role: string;
			public_url: string;
			sha256: string;
			media_type?: string;
			bytes?: number;
			duration_seconds?: number;
		}>;
		validation?: { receipt_id?: string; receipt_sha256?: string; status?: string };
		eligibility?: { schedule_eligible?: boolean; terminal_playback_authority_granted?: boolean };
	}>;
	schedule: {
		entries: BattleMusicScheduleEntry[];
		clock_ref?: { elapsed_time_domain?: string; source_receipt_id?: string };
		claim_boundary?: { may_claim: string[]; must_not_claim: string[] };
	};
	claim_boundary: { may_claim: string[]; must_not_claim: string[] };
	playback_contract: {
		browser_format?: string;
		time_domain?: string;
		music_never_authorizes_battle_truth?: boolean;
		local_actor_focus_is_preview_only?: boolean;
		midi_is_source_material?: boolean;
	};
	frontend_handoff: {
		route: string;
		schedule_field: string;
		promotion_field: string;
		claim_boundary_field: string;
	};
	receipt_refs: Array<{ receipt_id: string; sha256?: string; receipt_kind?: string; event_id?: string }>;
	provenance?: Record<string, unknown>;
	context_summary?: Record<string, unknown>;
	preview_catalog?: unknown;
};

export type MusicFixtureLoadError = {
	code: "unknown_fixture" | "fetch_failed" | "invalid_schema" | "contract_failed";
	detail: string;
};

export type MusicScheduleViewModel = {
	schema: typeof BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA;
	fixtureId: string;
	battleId: string;
	route: string;
	mocked: false;
	proofMode: string;
	composerLive: false;
	promotedEntries: Array<{
		id: string;
		musicId: string;
		oggUrl: string;
		oggSha256: string;
		midiUrl: string | null;
		atSeconds: number;
		loop: boolean;
		channel: string;
		permissionKind: string;
		receiptId: string;
		promotionId: string;
		spriteId: string | null;
		laneId: string | null;
	}>;
	eventsPresent: string[];
	eventsNotEmitted: string[];
	mayClaim: string[];
	mustNotClaim: string[];
	validationReceiptIds: string[];
	claimBoundary: { may_claim: string[]; must_not_claim: string[] };
};

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function validateNormalizedMusicFixture(raw: unknown): MusicFixtureLoadError | null {
	const fixture = asRecord(raw);
	if (!fixture) return { code: "invalid_schema", detail: "fixture is not an object" };
	if (fixture.schema !== BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA) {
		return { code: "invalid_schema", detail: `expected ${BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA}` };
	}
	if (fixture.mocked !== false) return { code: "contract_failed", detail: "mocked must be false" };
	if (fixture.status !== "PASS") return { code: "contract_failed", detail: "status must be PASS" };
	const schedule = asRecord(fixture.schedule);
	if (!schedule || !Array.isArray(schedule.entries)) {
		return { code: "contract_failed", detail: "schedule.entries required" };
	}
	const claim = asRecord(fixture.claim_boundary);
	if (!claim || !Array.isArray(claim.may_claim) || !Array.isArray(claim.must_not_claim)) {
		return { code: "contract_failed", detail: "claim_boundary required" };
	}
	if (!Array.isArray(fixture.events_not_emitted) || !Array.isArray(fixture.events_present)) {
		return { code: "contract_failed", detail: "events_present/events_not_emitted required" };
	}
	const handoff = asRecord(fixture.frontend_handoff);
	if (!handoff?.route) return { code: "contract_failed", detail: "frontend_handoff.route required" };
	for (const entry of schedule.entries) {
		const row = asRecord(entry);
		if (!row) return { code: "contract_failed", detail: "schedule entry invalid" };
		if (row.playback_class === "promoted") {
			const auth = asRecord(row.authorization);
			const asset = asRecord(row.asset_ref);
			const ogg = asRecord(asset?.ogg);
			const timing = asRecord(row.timing);
			if (!auth?.source_receipt_id) {
				return { code: "contract_failed", detail: "promoted entry missing source_receipt_id" };
			}
			if (typeof ogg?.public_url !== "string" || !String(ogg.public_url).startsWith("/battle-audio/promoted/v1/")) {
				return { code: "contract_failed", detail: "promoted ogg must be under /battle-audio/promoted/v1/" };
			}
			if (typeof timing?.resolved_start_elapsed_seconds !== "number") {
				return { code: "contract_failed", detail: "promoted entry missing resolved_start_elapsed_seconds" };
			}
		}
	}
	return null;
}

export function buildMusicScheduleViewModel(fixture: BattleNormalizedMusicFixture): MusicScheduleViewModel {
	const promotedEntries = fixture.schedule.entries
		.filter((entry) => entry.playback_class === "promoted")
		.map((entry) => ({
			id: entry.schedule_entry_id,
			musicId: entry.asset_ref.music_id,
			oggUrl: entry.asset_ref.ogg.public_url,
			oggSha256: entry.asset_ref.ogg.sha256,
			midiUrl: entry.asset_ref.midi?.public_url ?? null,
			atSeconds: entry.timing.resolved_start_elapsed_seconds,
			loop: Boolean(entry.playback?.loop),
			channel: entry.playback?.channel ?? "background",
			permissionKind: entry.authorization.permission_kind,
			receiptId: entry.authorization.source_receipt_id,
			promotionId: entry.promotion_id,
			spriteId: entry.authorization.sprite_id ?? null,
			laneId: entry.authorization.lane_id ?? null,
		}))
		.sort((a, b) => a.atSeconds - b.atSeconds || a.id.localeCompare(b.id));

	const validationReceiptIds = fixture.promotions
		.map((item) => item.validation?.receipt_id)
		.filter((item): item is string => Boolean(item));

	return {
		schema: BATTLE_NORMALIZED_MUSIC_FIXTURE_SCHEMA,
		fixtureId: fixture.fixture_id,
		battleId: fixture.battle_id,
		route: fixture.frontend_handoff.route,
		mocked: false,
		proofMode: fixture.proof_mode,
		composerLive: false,
		promotedEntries,
		eventsPresent: [...fixture.events_present],
		eventsNotEmitted: [...fixture.events_not_emitted],
		mayClaim: [...fixture.claim_boundary.may_claim],
		mustNotClaim: [...fixture.claim_boundary.must_not_claim],
		validationReceiptIds,
		claimBoundary: fixture.claim_boundary,
	};
}

export function promotedEntriesDueAtPlayhead(
	model: MusicScheduleViewModel,
	playheadSeconds: number,
	firedIds: Set<string>,
): MusicScheduleViewModel["promotedEntries"] {
	return model.promotedEntries.filter(
		(entry) => !firedIds.has(entry.id) && entry.atSeconds <= playheadSeconds + 0.001,
	);
}
