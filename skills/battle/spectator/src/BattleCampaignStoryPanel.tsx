import type { CampaignStoryChapter, CampaignStoryViewModel } from "./lib/battle-campaign-story";

type Props = {
	story: CampaignStoryViewModel;
	activeChapter: CampaignStoryChapter | null;
	soundCaption: string | null;
	soundEnabled: boolean;
	reducedMotion: boolean;
	particles: boolean;
	onArmSound: () => void;
	onSelectChapter?: (chapter: CampaignStoryChapter) => void;
};

export function BattleCampaignStoryPanel({
	story,
	activeChapter,
	soundCaption,
	soundEnabled,
	reducedMotion,
	particles,
	onArmSound,
	onSelectChapter,
}: Props) {
	return (
		<section className="battle-campaign-story" data-qid="battle:campaign:banner" aria-label="Battle campaign storytelling">
			<div className="flex flex-wrap items-center gap-2">
				<span
					className="rounded border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-violet-100"
					data-qid="battle:campaign:banner:mode"
				>
					CAMPAIGN STORY
				</span>
				<span
					className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
					data-qid="battle:campaign:banner:mocked"
				>
					MOCKED: NO
				</span>
				<span
					className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100"
					data-qid="battle:campaign:banner:chapters"
				>
					CHAPTERS {story.chapterCount}
				</span>
				<span
					className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-amber-100"
					data-qid="battle:campaign:banner:no-victory"
				>
					NO VICTORY FROM STORY ALONE
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:campaign:particles">
					particles {particles ? "on" : "off"}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:campaign:reduced-motion">
					reduced motion {reducedMotion ? "on" : "off"}
				</span>
				<button
					type="button"
					className="rounded border border-white/20 bg-white/5 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-slate-100"
					data-qid="battle:campaign:sound-arm"
					onClick={onArmSound}
				>
					{soundEnabled ? "Sound armed" : "Arm sound"}
				</button>
			</div>

			<div className="mt-2 grid gap-1 text-[11px] text-slate-300 md:grid-cols-4" data-qid="battle:campaign:pulse">
				<div data-qid="battle:campaign:pulse:lineages">lineages {story.pulse.activeLineages}</div>
				<div data-qid="battle:campaign:pulse:present">genetic present {story.pulse.geneticPresent}</div>
				<div data-qid="battle:campaign:pulse:spawns">spawns {story.pulse.spawns}</div>
				<div data-qid="battle:campaign:pulse:abandoned">abandoned {story.pulse.abandonedBranches}</div>
				<div data-qid="battle:campaign:pulse:compile">compile-pass chapters {story.pulse.compilePassedChapters}</div>
				<div data-qid="battle:campaign:pulse:target">target-contact chapters {story.pulse.targetContactChapters}</div>
				<div data-qid="battle:campaign:pulse:not-emitted">not emitted {story.pulse.geneticNotEmitted}</div>
				<div data-qid="battle:campaign:fixture">fixture {story.fixtureId}</div>
			</div>

			<div className="mt-2 rounded-lg border border-white/10 bg-black/20 p-2" data-qid="battle:campaign:active-chapter">
				<div className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-500">Now</div>
				{activeChapter ? (
					<>
						<div className="text-sm font-black text-white" data-qid="battle:campaign:active-title">
							{activeChapter.seq}. {activeChapter.title}
						</div>
						<div className="text-xs text-slate-300" data-qid="battle:campaign:active-caption">
							{activeChapter.caption}
						</div>
						<div className="mt-1 text-[10px] uppercase tracking-[0.08em] text-slate-500" data-qid="battle:campaign:active-meta">
							t={activeChapter.atSeconds.toFixed(1)}s · {activeChapter.eventType} · cue {activeChapter.soundCue}
						</div>
					</>
				) : (
					<div className="text-xs text-slate-400" data-qid="battle:campaign:active-empty">
						Playhead before first genetic chapter.
					</div>
				)}
				{soundCaption ? (
					<div className="mt-2 rounded border border-sky-400/20 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-100" data-qid="battle:campaign:sound-caption">
						Sound caption: {soundCaption}
					</div>
				) : null}
			</div>

			<ol className="mt-2 flex gap-2 overflow-x-auto pb-1" data-qid="battle:campaign:chapters">
				{story.chapters.map((chapter) => {
					const active = activeChapter?.id === chapter.id;
					return (
						<li key={chapter.id}>
							<button
								type="button"
								className={
									active
										? "min-w-[150px] rounded-lg border border-violet-300/50 bg-violet-500/20 px-2 py-2 text-left"
										: "min-w-[150px] rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-left"
								}
								data-qid={`battle:campaign:chapter:${chapter.eventType}`}
								data-active={active ? "1" : "0"}
								onClick={() => onSelectChapter?.(chapter)}
							>
								<div className="text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">
									Ch {chapter.seq} · {chapter.atSeconds.toFixed(0)}s
								</div>
								<div className="text-xs font-bold text-slate-100">{chapter.title}</div>
								<div className="mt-1 line-clamp-2 text-[10px] text-slate-400">{chapter.caption}</div>
							</button>
						</li>
					);
				})}
			</ol>

			<div className="mt-2 grid gap-2 md:grid-cols-2" data-qid="battle:campaign:claim-boundary">
				<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2" data-qid="battle:campaign:claim-may">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80">May claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
						{story.claimBoundary.mayClaim.slice(0, 6).map((item) => (
							<li key={item}>{item.replace(/_/g, " ")}</li>
						))}
					</ul>
				</div>
				<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-2" data-qid="battle:campaign:claim-must-not">
					<div className="text-[10px] font-black uppercase tracking-[0.1em] text-rose-300/80">Must not claim</div>
					<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
						{story.claimBoundary.mustNotClaim.slice(0, 6).map((item) => (
							<li key={item}>{item.replace(/_/g, " ")}</li>
						))}
					</ul>
				</div>
			</div>
		</section>
	);
}
