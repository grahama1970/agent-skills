import { useState } from "react";
import type { CompileViewModel } from "../lib/battle-compile-view-model";

export function CompileClaimBoundaryPanel({
	model,
	focused,
}: {
	model: CompileViewModel["claimBoundary"];
	focused?: boolean;
}) {
	const [showMay, setShowMay] = useState(true);
	const [showMustNot, setShowMustNot] = useState(true);

	return (
		<section className="battle-proof-panel" data-qid="battle:compile:claim-boundary" data-focused={focused ? "true" : undefined}>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div className="battle-label">Claim boundary</div>
				<div className="flex gap-2">
					<button type="button" className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" aria-pressed={showMay} onClick={() => setShowMay((v) => !v)}>
						What this proves
					</button>
					<button type="button" className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" aria-pressed={showMustNot} onClick={() => setShowMustNot((v) => !v)}>
						What this does not prove
					</button>
				</div>
			</div>
			<div className="battle-proof-notice mt-3" data-qid="battle:compile:claim:not-runnable">
				compile_passed_is_not_runnable: {model.compilePassedIsNotRunnable ? "true" : "false"}
			</div>
			<div className="mt-3 grid gap-3 md:grid-cols-2">
				{showMay ? (
					<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3" data-qid="battle:compile:claim-may">
						<div className="battle-label text-emerald-300/80">This proof may establish</div>
						<ul className="mt-2 space-y-1 text-sm text-slate-200">
							{model.mayClaim.map((item) => (
								<li key={item}>{item}</li>
							))}
						</ul>
					</div>
				) : null}
				{showMustNot ? (
					<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-3" data-qid="battle:compile:claim-must-not">
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
