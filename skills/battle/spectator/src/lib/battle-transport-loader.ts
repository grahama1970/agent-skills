import type { BattleNormalizedUxFixture } from "./battle-types";
import {
	BATTLE_LIVE_TRANSPORT_STREAMS,
	type BattleLiveTransportFixtureKey,
	isRegisteredLiveTransportFixture,
} from "./battle-transport-registry";
import type { BattleLiveEventV1, BattleTransportLoadError, BattleTransportPackage } from "./battle-transport-types";
import {
	validateLiveEvent,
	validateSnapshot,
	validateTransportManifest,
	validateTransportStreamSemantics,
} from "./battle-transport-validator";
import { loadBattleRaceFixture } from "./battle-view-fixture-loader";

function fail(error: BattleTransportLoadError): { ok: false; error: BattleTransportLoadError } {
	return { ok: false, error };
}

async function fetchJson(url: string): Promise<{ ok: true; data: unknown } | { ok: false; error: BattleTransportLoadError }> {
	try {
		const response = await fetch(url);
		if (!response.ok) {
			return fail({
				code: "TRANSPORT_UNAVAILABLE",
				title: "TRANSPORT UNAVAILABLE",
				detail: `Failed to fetch ${url} (${response.status}).`,
			});
		}
		return { ok: true, data: await response.json() };
	} catch (error) {
		return fail({
			code: "TRANSPORT_UNAVAILABLE",
			title: "TRANSPORT UNAVAILABLE",
			detail: error instanceof Error ? error.message : `Failed to fetch ${url}.`,
		});
	}
}

async function fetchText(url: string): Promise<{ ok: true; text: string } | { ok: false; error: BattleTransportLoadError }> {
	try {
		const response = await fetch(url);
		if (!response.ok) {
			return fail({
				code: "TRANSPORT_UNAVAILABLE",
				title: "TRANSPORT UNAVAILABLE",
				detail: `Failed to fetch ${url} (${response.status}).`,
			});
		}
		return { ok: true, text: await response.text() };
	} catch (error) {
		return fail({
			code: "TRANSPORT_UNAVAILABLE",
			title: "TRANSPORT UNAVAILABLE",
			detail: error instanceof Error ? error.message : `Failed to fetch ${url}.`,
		});
	}
}

export async function loadBattleTransportPackage(
	fixtureKey: string,
): Promise<{ ok: true; pack: BattleTransportPackage; companion: BattleNormalizedUxFixture } | { ok: false; error: BattleTransportLoadError }> {
	if (!isRegisteredLiveTransportFixture(fixtureKey)) {
		return fail({
			code: "UNSUPPORTED_FIXTURE",
			title: "UNSUPPORTED FIXTURE",
			detail: `Live transport fixture "${fixtureKey}" is not registered.`,
		});
	}
	const key = fixtureKey as BattleLiveTransportFixtureKey;
	const entry = BATTLE_LIVE_TRANSPORT_STREAMS[key];
	const streamBaseUrl = entry.streamBaseUrl.replace(/\/$/, "");

	const companionResult = await loadBattleRaceFixture(entry.companionFixtureUrl);
	if (!companionResult.ok) {
		return fail({
			code: "TRANSPORT_UNAVAILABLE",
			title: "TRANSPORT UNAVAILABLE",
			detail: companionResult.error.detail,
		});
	}

	const manifestResult = await fetchJson(`${streamBaseUrl}/manifest.json`);
	if (!manifestResult.ok) return manifestResult;
	const manifestValidated = validateTransportManifest(manifestResult.data);
	if (!manifestValidated.ok) return manifestValidated;

	const snapshotResult = await fetchJson(`${streamBaseUrl}/${manifestValidated.manifest.latest_snapshot}`);
	if (!snapshotResult.ok) return snapshotResult;
	const snapshotValidated = validateSnapshot(snapshotResult.data);
	if (!snapshotValidated.ok) return snapshotValidated;

	const eventsResult = await fetchText(`${streamBaseUrl}/${manifestValidated.manifest.events_jsonl}`);
	if (!eventsResult.ok) return eventsResult;
	const events: BattleLiveEventV1[] = [];
	const lines = eventsResult.text.split("\n");
	for (let index = 0; index < lines.length; index += 1) {
		const line = lines[index]!.trim();
		if (!line) continue;
		let parsed: unknown;
		try {
			parsed = JSON.parse(line);
		} catch (error) {
			return fail({
				code: "CONTRACT_VALIDATION_FAILED",
				title: "CONTRACT VALIDATION FAILED",
				detail: `events.jsonl line ${index + 1} is not valid JSON: ${error instanceof Error ? error.message : "parse error"}`,
			});
		}
		const validated = validateLiveEvent(parsed, index + 1);
		if (!validated.ok) return validated;
		events.push(validated.event);
	}

	const semantics = validateTransportStreamSemantics({
		manifest: manifestValidated.manifest,
		snapshot: snapshotValidated.snapshot,
		events,
		companionBattleId: companionResult.fixture.battle_id,
	});
	if (!semantics.ok) return semantics;

	return {
		ok: true,
		pack: {
			manifest: manifestValidated.manifest,
			snapshot: snapshotValidated.snapshot,
			events,
			streamBaseUrl,
			companionFixtureUrl: entry.companionFixtureUrl,
		},
		companion: companionResult.fixture,
	};
}
