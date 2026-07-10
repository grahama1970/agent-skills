import { battleHashPath, battleHashSearchParams } from "./battle-receipt-replay";

/** Stable fixture id → public JSON URL. Rejects arbitrary path/URL params. */
export const PROOF_CARD_FIXTURES = {
	"battle-004-pr3b": "/battle-fixtures/battle-004-pr3b-proof-card/battle.normalized_proof_card_fixture.json",
} as const;

export type BattleProofCardFixtureId = keyof typeof PROOF_CARD_FIXTURES;

/** Legacy kind aliases from the thin UX1 slice. */
const KIND_TO_FIXTURE_ID: Record<string, BattleProofCardFixtureId> = {
	"pr3b-research-combiner": "battle-004-pr3b",
};

export function isBattleProofCardView(hash = typeof window !== "undefined" ? window.location.hash : ""): boolean {
	const path = (hash || "").split("?")[0] || battleHashPath();
	return (
		path === "#battle/proof" ||
		path.startsWith("#battle/proof/") ||
		path === "#battle/proof-card" ||
		path.startsWith("#battle/proof-card/")
	);
}

export function battleProofCardFixtureId(hash = typeof window !== "undefined" ? window.location.hash : ""): BattleProofCardFixtureId | null {
	const params = battleHashSearchParams(hash);
	const fixture = params.get("fixture");
	if (fixture) {
		return fixture in PROOF_CARD_FIXTURES ? (fixture as BattleProofCardFixtureId) : null;
	}
	const kind = params.get("kind");
	if (kind && kind in KIND_TO_FIXTURE_ID) return KIND_TO_FIXTURE_ID[kind];
	// Default for bare #battle/proof
	return "battle-004-pr3b";
}

export function battleProofCardFixtureUrl(hash = typeof window !== "undefined" ? window.location.hash : ""): string | null {
	const id = battleProofCardFixtureId(hash);
	return id ? PROOF_CARD_FIXTURES[id] : null;
}

export function isRegisteredProofCardFixtureId(id: string): id is BattleProofCardFixtureId {
	return id in PROOF_CARD_FIXTURES;
}
