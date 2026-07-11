import { buildEvidenceLadder } from "../lib/battle-evidence-ladder";

type Props = {
	present: string[];
	notEmitted: string[];
};

export function BattleEvidenceLadder({ present, notEmitted }: Props) {
	const rungs = buildEvidenceLadder(present, notEmitted);
	return (
		<section className="rounded-lg border border-white/10 bg-black/25 p-3" data-qid="battle:evidence-ladder" aria-label="Evidence ladder">
			<div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">Evidence ladder</div>
			<p className="mt-1 text-[11px] text-slate-500">Educational progression only — each rung requires its own receipt. No rung invents Judge truth.</p>
			<ol className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
				{rungs.map((rung) => (
					<li
						key={rung.id}
						className="rounded border border-white/10 bg-white/[0.03] px-2 py-1.5"
						data-qid={`battle:evidence-ladder:${rung.id}`}
						data-status={rung.status}
					>
						<div className="flex items-center justify-between gap-2">
							<span className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-200">{rung.label}</span>
							<span className="text-[9px] uppercase tracking-[0.08em] text-slate-500">{rung.status}</span>
						</div>
						<div className="mt-0.5 text-[11px] text-slate-400">{rung.explanation}</div>
					</li>
				))}
			</ol>
		</section>
	);
}
