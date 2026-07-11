import type { MusicScheduleViewModel } from "../lib/battle-normalized-music-fixture";
import { musicClaimMayCopy, musicClaimMustNotCopy } from "../lib/battle-music-claim-copy";
import "./battle-music.css";

type Props = {
	model: MusicScheduleViewModel;
	playheadSeconds: number;
	maxSeconds: number;
	armed: boolean;
	activeMusicId: string | null;
	playbackNote: string;
	onArm: () => void;
	onPlayDue: () => void;
	onStop: () => void;
	onSeek: (seconds: number) => void;
	onSeekSpawn: () => void;
	onResetPlayhead: () => void;
};

export function BattleMusicSchedulePanel({
	model,
	playheadSeconds,
	maxSeconds,
	armed,
	activeMusicId,
	playbackNote,
	onArm,
	onPlayDue,
	onStop,
	onSeek,
	onSeekSpawn,
	onResetPlayhead,
}: Props) {
	return (
		<section className="battle-music-panel battle-music-route space-y-3 text-slate-200" data-qid="battle:music:banner" aria-label="Receipt-backed music schedule">
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
				<span className="rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-rose-100" data-qid="battle:music:no-speaker-claim">
					NO SPEAKER CLAIM
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:music:active">
					active {activeMusicId ?? "none"}
				</span>
			</div>

			<div className="battle-music-disclaimer" data-qid="battle:music:disclaimer">
				Arming may decode promoted OGG in this browser session. That does <strong>not</strong> prove speaker/headphone output, musical quality, death, victory, or Judge outcomes.
				<div className="mt-1 text-[11px] text-amber-100/80" data-qid="battle:music:playback-note">
					{playbackNote}
				</div>
			</div>

			<div className="battle-music-scrubber" data-qid="battle:music:scrubber">
				<div className="battle-music-scrubber__meta">
					<span>
						Playhead <span className="battle-music-scrubber__time" data-qid="battle:music:playhead">{playheadSeconds.toFixed(2)}s</span>
					</span>
					<span data-qid="battle:music:playhead-max">span 0–{maxSeconds.toFixed(1)}s</span>
					<span data-qid="battle:music:entry-count">{model.promotedEntries.length} promoted entries</span>
				</div>
				<div className="battle-music-scrubber__track">
					<div className="battle-music-scrubber__marks" data-qid="battle:music:scrubber-marks">
						{model.promotedEntries.map((entry) => {
							const pct = maxSeconds > 0 ? (entry.atSeconds / maxSeconds) * 100 : 0;
							return (
								<div key={entry.id} className="battle-music-scrubber__mark" style={{ left: `${pct}%` }} data-qid={`battle:music:mark:${entry.id}`}>
									<div className="battle-music-scrubber__mark-stem" />
									<div className="battle-music-scrubber__mark-label">{entry.musicId}</div>
								</div>
							);
						})}
					</div>
					<input
						data-qid="battle:music:playhead-input"
						className="battle-music-scrubber__range"
						type="range"
						min={0}
						max={maxSeconds}
						step={0.1}
						value={playheadSeconds}
						aria-label="Music schedule playhead"
						onChange={(event) => onSeek(Number(event.target.value))}
					/>
				</div>
				<div className="battle-music-scrubber__actions">
					<button type="button" className="rounded border border-white/15 bg-white/5 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:arm" onClick={onArm}>
						{armed ? "Sound armed" : "Arm promoted playback"}
					</button>
					<button type="button" className="rounded border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-cyan-100" data-qid="battle:music:play-due" onClick={onPlayDue}>
						Play due promoted
					</button>
					<button type="button" className="rounded border border-white/15 bg-white/5 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:seek-spawn" onClick={onSeekSpawn}>
						Seek spawn motif
					</button>
					<button type="button" className="rounded border border-white/10 bg-black/40 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:reset" onClick={onResetPlayhead}>
						Reset 0s
					</button>
					<button type="button" className="rounded border border-white/10 bg-black/40 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]" data-qid="battle:music:stop" onClick={onStop}>
						Stop
					</button>
				</div>
			</div>

			<div className="battle-music-claim" data-qid="battle:music:claim-boundary">
				<div className="battle-music-claim__box battle-music-claim__box--may">
					<div className="battle-music-claim__title">May claim</div>
					<ul className="battle-music-claim__list" data-qid="battle:music:claim-may">
						{model.mayClaim.map((item) => {
							const copy = musicClaimMayCopy(item);
							return (
								<li key={item} className="battle-music-claim__item" data-qid={`battle:music:claim-may:${item}`}>
									<strong>{copy.title}</strong>
									<span>{copy.detail}</span>
								</li>
							);
						})}
					</ul>
				</div>
				<div className="battle-music-claim__box battle-music-claim__box--must-not">
					<div className="battle-music-claim__title">Must not claim</div>
					<ul className="battle-music-claim__list" data-qid="battle:music:claim-must-not">
						{model.mustNotClaim.map((item) => {
							const copy = musicClaimMustNotCopy(item);
							return (
								<li key={item} className="battle-music-claim__item" data-qid={`battle:music:claim-must-not:${item}`}>
									<strong>{copy.title}</strong>
									<span>{copy.detail}</span>
								</li>
							);
						})}
					</ul>
				</div>
			</div>

			<div data-qid="battle:music:schedule">
				<div className="text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">Promoted schedule ({model.promotedEntries.length})</div>
				<ul className="mt-1 space-y-1">
					{model.promotedEntries.map((entry) => {
						const due = entry.atSeconds <= playheadSeconds + 0.001;
						const active = activeMusicId === entry.musicId;
						return (
							<li
								key={entry.id}
								className="battle-music-entry rounded border border-white/10 bg-black/25 px-2 py-1.5 text-[11px]"
								data-qid={`battle:music:entry:${entry.id}`}
								data-music-id={entry.musicId}
								data-playback-class="promoted"
								data-at-seconds={String(entry.atSeconds)}
								data-ogg-url={entry.oggUrl}
								data-receipt-id={entry.receiptId}
								data-due={due ? "1" : "0"}
								data-active={active ? "1" : "0"}
							>
								<span className="font-bold text-cyan-100">{entry.musicId}</span>
								<span className="text-slate-500">
									{" "}
									· t={entry.atSeconds.toFixed(3)}s · {entry.permissionKind}
									{due ? " · DUE" : ""}
									{active ? " · ACTIVE" : ""}
								</span>
								<div className="truncate text-[10px] text-slate-500">{entry.oggUrl}</div>
								<div className="truncate text-[10px] text-slate-600">receipt {entry.receiptId}</div>
							</li>
						);
					})}
				</ul>
			</div>

			<div className="flex flex-wrap gap-1" data-qid="battle:music:present">
				{model.eventsPresent.map((item) => (
					<span key={item} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px]" data-qid={`battle:music:present:${item}`}>
						{item}
					</span>
				))}
			</div>
			<div className="flex flex-wrap gap-1" data-qid="battle:music:not-emitted">
				{model.eventsNotEmitted.map((item) => (
					<span key={item} className="rounded bg-black/30 px-1.5 py-0.5 text-[10px] text-slate-500" data-qid={`battle:music:not-emitted:${item}`}>
						NOT_EMITTED:{item}
					</span>
				))}
			</div>
			<div className="text-[10px] text-slate-500" data-qid="battle:music:validation-receipts">
				validation receipts: {model.validationReceiptIds.join(", ") || "none"}
			</div>
		</section>
	);
}
