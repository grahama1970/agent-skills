import { battleSynthesisFixtureId, battleSynthesisFixtureUrl, isBattleSynthesisView } from "./battle-synthesis-registry";
import type { BattleNormalizedSynthesisFixtureV1, SynthesisLoadError } from "./battle-synthesis-types";
import { validateSynthesisFixture } from "./battle-synthesis-validator";
import { loadBattleSynthesisViewFixture } from "./battle-view-fixture-loader";
import type { BattleFixtureLoadError } from "./battle-view-fixture";

export type SynthesisLoadResult =
	| { ok: true; fixture: BattleNormalizedSynthesisFixtureV1; fixtureId: string }
	| { ok: false; error: SynthesisLoadError };

function toSynthesisError(error: BattleFixtureLoadError): SynthesisLoadError {
	if (error.code === "UNSUPPORTED_FIXTURE") return { code: "UNSUPPORTED_FIXTURE", title: error.title, detail: error.detail };
	if (error.code === "FIXTURE_UNAVAILABLE") return { code: "SYNTHESIS_FIXTURE_UNAVAILABLE", title: error.title, detail: error.detail };
	if (error.code === "UNSUPPORTED_SCHEMA" || error.code === "SCHEMA_ROUTE_MISMATCH") {
		return { code: "UNSUPPORTED_SCHEMA", title: error.title, detail: error.detail };
	}
	return { code: "CONTRACT_VALIDATION_FAILED", title: error.title, detail: error.detail };
}

export async function loadBattleSynthesisFixture(hash: string): Promise<SynthesisLoadResult> {
	if (!isBattleSynthesisView(hash)) {
		return {
			ok: false,
			error: { code: "UNSUPPORTED_FIXTURE", title: "UNSUPPORTED FIXTURE", detail: "Not a synthesis route." },
		};
	}
	const fixtureId = battleSynthesisFixtureId(hash);
	const url = battleSynthesisFixtureUrl(hash);
	if (!fixtureId || !url) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested synthesis fixture is not registered.",
			},
		};
	}

	const result = await loadBattleSynthesisViewFixture(url);
	if (!result.ok) return { ok: false, error: toSynthesisError(result.error) };
	return { ok: true, fixture: result.fixture, fixtureId };
}

export { validateSynthesisFixture };
