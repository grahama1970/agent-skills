import { useEffect, useMemo, useState } from "react";
import type { GenesisIntroViewModel } from "./lib/battle-genesis-intro";
import "./battle-genesis-intro.css";

type Props = {
	intro: GenesisIntroViewModel;
	midiPlaying: boolean;
	onStartArena: () => void;
	onSkip: () => void;
	onArmMidi: () => void;
	onStopMidi: () => void;
	autoAdvanceMs?: number;
};

export function BattleGenesisStoryIntro({
	intro,
	midiPlaying,
	onStartArena,
	onSkip,
	onArmMidi,
	onStopMidi,
	autoAdvanceMs = 2600,
}: Props) {
	const [pageIndex, setPageIndex] = useState(0);
	const page = intro.pages[Math.min(pageIndex, intro.pages.length - 1)]!;
	const isLast = pageIndex >= intro.pages.length - 1;

	useEffect(() => {
		if (isLast) return;
		const id = window.setTimeout(() => setPageIndex((value) => Math.min(value + 1, intro.pages.length - 1)), autoAdvanceMs);
		return () => window.clearTimeout(id);
	}, [autoAdvanceMs, intro.pages.length, isLast, pageIndex]);

	const pageLabel = useMemo(() => `${pageIndex + 1}/${intro.pages.length}`, [intro.pages.length, pageIndex]);

	return (
		<section
			className="battle-genesis-intro"
			data-qid="battle:genesis:intro"
			data-page={page.kind}
			aria-label="Genesis-style battle round intro"
		>
			<div className="battle-genesis-intro__inner">
				<div className="battle-genesis-intro__eyebrow" data-qid="battle:genesis:eyebrow">
					{page.eyebrow}
				</div>
				<div className="battle-genesis-intro__lines" data-qid="battle:genesis:lines">
					{page.lines.map((line) => (
						<p key={line} className="battle-genesis-intro__line">
							{line}
						</p>
					))}
				</div>
				{page.footer ? (
					<div className="battle-genesis-intro__footer" data-qid="battle:genesis:footer">
						{page.footer}
					</div>
				) : null}
				<div className="battle-genesis-intro__controls">
					<button type="button" className="battle-genesis-intro__btn" data-qid="battle:genesis:next" onClick={() => setPageIndex((value) => Math.min(value + 1, intro.pages.length - 1))}>
						Next
					</button>
					<button
						type="button"
						className="battle-genesis-intro__btn"
						data-qid="battle:genesis:midi"
						onClick={() => (midiPlaying ? onStopMidi() : onArmMidi())}
					>
						{midiPlaying ? "Stop MIDI" : "Play MIDI Intro"}
					</button>
					<button type="button" className="battle-genesis-intro__btn" data-qid="battle:genesis:skip" onClick={onSkip}>
						Skip
					</button>
					<button
						type="button"
						className="battle-genesis-intro__btn"
						data-primary="1"
						data-qid="battle:genesis:start"
						onClick={onStartArena}
					>
						Press Start
					</button>
				</div>
				<div className="battle-genesis-intro__meta">
					<span data-qid="battle:genesis:page">{pageLabel}</span>
					<span data-qid="battle:genesis:round">{intro.roundLabel}</span>
					<span data-qid="battle:genesis:midi-url">{intro.midiUrl}</span>
					<span data-qid="battle:genesis:style">{intro.graphicStyle}</span>
					<span data-qid="battle:genesis:midi-state">{midiPlaying ? "playing" : "stopped"}</span>
				</div>
			</div>
		</section>
	);
}
