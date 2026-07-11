import { useEffect, useMemo, useState } from "react";
import type { BattleRoundIntroViewModel } from "./lib/battle-round-intro";
import "./battle-genesis-intro.css";

type Props = {
	intro: BattleRoundIntroViewModel;
	audioPlaying: boolean;
	onStartArena: () => void;
	onSkip: () => void;
	onArmAudio: () => void;
	onStopAudio: () => void;
	autoAdvanceMs?: number;
};

export function BattleRoundStoryIntro({
	intro,
	audioPlaying,
	onStartArena,
	onSkip,
	onArmAudio,
	onStopAudio,
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
			data-qid="battle:intro"
			data-page={page.kind}
			data-provisional-gm={intro.provisionalGmRender ? "1" : "0"}
			aria-label="Battle Death Clock round intro"
		>
			<div className="battle-genesis-intro__inner">
				<div className="battle-genesis-intro__eyebrow" data-qid="battle:intro:eyebrow">
					{page.eyebrow}
				</div>
				<div className="battle-genesis-intro__lines" data-qid="battle:intro:lines">
					{page.lines.map((line) => (
						<p key={line} className="battle-genesis-intro__line">
							{line}
						</p>
					))}
				</div>
				{page.footer ? (
					<div className="battle-genesis-intro__footer" data-qid="battle:intro:footer">
						{page.footer}
					</div>
				) : null}
				<div className="battle-genesis-intro__controls">
					<button type="button" className="battle-genesis-intro__btn" data-qid="battle:intro:next" onClick={() => setPageIndex((value) => Math.min(value + 1, intro.pages.length - 1))}>
						Next
					</button>
					<button
						type="button"
						className="battle-genesis-intro__btn"
						data-qid="battle:intro:audio"
						onClick={() => (audioPlaying ? onStopAudio() : onArmAudio())}
					>
						{audioPlaying ? "Stop Overture" : "Play Death Clock"}
					</button>
					<button type="button" className="battle-genesis-intro__btn" data-qid="battle:intro:skip" onClick={onSkip}>
						Skip
					</button>
					<button
						type="button"
						className="battle-genesis-intro__btn"
						data-primary="1"
						data-qid="battle:intro:start"
						onClick={onStartArena}
					>
						Press Start
					</button>
				</div>
				<div className="battle-genesis-intro__meta">
					<span data-qid="battle:intro:page">{pageLabel}</span>
					<span data-qid="battle:intro:round">{intro.roundLabel}</span>
					<span data-qid="battle:intro:audio-url">{intro.audioUrl}</span>
					<span data-qid="battle:intro:style">{intro.graphicStyle}</span>
					<span data-qid="battle:intro:audio-state">{audioPlaying ? "playing" : "stopped"}</span>
					<span data-qid="battle:intro:provisional">{intro.provisionalGmRender ? "provisional_gm_render" : "final"}</span>
					<span data-qid="battle:intro:legacy-midi">{intro.legacyGenesisMidiUrl}</span>
					<span data-qid="battle:intro:legacy-selectable">{intro.legacyIntroSelectable ? "1" : "0"}</span>
				</div>
			</div>
		</section>
	);
}
