import { battlePopulationFixtureId, battlePopulationFixtureUrl, isBattlePopulationView } from "./battle-population-registry";
import type { BattleNormalizedPopulationFixtureV1, PopulationLoadError } from "./battle-population-types";
import { validatePopulationFixture } from "./battle-population-validator";
import { loadBattlePopulationViewFixture } from "./battle-view-fixture-loader";
import type { BattleFixtureLoadError } from "./battle-view-fixture";

export type PopulationLoadResult =
	| { ok: true; fixture: BattleNormalizedPopulationFixtureV1; fixtureId: string }
	| { ok: false; error: PopulationLoadError };

function toPopulationError(error: BattleFixtureLoadError): PopulationLoadError {
	if (error.code === "UNSUPPORTED_FIXTURE") return { code: "UNSUPPORTED_FIXTURE", title: error.title, detail: error.detail };
	if (error.code === "FIXTURE_UNAVAILABLE") return { code: "POPULATION_FIXTURE_UNAVAILABLE", title: error.title, detail: error.detail };
	if (error.code === "UNSUPPORTED_SCHEMA" || error.code === "SCHEMA_ROUTE_MISMATCH") {
		return { code: "UNSUPPORTED_SCHEMA", title: error.title, detail: error.detail };
	}
	return { code: "CONTRACT_VALIDATION_FAILED", title: error.title, detail: error.detail };
}

export async function loadBattlePopulationFixture(hash: string): Promise<PopulationLoadResult> {
	if (!isBattlePopulationView(hash)) {
		return {
			ok: false,
			error: { code: "UNSUPPORTED_FIXTURE", title: "UNSUPPORTED FIXTURE", detail: "Not a population route." },
		};
	}
	const fixtureId = battlePopulationFixtureId(hash);
	const url = battlePopulationFixtureUrl(hash);
	if (!fixtureId || !url) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested population fixture is not registered.",
			},
		};
	}

	const result = await loadBattlePopulationViewFixture(url);
	if (!result.ok) return { ok: false, error: toPopulationError(result.error) };
	return { ok: true, fixture: result.fixture, fixtureId };
}

export { validatePopulationFixture };
