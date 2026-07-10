import type { BattleNormalizedProofCardFixtureV1 } from "./battle-proof-card-types";
import type { BattleNormalizedUxFixture } from "./battle-types";

/** Known normalized UX fixture schemas. Future synthesis/population schemas register here when backend emits them. */
export const BATTLE_VIEW_FIXTURE_SCHEMAS = {
	RACE: "battle.normalized_ux_fixture.v1",
	PROOF_CARD: "battle.normalized_proof_card_fixture.v1",
	SYNTHESIS: "battle.normalized_synthesis_fixture.v1",
	POPULATION: "battle.normalized_population_fixture.v1",
} as const;

export type BattleViewFixtureSchema = (typeof BATTLE_VIEW_FIXTURE_SCHEMAS)[keyof typeof BATTLE_VIEW_FIXTURE_SCHEMAS];

export type BattleViewKind = "race" | "proof-card" | "synthesis" | "population";

/** Discriminated union of fixtures the spectator can render. Future schemas stay typed but unsupported until registered. */
export type BattleViewFixture =
	| BattleNormalizedUxFixture
	| BattleNormalizedProofCardFixtureV1;

export type BattleFixtureLoadErrorCode =
	| "UNSUPPORTED_FIXTURE"
	| "FIXTURE_UNAVAILABLE"
	| "UNSUPPORTED_SCHEMA"
	| "SCHEMA_ROUTE_MISMATCH"
	| "CONTRACT_VALIDATION_FAILED";

export type BattleFixtureLoadError = {
	code: BattleFixtureLoadErrorCode;
	title: string;
	detail: string;
	schema?: string | null;
};

export type BattleFixtureLoadResult<T extends BattleViewFixture = BattleViewFixture> =
	| { ok: true; fixture: T; schema: T["schema"]; viewKind: BattleViewKind }
	| { ok: false; error: BattleFixtureLoadError };

export function readFixtureSchema(data: unknown): string | null {
	if (!data || typeof data !== "object") return null;
	const schema = (data as { schema?: unknown }).schema;
	return typeof schema === "string" ? schema : null;
}
