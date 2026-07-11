import { isBattleProofCardView } from "../lib/battle-proof-card-registry";
import { isBattleReceiptReplayView } from "../lib/battle-receipt-replay";
import { isBattleDesignView } from "../lib/battle-mockup-lanes";
import { isBattleSynthesisView } from "../lib/battle-synthesis-registry";
import { isBattleCompileView } from "../lib/battle-compile-registry";
import { isBattleRuntimeView } from "../lib/battle-runtime-registry";
import { isBattlePopulationView } from "../lib/battle-population-registry";
import { isBattleLiveView } from "../lib/battle-transport-registry";
import { isBattleCampaignView } from "../lib/battle-campaign-registry";
import { isBattleMusicView } from "../lib/battle-music-registry";

export function BattleProofNav() {
	const hash = typeof window !== "undefined" ? window.location.hash : "";
	const onProof = isBattleProofCardView(hash);
	const onSynthesis = isBattleSynthesisView(hash);
	const onCompile = isBattleCompileView(hash);
	const onRuntime = isBattleRuntimeView(hash);
	const onPopulation = isBattlePopulationView(hash);
	const onLive = isBattleLiveView(hash);
	const onCampaign = isBattleCampaignView(hash);
	const onMusic = isBattleMusicView(hash);
	const onRace =
		!onProof &&
		!onSynthesis &&
		!onCompile &&
		!onRuntime &&
		!onPopulation &&
		!onLive &&
		!onMusic &&
		(isBattleReceiptReplayView() || isBattleDesignView() || hash.startsWith("#battle"));

	return (
		<nav className="battle-proof-nav" aria-label="Battle views" data-qid="battle:proof-card:nav">
			<a href="#battle/receipt?engine=pixi" aria-current={onRace && !hash.includes("pr6-genetic") && !onCampaign ? "page" : undefined} data-qid="battle:nav:race">
				Battle Replay
			</a>
			<a
				href="#battle/receipt?engine=pixi&fixture=battle-004-pr6-genetic-pixi"
				aria-current={hash.includes("pr6-genetic") && !onCampaign ? "page" : undefined}
				data-qid="battle:nav:genetic"
				title="Composite demonstration — causal continuity not proven"
			>
				Genetic Pixi (composite)
			</a>
			<a
				href="#battle/campaign?engine=pixi&fixture=battle-004-pr6-genetic-pixi"
				aria-current={onCampaign ? "page" : undefined}
				data-qid="battle:nav:campaign"
				title="Campaign story over composite genetic fixture"
			>
				Campaign (composite)
			</a>
			<a
				href="#battle/music?fixture=battle-004-music-runtime"
				aria-current={onMusic ? "page" : undefined}
				data-qid="battle:nav:music"
			>
				Music Schedule
			</a>
			<a
				href="#battle/live?engine=pixi&battle=battle-004"
				aria-current={onLive ? "page" : undefined}
				data-qid="battle:nav:live"
			>
				Live Transport
			</a>
			<a href="#battle/proof?fixture=battle-004-pr3b" aria-current={onProof ? "page" : undefined} data-qid="battle:nav:proof">
				Research & Genome Proof
			</a>
			<a href="#battle/synthesis?fixture=battle-004-pr3c" aria-current={onSynthesis ? "page" : undefined} data-qid="battle:nav:synthesis">
				Provider Synthesis
			</a>
			<a href="#battle/compile?fixture=battle-004-pr3d" aria-current={onCompile ? "page" : undefined} data-qid="battle:nav:compile">
				Compile Timeline
			</a>
			<a href="#battle/runtime?fixture=battle-004-pr4" aria-current={onRuntime ? "page" : undefined} data-qid="battle:nav:runtime">
				Runtime & Judge
			</a>
			<a
				href="#battle/population?fixture=battle-004-pr5-population"
				aria-current={onPopulation ? "page" : undefined}
				data-qid="battle:nav:population"
			>
				Population
			</a>
		</nav>
	);
}
