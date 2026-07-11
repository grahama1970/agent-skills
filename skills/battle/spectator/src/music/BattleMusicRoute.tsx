import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BattleProofNav } from "../proof-card/BattleProofNav";
import { useBattleMusicFixture } from "../hooks/useBattleMusicFixture";
import { useBattleSound } from "../hooks/useBattleSound";
import { useBattleScore } from "../hooks/useBattleScore";
import { promotedEntriesDueAtPlayhead } from "../lib/battle-normalized-music-fixture";
import { BattleMusicSchedulePanel } from "./BattleMusicSchedulePanel";
import "../proof-card/battle-proof-card.css";
import "./battle-music.css";

export function BattleMusicRoute() {
	const { viewModel, error, loading } = useBattleMusicFixture();
	const { arm, getContext, enabled } = useBattleSound();
	const score = useBattleScore(getContext);
	const [playheadSeconds, setPlayheadSeconds] = useState(0);
	const [activeMusicId, setActiveMusicId] = useState<string | null>(null);
	const [playbackNote, setPlaybackNote] = useState(
		"Playback status: idle — no speaker-output claim.",
	);
	const firedRef = useRef(new Set<string>());

	const maxSeconds = useMemo(() => {
		if (!viewModel?.promotedEntries.length) return 120;
		return Math.max(30, Math.max(...viewModel.promotedEntries.map((entry) => entry.atSeconds)) + 8);
	}, [viewModel]);

	useEffect(() => {
		firedRef.current = new Set();
		setPlayheadSeconds(0);
		setActiveMusicId(null);
		setPlaybackNote("Playback status: idle — no speaker-output claim.");
		score.stopAll();
	}, [viewModel?.fixtureId, score.stopAll]);

	const seek = useCallback((seconds: number) => {
		const next = Math.max(0, Math.min(maxSeconds, seconds));
		setPlayheadSeconds(next);
		for (const id of [...firedRef.current]) {
			const entry = viewModel?.promotedEntries.find((item) => item.id === id);
			if (entry && entry.atSeconds > next + 0.001) firedRef.current.delete(id);
		}
	}, [maxSeconds, viewModel?.promotedEntries]);

	const playDue = useCallback(async () => {
		if (!viewModel) return;
		arm();
		const due = promotedEntriesDueAtPlayhead(viewModel, playheadSeconds, firedRef.current);
		if (!due.length) {
			setPlaybackNote(`Playback status: armed at t=${playheadSeconds.toFixed(2)}s — no new due promoted entries. Speaker output unproven.`);
			return;
		}
		for (const entry of due) {
			firedRef.current.add(entry.id);
			await score.playPromotedUrl(entry.oggUrl, {
				loop: entry.loop,
				asLoop: entry.loop || entry.channel === "background",
				label: entry.musicId,
			});
			setActiveMusicId(entry.musicId);
			setPlaybackNote(
				`Playback status: browser decode requested for ${entry.musicId} (promoted). Decode≠heard; speaker output unproven.`,
			);
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
		<div className="battle-proof-card battle-music-route h-full overflow-auto p-4" data-qid="battle:music:route">
			<BattleProofNav />
			<div className="mx-auto mt-3 max-w-[1100px] space-y-3">
				<header>
					<h1 className="text-lg font-black uppercase tracking-[0.08em] text-slate-100">Battle Music Schedule</h1>
					<p className="text-sm text-slate-400">
						Receipt-backed promoted playback only. Music never authorizes Battle truth. Actor-focus previews stay outside this schedule.
					</p>
					<div className="mt-1 text-[11px] text-slate-500" data-qid="battle:music:route-meta">
						{viewModel.route} · mocked:false · composer_live:false · speaker_output:unproven
					</div>
				</header>
				<BattleMusicSchedulePanel
					model={viewModel}
					playheadSeconds={playheadSeconds}
					maxSeconds={maxSeconds}
					armed={enabled}
					activeMusicId={activeMusicId}
					playbackNote={playbackNote}
					onArm={() => {
						arm();
						void playDue();
					}}
					onPlayDue={() => void playDue()}
					onStop={() => {
						score.stopAll();
						setActiveMusicId(null);
						setPlaybackNote("Playback status: stopped — no speaker-output claim.");
					}}
					onSeek={seek}
					onSeekSpawn={() => {
						const motif = viewModel.promotedEntries.find((entry) => entry.musicId.startsWith("motif:"));
						if (motif) seek(motif.atSeconds);
					}}
					onResetPlayhead={() => seek(0)}
				/>
			</div>
		</div>
	);
}
