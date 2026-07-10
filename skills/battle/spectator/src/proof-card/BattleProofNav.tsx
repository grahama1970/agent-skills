import { isBattleProofCardView } from "../lib/battle-proof-card-registry";
import { isBattleReceiptReplayView } from "../lib/battle-receipt-replay";
import { isBattleDesignView } from "../lib/battle-mockup-lanes";

export function BattleProofNav() {
	const hash = typeof window !== "undefined" ? window.location.hash : "";
	const onProof = isBattleProofCardView(hash);
	const onRace = isBattleReceiptReplayView() || isBattleDesignView() || hash.startsWith("#battle");

	return (
		<nav className="battle-proof-nav" aria-label="Battle views" data-qid="battle:proof-card:nav">
			<a href="#battle/receipt?engine=pixi" aria-current={!onProof && onRace ? "page" : undefined} data-qid="battle:nav:race">
				Battle Replay
			</a>
			<a
				href="#battle/proof?fixture=battle-004-pr3b"
				aria-current={onProof ? "page" : undefined}
				data-qid="battle:nav:proof"
			>
				Research & Genome Proof
			</a>
		</nav>
	);
}
