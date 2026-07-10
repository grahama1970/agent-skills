import type { BattleNormalizedProofCardFixtureV1 } from "./battle-proof-card-types";
import { validateProofCardFixture } from "./battle-proof-card-validator";
import type { BattleNormalizedCompileFixtureV1 } from "./battle-compile-types";
import { validateCompileFixture } from "./battle-compile-validator";
import type { BattleNormalizedSynthesisFixtureV1 } from "./battle-synthesis-types";
import { validateSynthesisFixture } from "./battle-synthesis-validator";
import type { BattleNormalizedUxFixture } from "./battle-types";
import {
	BATTLE_VIEW_FIXTURE_SCHEMAS,
	readFixtureSchema,
	type BattleFixtureLoadError,
	type BattleFixtureLoadResult,
	type BattleViewFixture,
	type BattleViewKind,
} from "./battle-view-fixture";
import { battleFixtureRegistryEntry, expectedSchemaForViewKind } from "./battle-view-fixture-registry";

export async function fetchBattleFixtureJson(url: string): Promise<BattleFixtureLoadResult<BattleViewFixture> | { ok: true; data: unknown }> {
	let response: Response;
	try {
		response = await fetch(url);
	} catch (error) {
		return {
			ok: false,
			error: {
				code: "FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: error instanceof Error ? error.message : "No receipt-backed state was loaded.",
			},
		};
	}

	if (!response.ok) {
		return {
			ok: false,
			error: {
				code: "FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: `No receipt-backed state was loaded (HTTP ${response.status}).`,
			},
		};
	}

	try {
		const data: unknown = await response.json();
		return { ok: true, data };
	} catch {
		return {
			ok: false,
			error: {
				code: "FIXTURE_UNAVAILABLE",
				title: "PROOF FIXTURE UNAVAILABLE",
				detail: "Fixture response was not valid JSON.",
			},
		};
	}
}

/** Discriminate + validate a fixture payload for a specific spectator view. */
export function discriminateBattleViewFixture(
	data: unknown,
	expectedViewKind: BattleViewKind,
): BattleFixtureLoadResult<BattleViewFixture> {
	const schema = readFixtureSchema(data);
	if (!schema) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_SCHEMA",
				title: "UNSUPPORTED SCHEMA",
				detail: `Expected ${expectedSchemaForViewKind(expectedViewKind)}.`,
				schema: null,
			},
		};
	}

	const entry = battleFixtureRegistryEntry(schema);
	if (!entry || !entry.supported) {
		return {
			ok: false,
			error: {
				code: "UNSUPPORTED_SCHEMA",
				title: "UNSUPPORTED SCHEMA",
				detail: entry
					? `Schema ${schema} is registered but not yet supported for rendering.`
					: `Unknown fixture schema: ${schema}.`,
				schema,
			},
		};
	}

	const expectedSchema = expectedSchemaForViewKind(expectedViewKind);
	if (schema !== expectedSchema || entry.viewKind !== expectedViewKind) {
		return {
			ok: false,
			error: {
				code: "SCHEMA_ROUTE_MISMATCH",
				title: "UNSUPPORTED SCHEMA",
				detail: `Route expects ${expectedSchema} (${expectedViewKind}); fixture declared ${schema} (${entry.viewKind}).`,
				schema,
			},
		};
	}

	if (schema === BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD) {
		const validated = validateProofCardFixture(data);
		if (!validated.ok) {
			return {
				ok: false,
				error: {
					code: validated.error.code === "UNSUPPORTED_SCHEMA" ? "UNSUPPORTED_SCHEMA" : "CONTRACT_VALIDATION_FAILED",
					title: validated.error.title,
					detail: validated.error.detail,
					schema,
				},
			};
		}
		return {
			ok: true,
			fixture: validated.fixture,
			schema: validated.fixture.schema,
			viewKind: "proof-card",
		};
	}

	if (schema === BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS) {
		const validated = validateSynthesisFixture(data);
		if (!validated.ok) {
			return {
				ok: false,
				error: {
					code: validated.error.code === "UNSUPPORTED_SCHEMA" ? "UNSUPPORTED_SCHEMA" : "CONTRACT_VALIDATION_FAILED",
					title: validated.error.title,
					detail: validated.error.detail,
					schema,
				},
			};
		}
		return {
			ok: true,
			fixture: validated.fixture,
			schema: validated.fixture.schema,
			viewKind: "synthesis",
		};
	}

	if (schema === BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE) {
		const validated = validateCompileFixture(data);
		if (!validated.ok) {
			return {
				ok: false,
				error: {
					code: validated.error.code === "UNSUPPORTED_SCHEMA" ? "UNSUPPORTED_SCHEMA" : "CONTRACT_VALIDATION_FAILED",
					title: validated.error.title,
					detail: validated.error.detail,
					schema,
				},
			};
		}
		return {
			ok: true,
			fixture: validated.fixture,
			schema: validated.fixture.schema,
			viewKind: "compile",
		};
	}

	if (schema === BATTLE_VIEW_FIXTURE_SCHEMAS.RACE) {
		const raceError = validateRaceFixtureShape(data);
		if (raceError) return { ok: false, error: raceError };
		const fixture = data as BattleNormalizedUxFixture;
		return {
			ok: true,
			fixture,
			schema: fixture.schema,
			viewKind: "race",
		};
	}

	return {
		ok: false,
		error: {
			code: "UNSUPPORTED_SCHEMA",
			title: "UNSUPPORTED SCHEMA",
			detail: `No validator registered for ${schema}.`,
			schema,
		},
	};
}

