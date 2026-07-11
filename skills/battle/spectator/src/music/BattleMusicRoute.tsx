import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { useBattleMusicFixture } from "../hooks/useBattleMusicFixture";
import { useBattleSound } from "../hooks/useBattleSound";
import { useBattleScore } from "../hooks/useBattleScore";
import { promotedEntriesDueAtPlayhead } from "../lib/battle-normalized-music-fixture";
import { BattleMusicSchedulePanel } from "./BattleMusicSchedulePanel";
import "../proof-card/battle-proof-card.css";

export function BattleMusicRoute() {
	const { viewModel, error, loading } = useBattleMusicFixture();
	const { arm, getContext, enabled } = useBattleSound();
	const score = useBattleScore(getContext);
	const [playheadSeconds, setPlayheadSeconds] = useState(0);
	const [activeMusicId, setActiveMusicId] = useState<string | null>(null);
	const firedRef = useRef(new Set<string>());

	const maxSeconds = useMemo(() => {
		if (!viewModel?.promotedEntries.length) return 120;
		return Math.max(...viewModel.promotedEntries.map((entry) => entry.atSeconds)) + 5;
	}, [viewModel]);

	useEffect(() => {
		firedRef.current = new Set();
		setPlayheadSeconds(0);
		setActiveMusicId(null);
		score.stopAll();
	}, [viewModel?.fixtureId, score.stopAll]);

	const playDue = useCallback(async () => {
		if (!viewModel) return;
		arm();
		const due = promotedEntriesDueAtPlayhead(viewModel, playheadSeconds, firedRef.current);
		for (const entry of due) {
			firedRef.current.add(entry.id);
			await score.playPromotedUrl(entry.oggUrl, {
				loop: entry.loop,
				asLoop: entry.loop || entry.channel === "background",
				label: entry.musicId,
			});
			setActiveMusicId(entry.musicId);
		}
	}, [arm, playheadSeconds, score, viewModel]);

	useEffect(() => {
		if (!enabled || !viewModel) return;
		void playDue();
	}, [enabled, playDue, playheadSeconds, viewModel]);

	if (loading) {
		return <div className="battle-proof-card grid h-full place-items-center text-slate-300">Loading music fixture…</div>;
	}
	if (error) {
		return (
			<div className="battle-proof-card h-full p-4 text-rose-200">
				<BattleProofNav />
				<div data-qid="battle:music:error">BATTLE MUSIC BLOCKED: {error.code} — {error.detail}</div>
			</div>
		);
	}
	if (!viewModel) {
		return <div className="battle-proof-card grid h-full place-items-center text-slate-500">No music fixture loaded.</div>;
	}

	return (
		<div className="battle-proof-card h-full overflow-auto p-4" data-qid="battle:music:route">
			<BattleProofNav />
			<div className="mx-auto mt-3 max-w-[1100px] space-y-3">
				<header>
					<h1 className="text-lg font-black uppercase tracking-[0.08em] text-slate-100">Battle Music Schedule</h1>
					<p className="text-sm text-slate-400">
						Receipt-backed promoted playback only. Music never authorizes Battle truth. Actor-focus previews stay outside this schedule.
					</p>
					<div className="mt-1 text-[11px] text-slate-500" data-qid="battle:music:route-meta">
						{viewModel.route} · mocked:false · composer_live:false
					</div>
				</header>
				<label className="flex items-center gap-3 text-[11px] uppercase tracking-[0.08em] text-slate-400">
					Playhead
					<input
						data-qid="battle:music:playhead-input"
						type="range"
						min={0}
						max={maxSeconds}
						step={0.1}
						value={playheadSeconds}
						onChange={(event) => setPlayheadSeconds(Number(event.target.value))}
						className="w-full"
					/>
				</label>
				<button
					type="button"
					className="rounded border border-white/15 bg-white/5 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em]"
					data-qid="battle:music:seek-spawn"
					onClick={() => {
						const motif = viewModel.promotedEntries.find((entry) => entry.musicId.startsWith("motif:"));
						if (motif) setPlayheadSeconds(motif.atSeconds);
					}}
				>
					Seek spawn motif
				</button>
				<BattleMusicSchedulePanel
					model={viewModel}
					playheadSeconds={playheadSeconds}
					armed={enabled}
					activeMusicId={activeMusicId}
					onArm={() => {
						arm();
						void playDue();
					}}
					onPlayDue={() => void playDue()}
					onStop={() => {
						score.stopAll();
						setActiveMusicId(null);
					}}
				/>
			</div>
		</div>
	);
}
