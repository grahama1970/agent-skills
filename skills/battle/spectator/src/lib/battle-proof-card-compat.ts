import type { BattleNormalizedProofCardFixtureV1 } from "./battle-proof-card-types";
import { buildProofCardViewModel, humanizeProofClaimKey } from "./battle-proof-card-view-model";

const FORBIDDEN_CLAIM_PHRASES = [
	"child exploit generated",
	"child exploit compiled",
	"child exploit runnable",
	"exploit success",
	"command-loop/command-artifacts",
] as const;

export { humanizeProofClaimKey, buildProofCardViewModel };

export function proofCardForbiddenClaimPhrases(): readonly string[] {
	return FORBIDDEN_CLAIM_PHRASES;
}

export function proofCardContainsForbiddenClaim(text: string): string | null {
	const lower = text.toLowerCase();
	for (const phrase of FORBIDDEN_CLAIM_PHRASES) {
		if (lower.includes(phrase)) return phrase;
	}
	return null;
}

export function proofCardNodeRowsCompat(fixture: BattleNormalizedProofCardFixtureV1) {
	return buildProofCardViewModel(fixture).nodes.map((node) => ({
		id: node.id,
		status: node.status,
		verdict: node.verdict,
	}));
}
