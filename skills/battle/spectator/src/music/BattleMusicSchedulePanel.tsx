import type { MusicScheduleViewModel } from "../lib/battle-normalized-music-fixture";

type Props = {
	model: MusicScheduleViewModel;
	playheadSeconds: number;
	armed: boolean;
	activeMusicId: string | null;
	onArm: () => void;
	onPlayDue: () => void;
	onStop: () => void;
};

export function BattleMusicSchedulePanel({
	model,
	playheadSeconds,
	armed,
	activeMusicId,
	onArm,
	onPlayDue,
	onStop,
}: Props) {
	return (
		<section className="battle-music-panel rounded-xl border border-white/10 bg-black/35 p-3 text-slate-200" data-qid="battle:music:banner" aria-label="Receipt-backed music schedule">
			<div className="flex flex-wrap items-center gap-2">
				<span className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100" data-qid="battle:music:fixture">
					{model.fixtureId}
				</span>
				<span className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100" data-qid="battle:music:proof-mode">
					{model.proofMode}
				</span>
				<span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-amber-100" data-qid="battle:music:composer-live">
					composer_live:false
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:music:playhead">
					t={playheadSeconds.toFixed(1)}s
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:music:active">
					active {activeMusicId ?? "none"}
				</span>
			</div>

			<div className="mt-2 flex flex-wrap gap-2">
				<button type="button" className="rounded border border-white/15 bg-white/5 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:arm" onClick={onArm}>
					{armed ? "Sound armed" : "Arm promoted playback"}
				</button>
				<button type="button" className="rounded border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-cyan-100" data-qid="battle:music:play-due" onClick={onPlayDue}>
					Play due promoted
				</button>
				<button type="button" className="rounded border border-white/10 bg-black/40 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:stop" onClick={onStop}>
					Stop
				</button>
			</div>

			<div className="mt-3 grid gap-2 md:grid-cols-2" data-qid="battle:music:claim-boundary">
				<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80">May claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px]" data-qid="battle:music:claim-may">
						{model.mayClaim.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
				<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-2">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-rose-300/80">Must not claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px]" data-qid="battle:music:claim-must-not">
						{model.mustNotClaim.map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			</div>

			<div className="mt-3" data-qid="battle:music:schedule">
				<div className="text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">Promoted schedule ({model.promotedEntries.length})</div>
				<ul className="mt-1 space-y-1">
					{model.promotedEntries.map((entry) => (
						<li
							key={entry.id}
							className="rounded border border-white/10 bg-black/25 px-2 py-1.5 text-[11px]"
							data-qid={`battle:music:entry:${entry.id}`}
							data-music-id={entry.musicId}
							data-playback-class="promoted"
							data-at-seconds={String(entry.atSeconds)}
							data-ogg-url={entry.oggUrl}
							data-receipt-id={entry.receiptId}
						>
							<span className="font-bold text-cyan-100">{entry.musicId}</span>
							<span className="text-slate-500"> · t={entry.atSeconds.toFixed(3)}s · {entry.permissionKind}</span>
							<div className="truncate text-[10px] text-slate-500">{entry.oggUrl}</div>
							<div className="truncate text-[10px] text-slate-600">receipt {entry.receiptId}</div>
						</li>
					))}
				</ul>
			</div>

			<div className="mt-2 flex flex-wrap gap-1" data-qid="battle:music:present">
				{model.eventsPresent.map((item) => (
					<span key={item} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px]" data-qid={`battle:music:present:${item}`}>
						{item}
					</span>
				))}
			</div>
			<div className="mt-1 flex flex-wrap gap-1" data-qid="battle:music:not-emitted">
				{model.eventsNotEmitted.map((item) => (
					<span key={item} className="rounded bg-black/30 px-1.5 py-0.5 text-[10px] text-slate-500" data-qid={`battle:music:not-emitted:${item}`}>
						NOT_EMITTED:{item}
					</span>
				))}
			</div>
			<div className="mt-2 text-[10px] text-slate-500" data-qid="battle:music:validation-receipts">
				validation receipts: {model.validationReceiptIds.join(", ") || "none"}
			</div>
		</section>
	);
}
