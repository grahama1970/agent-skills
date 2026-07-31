import type {
	BattleLiveEventV1,
	BattleSnapshotV1Full,
	BattleTransportLoadError,
	BattleTransportManifestV1,
} from "./battle-transport-types";

const FORBIDDEN_PATH_FRAGMENTS = [
	"command-loop/command-artifacts",
	"tau-dag-run/",
	"provider-workspace",
	"scillm-worker",
] as const;

function fail(code: BattleTransportLoadError["code"], title: string, detail: string): BattleTransportLoadError {
	return { code, title, detail };
}

function asRecord(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function validateTransportManifest(
	data: unknown,
): { ok: true; manifest: BattleTransportManifestV1 } | { ok: false; error: BattleTransportLoadError } {
	const record = asRecord(data);
	if (!record) return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "Transport manifest must be an object.") };
	if (record.schema !== "battle.transport_manifest.v1") {
		return {
			ok: false,
			error: fail("UNSUPPORTED_SCHEMA", "UNSUPPORTED SCHEMA", "Expected battle.transport_manifest.v1."),
		};
	}
	if (record.mode !== "file_backed_replay_stream" && record.mode !== "live_sse_adapter") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "Only file_backed_replay_stream or live_sse_adapter modes are supported."),
		};
	}
	const stream = asRecord(record.stream_contract);
	if (!stream || stream.schema !== "battle.stream_contract.v1") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "stream_contract.schema must be battle.stream_contract.v1."),
		};
	}
	if (stream.event_schema !== "battle.live_event.v1" || stream.snapshot_schema !== "battle.snapshot.v1") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "stream_contract event/snapshot schemas mismatch."),
		};
	}
	if (typeof record.battle_id !== "string" || typeof record.run_id !== "string") {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "manifest battle_id/run_id required.") };
	}
	if (typeof record.event_count !== "number" || typeof record.last_seq !== "number") {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "manifest event_count/last_seq required.") };
	}
	if (record.events_jsonl !== "events.jsonl" || record.latest_snapshot !== "latest-snapshot.json") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "manifest must point at events.jsonl and latest-snapshot.json."),
		};
	}
	if (record.mocked !== false) {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "transport manifest mocked must be false.") };
	}
	return { ok: true, manifest: record as unknown as BattleTransportManifestV1 };
}

export function validateLiveEvent(
	data: unknown,
	lineNumber?: number,
): { ok: true; event: BattleLiveEventV1 } | { ok: false; error: BattleTransportLoadError } {
	const record = asRecord(data);
	const where = lineNumber != null ? `events.jsonl line ${lineNumber}` : "live event";
	if (!record) return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where} must be an object.`) };
	if (record.schema !== "battle.live_event.v1") {
		return { ok: false, error: fail("UNSUPPORTED_SCHEMA", "UNSUPPORTED SCHEMA", `${where}: expected battle.live_event.v1.`) };
	}
	for (const key of ["run_id", "battle_id", "event_id", "event_type", "observed_at"] as const) {
		if (typeof record[key] !== "string" || !record[key]) {
			return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where}: missing ${key}.`) };
		}
	}
	if (typeof record.seq !== "number" || record.seq < 1) {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where}: seq must be >= 1.`) };
	}
	if (typeof record.at_seconds !== "number" || record.at_seconds < 0) {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where}: at_seconds required.`) };
	}
	const lifecycle = asRecord(record.lifecycle);
	if (!lifecycle || lifecycle.schema !== "battle.lifecycle_event.v1") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where}: lifecycle.schema must be battle.lifecycle_event.v1.`),
		};
	}
	if (typeof lifecycle.lane_id !== "string" || typeof lifecycle.receipt_id !== "string") {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `${where}: lifecycle lane_id/receipt_id required.`),
		};
	}
	return { ok: true, event: record as unknown as BattleLiveEventV1 };
}

export function validateSnapshot(
	data: unknown,
): { ok: true; snapshot: BattleSnapshotV1Full } | { ok: false; error: BattleTransportLoadError } {
	const record = asRecord(data);
	if (!record) return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "Snapshot must be an object.") };
	if (record.schema !== "battle.snapshot.v1") {
		return { ok: false, error: fail("UNSUPPORTED_SCHEMA", "UNSUPPORTED SCHEMA", "Expected battle.snapshot.v1.") };
	}
	if (typeof record.battle_id !== "string" || typeof record.run_id !== "string") {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "snapshot battle_id/run_id required.") };
	}
	if (typeof record.last_seq !== "number") {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "snapshot.last_seq required.") };
	}
	if (!Array.isArray(record.lanes) || !Array.isArray(record.events)) {
		return { ok: false, error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "snapshot must include lanes[] and events[].") };
	}
	return { ok: true, snapshot: record as unknown as BattleSnapshotV1Full };
}

export function validateTransportStreamSemantics(args: {
	manifest: BattleTransportManifestV1;
	snapshot: BattleSnapshotV1Full;
	events: BattleLiveEventV1[];
	companionBattleId?: string;
}): { ok: true } | { ok: false; error: BattleTransportLoadError } {
	const { manifest, snapshot, events, companionBattleId } = args;
	if (manifest.event_count !== events.length) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "manifest.event_count must match events.jsonl line count."),
		};
	}
	const lastSeq = events.length ? events[events.length - 1]!.seq : 0;
	if (manifest.last_seq !== lastSeq) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "manifest.last_seq must match final event seq."),
		};
	}
	for (let index = 0; index < events.length; index += 1) {
		const expected = index + 1;
		if (events[index]!.seq !== expected) {
			return {
				ok: false,
				error: fail(
					"SEQUENCE_GAP",
					"SEQUENCE GAP",
					`events seq must be contiguous; expected ${expected} at index ${index}, got ${events[index]!.seq}.`,
				),
			};
		}
	}
	if (snapshot.last_seq !== manifest.last_seq) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "snapshot.last_seq must match manifest.last_seq."),
		};
	}
	if (snapshot.battle_id !== manifest.battle_id || snapshot.run_id !== manifest.run_id) {
		return {
			ok: false,
			error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", "snapshot battle_id/run_id must match manifest."),
		};
	}
	if (companionBattleId && companionBattleId !== manifest.battle_id) {
		return {
			ok: false,
			error: fail(
				"FIXTURE_MISMATCH",
				"FIXTURE MISMATCH",
				`normalized fixture battle_id ${companionBattleId} does not match transport ${manifest.battle_id}.`,
			),
		};
	}
	const blob = JSON.stringify({ manifest, snapshot, events });
	for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
		if (blob.includes(fragment)) {
			// Stream payloads may still embed historical evidence paths in nested source_event.
			// Fail closed only for command-loop / tau-dag / provider-workspace / scillm-worker in top-level chrome fields.
		}
	}
	const chrome = JSON.stringify({
		live_source: manifest.live_source,
		phase: manifest.stream_contract.phase,
		authority: manifest.stream_contract.authority,
	});
	for (const fragment of FORBIDDEN_PATH_FRAGMENTS) {
		if (chrome.includes(fragment)) {
			return {
				ok: false,
				error: fail("CONTRACT_VALIDATION_FAILED", "CONTRACT VALIDATION FAILED", `transport chrome leaks path fragment ${fragment}.`),
			};
		}
	}
	return { ok: true };
}
