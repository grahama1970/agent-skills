import { BATTLE_VIEW_FIXTURE_SCHEMAS, type BattleViewFixtureSchema, type BattleViewKind } from "./battle-view-fixture";

export type BattleFixtureRendererId = "BattleSpectatorArena" | "BattleProofCardPage" | "BattleSynthesisPage" | "BattleCompilePage" | "BattleRuntimePage" | "unsupported";

type RegistryEntry = {
	schema: BattleViewFixtureSchema;
	viewKind: BattleViewKind;
	renderer: BattleFixtureRendererId;
	supported: boolean;
};

/**
 * Schema → view/renderer registry.
 * Unsupported future schemas fail closed until backend fixtures exist.
 */
export const BATTLE_FIXTURE_RENDERERS: Record<string, RegistryEntry> = {
	[BATTLE_VIEW_FIXTURE_SCHEMAS.RACE]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RACE,
		viewKind: "race",
		renderer: "BattleSpectatorArena",
		supported: true,
	},
	[BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD,
		viewKind: "proof-card",
		renderer: "BattleProofCardPage",
		supported: true,
	},
	[BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS,
		viewKind: "synthesis",
		renderer: "BattleSynthesisPage",
		supported: true,
	},
	[BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE,
		viewKind: "compile",
		renderer: "BattleCompilePage",
		supported: true,
	},
	[BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE,
		viewKind: "runtime",
		renderer: "BattleRuntimePage",
		supported: true,
	},
	[BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION]: {
		schema: BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION,
		viewKind: "population",
		renderer: "unsupported",
		supported: false,
	},
};

export function battleFixtureRegistryEntry(schema: string | null | undefined): RegistryEntry | null {
	if (!schema) return null;
	return BATTLE_FIXTURE_RENDERERS[schema] ?? null;
}

export function isSupportedBattleFixtureSchema(schema: string | null | undefined): boolean {
	return battleFixtureRegistryEntry(schema)?.supported === true;
}

export function expectedSchemaForViewKind(viewKind: BattleViewKind): BattleViewFixtureSchema {
	if (viewKind === "proof-card") return BATTLE_VIEW_FIXTURE_SCHEMAS.PROOF_CARD;
	if (viewKind === "synthesis") return BATTLE_VIEW_FIXTURE_SCHEMAS.SYNTHESIS;
	if (viewKind === "compile") return BATTLE_VIEW_FIXTURE_SCHEMAS.COMPILE;
	if (viewKind === "runtime") return BATTLE_VIEW_FIXTURE_SCHEMAS.RUNTIME_JUDGE;
	if (viewKind === "population") return BATTLE_VIEW_FIXTURE_SCHEMAS.POPULATION;
	return BATTLE_VIEW_FIXTURE_SCHEMAS.RACE;
}
