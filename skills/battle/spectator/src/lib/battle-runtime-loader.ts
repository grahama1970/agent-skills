import { battleRuntimeFixtureId, battleRuntimeFixtureUrl, isBattleRuntimeView } from "./battle-runtime-registry";
import type { BattleNormalizedRuntimeJudgeFixtureV1, RuntimeLoadError } from "./battle-runtime-types";
import { validateRuntimeJudgeFixture } from "./battle-runtime-validator";
import { loadBattleRuntimeViewFixture } from "./battle-view-fixture-loader";
import type { BattleFixtureLoadError } from "./battle-view-fixture";

export type RuntimeLoadResult =
	| { ok: true; fixture: BattleNormalizedRuntimeJudgeFixtureV1; fixtureId: string }
	| { ok: false; error: RuntimeLoadError };

function toRuntimeError(error: BattleFixtureLoadError): RuntimeLoadError {
	if (error.code === "UNSUPPORTED_FIXTURE") return { code: "UNSUPPORTED_FIXTURE", title: error.title, detail: error.detail };
	if (error.code === "FIXTURE_UNAVAILABLE") return { code: "RUNTIME_FIXTURE_UNAVAILABLE", title: error.title, detail: error.detail };
	if (error.code === "UNSUPPORTED_SCHEMA" || error.code === "SCHEMA_ROUTE_MISMATCH") {
		return { code: "UNSUPPORTED_SCHEMA", title: error.title, detail: error.detail };
	}
	return { code: "CONTRACT_VALIDATION_FAILED", title: error.title, detail: error.detail };
}

export async function loadBattleRuntimeFixture(hash: string): Promise<RuntimeLoadResult> {
	if (!isBattleRuntimeView(hash)) {
		return {
			ok: false,
			error: { code: "UNSUPPORTED_FIXTURE", title: "UNSUPPORTED FIXTURE", detail: "Not a runtime route." },
		};
	}
	const fixtureId = battleRuntimeFixtureId(hash);
	const url = battleRuntimeFixtureUrl(hash);
	if (!fixtureId || !url) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested runtime fixture is not registered.",
			},
		};
	}

	const result = await loadBattleRuntimeViewFixture(url);
	if (!result.ok) return { ok: false, error: toRuntimeError(result.error) };
	return { ok: true, fixture: result.fixture, fixtureId };
}

export { validateRuntimeJudgeFixture };
