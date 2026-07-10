import { battleCompileFixtureId, battleCompileFixtureUrl, isBattleCompileView } from "./battle-compile-registry";
import type { BattleNormalizedCompileFixtureV1, CompileLoadError } from "./battle-compile-types";
import { validateCompileFixture } from "./battle-compile-validator";
import { loadBattleCompileViewFixture } from "./battle-view-fixture-loader";
import type { BattleFixtureLoadError } from "./battle-view-fixture";

export type CompileLoadResult =
	| { ok: true; fixture: BattleNormalizedCompileFixtureV1; fixtureId: string }
	| { ok: false; error: CompileLoadError };

function toCompileError(error: BattleFixtureLoadError): CompileLoadError {
	if (error.code === "UNSUPPORTED_FIXTURE") return { code: "UNSUPPORTED_FIXTURE", title: error.title, detail: error.detail };
	if (error.code === "FIXTURE_UNAVAILABLE") return { code: "COMPILE_FIXTURE_UNAVAILABLE", title: error.title, detail: error.detail };
	if (error.code === "UNSUPPORTED_SCHEMA" || error.code === "SCHEMA_ROUTE_MISMATCH") {
		return { code: "UNSUPPORTED_SCHEMA", title: error.title, detail: error.detail };
	}
	return { code: "CONTRACT_VALIDATION_FAILED", title: error.title, detail: error.detail };
}

export async function loadBattleCompileFixture(hash: string): Promise<CompileLoadResult> {
	if (!isBattleCompileView(hash)) {
		return {
			ok: false,
			error: { code: "UNSUPPORTED_FIXTURE", title: "UNSUPPORTED FIXTURE", detail: "Not a compile route." },
		};
	}
	const fixtureId = battleCompileFixtureId(hash);
	const url = battleCompileFixtureUrl(hash);
	if (!fixtureId || !url) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested compile fixture is not registered.",
			},
		};
	}

	const result = await loadBattleCompileViewFixture(url);
	if (!result.ok) return { ok: false, error: toCompileError(result.error) };
	return { ok: true, fixture: result.fixture, fixtureId };
}

export { validateCompileFixture };
