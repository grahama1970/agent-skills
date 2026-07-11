import type { BattleTransportViewModel } from "./lib/battle-transport-types";

type Props = {
	model: BattleTransportViewModel;
	onReturnToLive: () => void;
	onRecover?: () => void;
};

export function BattleLiveTransportBanner({ model, onReturnToLive, onRecover }: Props) {
	return (
		<section className="battle-live-transport-banner" data-qid="battle:live:banner" aria-label="Battle live transport">
			<div className="flex flex-wrap items-center gap-2">
				<span
					className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100"
					data-qid="battle:live:banner:mode"
				>
					FILE-BACKED STREAM
				</span>
				<span
					className="rounded border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-violet-100"
					data-qid="battle:live:banner:phase"
				>
					{model.phase.replace(/_/g, " ").toUpperCase()}
				</span>
				<span
					className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
					data-qid="battle:live:banner:mocked"
				>
					MOCKED: {model.mocked ? "YES" : "NO"}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:status">
					status {model.status}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:seq">
					seq {model.appliedSeq}/{model.lastSeq}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:transport">
					{model.transport}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:event-count">
					events {model.eventCount}
				</span>
				{!model.followLive ? (
					<button
						type="button"
						className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-amber-100"
						data-qid="battle:live:return-to-live"
						onClick={onReturnToLive}
					>
						Return to live
					</button>
				) : (
					<span className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80" data-qid="battle:live:following">
						Following live cursor
					</span>
				)}
				{model.status === "gap_recovery" && onRecover ? (
					<button
						type="button"
						className="rounded border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-rose-100"
						data-qid="battle:live:recover-snapshot"
						onClick={onRecover}
					>
						Reload snapshot
					</button>
				) : null}
			</div>
			<div className="mt-2 grid gap-1 text-[11px] text-slate-300 md:grid-cols-3">
				<div data-qid="battle:live:battle-id">battle_id: {model.battleId}</div>
				<div data-qid="battle:live:run-id">run_id: {model.runId}</div>
				<div data-qid="battle:live:source">live_source: {model.liveSource}</div>
				<div data-qid="battle:live:cursor">cursor_seconds: {model.cursorSeconds.toFixed(3)}</div>
				<div data-qid="battle:live:live-seconds">live_seconds: {model.liveSeconds.toFixed(3)}</div>
				<div data-qid="battle:live:authority">authority: normalized fixture + stream events</div>
			</div>
			{model.error ? (
				<div className="mt-2 rounded border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100" data-qid="battle:live:error">
					{model.error}
				</div>
			) : null}
		</section>
	);
}
