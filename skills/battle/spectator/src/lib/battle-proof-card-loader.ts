import { battleProofCardFixtureId, battleProofCardFixtureUrl, isBattleProofCardView } from "./battle-proof-card-registry";
import type { BattleNormalizedProofCardFixtureV1, ProofCardLoadError } from "./battle-proof-card-types";
import { validateProofCardFixture } from "./battle-proof-card-validator";

export type ProofCardLoadResult =
	| { ok: true; fixture: BattleNormalizedProofCardFixtureV1; fixtureId: string }
	| { ok: false; error: ProofCardLoadError };

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

	let response: Response;
	try {
		response = await fetch(url);
	} catch (error) {
		return {
			ok: false,
			error: {
				code: "PROOF_FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: error instanceof Error ? error.message : "No receipt-backed state was loaded.",
			},
		};
	}

	if (!response.ok) {
		return {
			ok: false,
			error: {
				code: "PROOF_FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: `No receipt-backed state was loaded (HTTP ${response.status}).`,
			},
		};
	}

	let data: unknown;
	try {
		data = await response.json();
	} catch {
		return {
			ok: false,
			error: {
				code: "PROOF_FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: "Fixture response was not valid JSON.",
			},
		};
	}

	const validated = validateProofCardFixture(data);
	if (!validated.ok) return validated;
	return { ok: true, fixture: validated.fixture, fixtureId };
}
