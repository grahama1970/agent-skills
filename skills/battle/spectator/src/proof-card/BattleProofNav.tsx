import { isBattleProofCardView } from "../lib/battle-proof-card-registry";
import { isBattleReceiptReplayView } from "../lib/battle-receipt-replay";
import { isBattleDesignView } from "../lib/battle-mockup-lanes";
import { isBattleSynthesisView } from "../lib/battle-synthesis-registry";
import { isBattleCompileView } from "../lib/battle-compile-registry";
import { isBattleRuntimeView } from "../lib/battle-runtime-registry";

export function BattleProofNav() {
	const hash = typeof window !== "undefined" ? window.location.hash : "";
	const onProof = isBattleProofCardView(hash);
	const onSynthesis = isBattleSynthesisView(hash);
	const onCompile = isBattleCompileView(hash);
	const onRuntime = isBattleRuntimeView(hash);
	const onRace = !onProof && !onSynthesis && !onCompile && !onRuntime && (isBattleReceiptReplayView() || isBattleDesignView() || hash.startsWith("#battle"));

	return (
		<nav className="battle-proof-nav" aria-label="Battle views" data-qid="battle:proof-card:nav">
			<a href="#battle/receipt?engine=pixi" aria-current={onRace ? "page" : undefined} data-qid="battle:nav:race">
				Battle Replay
			</a>
			<a
				href="#battle/proof?fixture=battle-004-pr3b"
				aria-current={onProof ? "page" : undefined}
				data-qid="battle:nav:proof"
			>
				Research & Genome Proof
			</a>
			<a
				href="#battle/synthesis?fixture=battle-004-pr3c"
				aria-current={onSynthesis ? "page" : undefined}
				data-qid="battle:nav:synthesis"
			>
				Provider Synthesis
			</a>
			<a
				href="#battle/compile?fixture=battle-004-pr3d"
				aria-current={onCompile ? "page" : undefined}
				data-qid="battle:nav:compile"
			>
				Compile Timeline
			</a>
			<a
				href="#battle/runtime?fixture=battle-004-pr4"
				aria-current={onRuntime ? "page" : undefined}
				data-qid="battle:nav:runtime"
			>
				Runtime & Judge
			</a>
		</nav>
	);
}
