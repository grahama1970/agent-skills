import { useBattleTimelineScale } from "./BattleTimelineProvider";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { cn } from "./lib/utils";

type Props = {
  playheadSeconds: number;
};

export function BattlePlayheadCursor({ playheadSeconds }: Props) {
  const designView = isBattleDesignView();
  const { leftPxFromSeconds } = useBattleTimelineScale();
  const left = leftPxFromSeconds(playheadSeconds);

  return (
    <div
      className={cn("battle-playhead pointer-events-none absolute inset-y-0 z-40", designView && "playhead")}
      style={{ left: `${left}px` }}
      data-capability-playhead
    >
      <div className={cn("battle-playhead-line", designView && "hidden")} />
    </div>
  );
}
