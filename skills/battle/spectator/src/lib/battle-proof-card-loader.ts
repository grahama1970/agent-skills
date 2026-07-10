import { battleProofCardFixtureId, battleProofCardFixtureUrl, isBattleProofCardView } from "./battle-proof-card-registry";
import type { BattleNormalizedProofCardFixtureV1, ProofCardLoadError } from "./battle-proof-card-types";
import { formatBattleFixtureLoadError, loadBattleProofCardViewFixture } from "./battle-view-fixture-loader";
import type { BattleFixtureLoadError } from "./battle-view-fixture";

export type ProofCardLoadResult =
	| { ok: true; fixture: BattleNormalizedProofCardFixtureV1; fixtureId: string }
	| { ok: false; error: ProofCardLoadError };

function toProofCardError(error: BattleFixtureLoadError): ProofCardLoadError {
	if (error.code === "UNSUPPORTED_FIXTURE") {
		return { code: "UNSUPPORTED_FIXTURE", title: error.title, detail: error.detail };
	}
	if (error.code === "FIXTURE_UNAVAILABLE") {
		return { code: "PROOF_FIXTURE_UNAVAILABLE", title: error.title, detail: error.detail };
	}
	if (error.code === "UNSUPPORTED_SCHEMA" || error.code === "SCHEMA_ROUTE_MISMATCH") {
		return { code: "UNSUPPORTED_SCHEMA", title: error.title, detail: error.detail };
	}
	return { code: "CONTRACT_VALIDATION_FAILED", title: error.title, detail: error.detail };
}

export async function loadBattleProofCardFixture(hash: string): Promise<ProofCardLoadResult> {
	if (!isBattleProofCardView(hash)) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "Not a proof-card route.",
			},
		};
	}

	const fixtureId = battleProofCardFixtureId(hash);
	const url = battleProofCardFixtureUrl(hash);
	if (!fixtureId || !url) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_FIXTURE",
				title: "UNSUPPORTED FIXTURE",
				detail: "The requested proof-card fixture is not registered.",
			},
		};
	}

	const result = await loadBattleProofCardViewFixture(url);
	if (!result.ok) {
		return { ok: false, error: toProofCardError(result.error) };
	}
	return { ok: true, fixture: result.fixture, fixtureId };
}

export { formatBattleFixtureLoadError };
