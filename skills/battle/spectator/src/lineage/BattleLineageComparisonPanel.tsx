import type { BattleNormalizedUxFixture } from "../lib/battle-types";
import { buildLineageComparisonViewModel } from "../lib/battle-lineage-comparison";

type Props = {
	fixture: BattleNormalizedUxFixture;
	composite: boolean;
};

export function BattleLineageComparisonPanel({ fixture, composite }: Props) {
	const model = buildLineageComparisonViewModel(fixture, composite);
	if (!model) return null;
	return (
		<section className="rounded-lg border border-white/10 bg-black/25 p-3" data-qid="battle:lineage-comparison" aria-label="Parent child lineage comparison">
			<div className="flex flex-wrap items-center gap-2">
				<span className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">Parent / child comparison</span>
				{composite ? (
					<span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.1em] text-amber-100" data-qid="battle:lineage-comparison:composite">
						PREVIEW · NOT ADAPTIVE CANARY
					</span>
				) : null}
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2">
				<div className="rounded border border-white/10 bg-white/[0.03] p-2" data-qid="battle:lineage-comparison:parent">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-cyan-200">Parent</div>
					<div className="text-[12px] text-slate-200">{model.parent?.name ?? "not emitted"}</div>
					<div className="text-[10px] text-slate-500">{model.parent?.laneId ?? "—"} · gen {model.parent?.generation ?? "—"}</div>
				</div>
				<div className="rounded border border-white/10 bg-white/[0.03] p-2" data-qid="battle:lineage-comparison:child">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-violet-200">Child</div>
					<div className="text-[12px] text-slate-200">{model.child?.name ?? "not emitted"}</div>
					<div className="text-[10px] text-slate-500">{model.child?.laneId ?? "—"} · gen {model.child?.generation ?? "—"}</div>
				</div>
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2">
				<div data-qid="battle:lineage-comparison:inherited">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-emerald-300/80">Inherited (fixture-listed)</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-300">
						{model.inherited.slice(0, 6).map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
				<div data-qid="battle:lineage-comparison:new">
					<div className="text-[10px] font-black uppercase tracking-[0.08em] text-amber-200/80">Changed / unknown</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-300">
						{model.newOrUnknown.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			</div>
			<div className="mt-2 text-[10px] text-slate-500" data-qid="battle:lineage-comparison:questions">
				Viewer questions: {model.questions.join(" · ")}
			</div>
			<div className="mt-1 text-[10px] text-rose-200/80" data-qid="battle:lineage-comparison:does-not-prove">
				Does not prove: {model.doesNotProve.slice(0, 4).join("; ")}
			</div>
		</section>
	);
}
