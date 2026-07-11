import type { GeneticLifecycleViewModel } from "./lib/battle-genetic-lifecycle";
import { humanizeGeneticClaimKey } from "./lib/battle-genetic-lifecycle";
import { BattleEvidenceLadder } from "./lineage/BattleEvidenceLadder";
import { BattleLineageComparisonPanel } from "./lineage/BattleLineageComparisonPanel";
import type { BattleNormalizedUxFixture } from "./lib/battle-types";

type Props = {
	model: GeneticLifecycleViewModel;
	fixture?: BattleNormalizedUxFixture | null;
};

export function BattleGeneticLifecycleBanner({ model, fixture = null }: Props) {
	return (
		<section className="battle-genetic-banner space-y-3" data-qid="battle:genetic:banner" aria-label="Genetic lifecycle claim boundary">
			{model.compositeDemonstration ? (
				<div
					className="rounded-lg border border-amber-400/40 bg-amber-500/15 p-3"
					data-qid="battle:genetic:composite-banner"
					data-proof-mode={model.presentationProofMode}
					data-causal-continuity={model.causalContinuityProven ? "1" : "0"}
					data-source-run-count={String(model.sourceRunCount)}
					data-timeline-source={model.timelineSource}
				>
					<div className="text-[11px] font-black uppercase tracking-[0.14em] text-amber-100" data-qid="battle:genetic:composite-title">
						COMPOSITE DEMONSTRATION
					</div>
					<p className="mt-1 text-[12px] leading-5 text-amber-50/90" data-qid="battle:genetic:composite-body">
						Stages are assembled from separate proof runs ({model.sourceRunCount}: {model.sourceFixtureKeys.join(", ")}).
						Causal continuity is not proven. Timeline source: {model.timelineSource.replaceAll("_", " ")}.
					</p>
				</div>
			) : null}
			<div className="flex flex-wrap items-center gap-2">
				<span className="rounded border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-violet-200" data-qid="battle:genetic:banner:fixture">
					{model.compositeDemonstration ? "GENETIC PIXI · COMPOSITE" : "GENETIC PIXI FIXTURE"}
				</span>
				{model.compositeDemonstration ? (
					<span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-amber-100" data-qid="battle:genetic:banner:no-causal">
						NO CAUSAL CONTINUITY
					</span>
				) : null}
				<span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-amber-100" data-qid="battle:genetic:banner:no-victory">
					NO VICTORY WITHOUT JUDGE
				</span>
				{model.compilePassedNotRunnable ? (
					<span className="rounded border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-sky-100" data-qid="battle:genetic:banner:compile-not-runnable">
						COMPILE PASS ≠ RUNNABLE
					</span>
				) : null}
				{model.targetContactNotExploit ? (
					<span className="rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-rose-100" data-qid="battle:genetic:banner:target-not-exploit">
						TARGET CONTACT ≠ EXPLOIT
					</span>
				) : null}
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:genetic:present-count">
					present {model.present.length}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:genetic:not-emitted-count">
					not emitted {model.notEmitted.length}
				</span>
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2" data-qid="battle:genetic:claim-boundary">
				<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2" data-qid="battle:genetic:claim-may">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80">May claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
						{model.mayClaim.slice(0, 6).map((item) => (
							<li key={item}>{humanizeGeneticClaimKey(item)}</li>
						))}
					</ul>
				</div>
				<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-2" data-qid="battle:genetic:claim-must-not">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-rose-300/80">Must not claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
						{model.mustNotClaim.slice(0, 8).map((item) => (
							<li key={item}>{humanizeGeneticClaimKey(item)}</li>
						))}
					</ul>
				</div>
			</div>
			<div className="mt-2 flex flex-wrap gap-1" data-qid="battle:genetic:present-types">
				{model.present.map((item) => (
					<span key={item} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300" data-qid={`battle:genetic:present:${item}`}>
						{item}
					</span>
				))}
			</div>
			<div className="mt-1 flex flex-wrap gap-1" data-qid="battle:genetic:not-emitted-types">
				{model.notEmitted.map((item) => (
					<span key={item} className="rounded bg-black/30 px-1.5 py-0.5 text-[10px] text-slate-500" data-qid={`battle:genetic:not-emitted:${item}`}>
						NOT_EMITTED:{item}
					</span>
				))}
			</div>
			<BattleEvidenceLadder present={model.present} notEmitted={model.notEmitted} />
			{fixture ? <BattleLineageComparisonPanel fixture={fixture} composite={model.compositeDemonstration} /> : null}
		</section>
	);
}
