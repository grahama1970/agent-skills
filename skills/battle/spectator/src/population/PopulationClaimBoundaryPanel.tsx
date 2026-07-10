import { useState } from "react";
import type { PopulationViewModel } from "../lib/battle-population-view-model";

export function PopulationClaimBoundaryPanel({ model }: { model: PopulationViewModel["claimBoundary"] }) {
	const [showMay, setShowMay] = useState(true);
	const [showMustNot, setShowMustNot] = useState(true);
	return (
		<section className="battle-proof-panel" data-qid="battle:population:claim-boundary">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Claim boundary</div>
				<div className="flex gap-2">
					<button type="button" className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" onClick={() => setShowMay((v) => !v)}>
						What this proves
					</button>
					<button type="button" className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" onClick={() => setShowMustNot((v) => !v)}>
						What this does not prove
					</button>
				</div>
			</div>
			<div className="mt-3 grid gap-1 text-xs text-slate-400">
				<div data-qid="battle:population:claim:not-engine">population_fixture_is_not_full_engine: {model.notFullEngine ? "true" : "false"}</div>
				<div data-qid="battle:population:claim:target-not-exploit">target_contact_is_not_exploit_success: {model.targetNotExploit ? "true" : "false"}</div>
				<div data-qid="battle:population:claim:runnable-not-exploit">runnable_is_not_exploit_success: {model.runnableNotExploit ? "true" : "false"}</div>
			</div>
			<div className="mt-3 grid gap-3 md:grid-cols-2">
				{showMay ? (
					<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3" data-qid="battle:population:claim-may">
						<div className="battle-label text-emerald-300/80">This proof may establish</div>
						<ul className="mt-2 space-y-1 text-sm text-slate-200">
							{model.mayClaim.map((item) => (
								<li key={item}>{item}</li>
							))}
						</ul>
					</div>
				) : null}
				{showMustNot ? (
					<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-3" data-qid="battle:population:claim-must-not">
						<div className="battle-label text-rose-300/80">This proof does not establish</div>
						<ul className="mt-2 space-y-1 text-sm text-slate-200">
							{model.mustNotClaim.map((item) => (
								<li key={item}>{item}</li>
							))}
						</ul>
					</div>
				) : null}
			</div>
		</section>
	);
}
