import type { TimelineOverviewMark } from "./lib/timeline-playback";
import { BATTLE_LANE_LABEL_PX } from "./lib/layout-constants";

type Props = {
  marks: TimelineOverviewMark[];
  viewportStyle: { left: number; width: number };
  showScrollHint: boolean;
  designView?: boolean;
  onScrub?: (event: React.MouseEvent<HTMLElement>) => void;
};

export function TimelineOverview({ marks, viewportStyle, showScrollHint, designView = false, onScrub }: Props) {
  if (designView) {
    return (
      <div
        className="battle-mockup-overview timelineOverview"
        style={{ ["--battle-label-w" as string]: `${BATTLE_LANE_LABEL_PX}px` }}
      >
        <div className="overviewSpacer" aria-hidden="true" />
        <div className="overviewTrackWrap" onClick={onScrub} role={onScrub ? "presentation" : undefined}>
          <div className="overviewTrack">
            <div
              aria-hidden="true"
              className="overviewViewport"
              style={{ left: viewportStyle.left, width: viewportStyle.width }}
            />
            {marks.map((mark) => (
              <span
                key={mark.id}
                title={mark.title}
                className={`overviewMark ${mark.tone} battle-overview-mark battle-overview-mark-${mark.tone}`}
                style={{ left: `${mark.leftPct}%` }}
              />
            ))}
          </div>
        </div>
        <div className={`scrollHint${showScrollHint ? "" : " hidden"}`}>More outcomes →</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[28px] items-center gap-3 border-b border-white/10 bg-black/20 px-4 py-1.5">
      <div className="shrink-0 text-[10px] font-black uppercase tracking-[.1em] text-slate-500" style={{ width: 218 }}>
        Overview
      </div>
      <div className="relative min-w-0 flex-1" onClick={onScrub} role={onScrub ? "presentation" : undefined}>
        <div className="relative h-1.5 rounded-full border border-battle-cyan/15 bg-battle-cyan/10">
          <div
            aria-hidden="true"
            className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full border border-battle-cyan/35 bg-battle-cyan/20 shadow-blueGlow"
            style={{ left: viewportStyle.left, width: viewportStyle.width }}
          />
          {marks.map((mark) => (
            <span
              key={mark.id}
              title={mark.title}
              className={`battle-overview-mark battle-overview-mark-${mark.tone}`}
              style={{ left: `${mark.leftPct}%` }}
            />
          ))}
        </div>
      </div>
      <div className={`shrink-0 text-[10px] font-bold uppercase tracking-[.08em] text-battle-cyan/80 ${showScrollHint ? "" : "invisible"}`}>
        More outcomes →
      </div>
    </div>
  );
}
