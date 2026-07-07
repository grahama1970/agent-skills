import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { cn } from "./lib/utils";
import { Icons } from "./battle-icons";

type Tick = { x: number; label: string };

type Props = {
  ticks: Tick[];
  allottedSeconds: number;
};

const STAGES = [
  { label: "Research", Icon: Icons.Search },
  { label: "Payload", Icon: Icons.Code2 },
  { label: "Mutate", Icon: Icons.Dna },
  { label: "Retry", Icon: Icons.RefreshCw },
  { label: "Terminal", Icon: Icons.Terminal },
] as const;

export function BattleTimelineAxis({ ticks, allottedSeconds }: Props) {
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const designView = isBattleDesignView();

  if (designView) {
    return (
      <div className="axis battle-timeline-axis">
        <div className="axisCorner">TIME</div>
        <div className="axisTrack">
          <div className="ticks">
            {ticks.map((tick) => (
              <span key={tick.label} className="tick font-mono" style={{ left: leftPxFromLaneX(tick.x) }}>
                {tick.label}
              </span>
            ))}
          </div>
          <div className="stage">
            {STAGES.map(({ label, Icon }) => (
              <div key={label}>
                <Icon className="h-3 w-3 shrink-0" aria-hidden="true" /> {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="battle-timeline-axis battle-track-grid sticky top-0 z-30 h-9 border-b border-white/10 bg-[rgba(3,8,15,.82)] backdrop-blur-xl">
      <div className="relative">
        {ticks.map((tick) => (
          <div key={tick.label} className="absolute inset-y-0 -translate-x-1/2" style={{ left: leftPxFromLaneX(tick.x) }}>
            <div className="mt-1.5 font-mono text-[10px] font-semibold text-slate-500">{tick.label}</div>
            <div className="absolute bottom-0 left-1/2 h-2 w-px bg-white/15" />
          </div>
        ))}
      </div>
    </div>
  );
}