export async function loadBattleViewFixture(
	url: string,
	expectedViewKind: BattleViewKind,
): Promise<BattleFixtureLoadResult<BattleViewFixture>> {
	const fetched = await fetchBattleFixtureJson(url);
	if (!fetched.ok) return fetched;
	if (!("data" in fetched)) return fetched;
	return discriminateBattleViewFixture(fetched.data, expectedViewKind);
}

export async function loadBattleRaceFixture(url: string): Promise<BattleFixtureLoadResult<BattleNormalizedUxFixture>> {
	const result = await loadBattleViewFixture(url, "race");
	if (!result.ok) return result;
	return {
		ok: true,
		fixture: result.fixture as BattleNormalizedUxFixture,
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RACE,
		viewKind: "race",
	};
}

export async function loadBattleProofCardViewFixture(
	url: string,
): Promise<BattleFixtureLoadResult<BattleNormalizedProofCardFixtureV1>> {
	const result = await loadBattleViewFixture(url, "proof-card");
	if (!result.ok) return result;
	return {
		ok: true,
		fixture: result.fixture as BattleNormalizedProofCardFixtureV1,
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD,
		viewKind: "proof-card",
	};
}

export async function loadBattleSynthesisViewFixture(
	url: string,
): Promise<BattleFixtureLoadResult<BattleNormalizedSynthesisFixtureV1>> {
	const result = await loadBattleViewFixture(url, "synthesis");
	if (!result.ok) return result;
	return {
		ok: true,
		fixture: result.fixture as BattleNormalizedSynthesisFixtureV1,
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS,
		viewKind: "synthesis",
	};
}

export async function loadBattleCompileViewFixture(
	url: string,
): Promise<BattleFixtureLoadResult<BattleNormalizedCompileFixtureV1>> {
	const result = await loadBattleViewFixture(url, "compile");
	if (!result.ok) return result;
	return {
		ok: true,
		fixture: result.fixture as BattleNormalizedCompileFixtureV1,
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE,
		viewKind: "compile",
	};
}

function validateRaceFixtureShape(data: unknown): BattleFixtureLoadError | null {
	if (!data || typeof data !== "object") {
		return {
			code: "CONTRACT_VALIDATION_FAILED",
			title: "CONTRACT VALIDATION FAILED",
			detail: "Race fixture must be an object.",
			schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RACE,
		};
	}
	const record = data as Record<string, unknown>;
	if (record.schema !== BATTLE_VIEW_FIXTURE_SCHEMAS.RACE) {
		return {
			code: "UNSUPPORTED_SCHEMA",
			title: "UNSUPPORTED SCHEMA",
			detail: `Expected ${BATTLE_VIEW_FIXTURE_SCHEMAS.RACE}.`,
			schema: typeof record.schema === "string" ? record.schema : null,
		};
	}
	if (!Array.isArray(record.lanes)) {
		return {
			code: "CONTRACT_VALIDATION_FAILED",
			title: "CONTRACT VALIDATION FAILED",
			detail: "Race fixture must include lanes[].",
			schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RACE,
		};
	}
	return null;
}

export function formatBattleFixtureLoadError(error: BattleFixtureLoadError): string {
	return `${error.title}: ${error.detail}`;
}
