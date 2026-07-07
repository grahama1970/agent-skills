import { forwardRef } from "react";
import { motion } from "motion/react";
import { Badge } from "./ui/badge";
import type { BlueFinisherState, Lane } from "./lib/battle-types";
import { cn } from "./lib/utils";
import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { Icons } from "./battle-icons";
import { LaneEventMarker } from "./LaneEventMarker";
import { RunnerHud } from "./RunnerHud";
import { layoutLaneEvents } from "./lib/layout-lane-events";
import { LaneEventLabel } from "./LaneEventLabel";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { partitionMockupLaneEvents } from "./lib/mockup-lane-partition";

type Props = {
  lane: Lane;
  hasChildren?: boolean;
  isCollapsed?: boolean;
  isChild?: boolean;
  isSelected: boolean;
  isDimmed: boolean;
  activeFinisher?: BlueFinisherState | null;
  onSelect: (id: string) => void;
  onToggleCollapse?: () => void;
  allottedSeconds: number;
  hideTrack?: boolean;
};

export const LaneRow = forwardRef<HTMLDivElement, Props>(function LaneRow(
  { lane, hasChildren = false, isCollapsed = false, isChild = false, isSelected, isDimmed, activeFinisher, onSelect, onToggleCollapse, allottedSeconds, hideTrack = false },
  ref
) {
  const designView = isBattleDesignView();
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const displayName = lane.name.replace(/\s+red-\d+$/i, "");
  const trackLeft = leftPxFromLaneX(lane.xStart);
  const trackRight = leftPxFromLaneX(lane.xEnd);
  const trackWidthPx = Math.max(8, trackRight - trackLeft);

  if (designView) {
    const { top, above, icons, bottom } = partitionMockupLaneEvents(lane);
    const chev = hasChildren ? (isCollapsed ? "›" : "⌄") : isChild ? "" : "›";

    return (
      <div
        ref={ref}
        data-lane-row
        data-lane-id={lane.id}
        data-qid={`battle:lane:${lane.id}`}
        data-qs-action="BATTLE_LANE_SELECT"
        title={`Select lane ${lane.name}`}
        role="button"
        tabIndex={0}
        className={cn(
          "row",
          isChild ? "child" : "root",
          lane.lineColor === "purple" && "purple",
          isChild && "childIndent",
          isSelected && "selected",
          isDimmed && "opacity-70",
          hideTrack && "pixiLabelsOnly",
          "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
        )}
        onClick={() => onSelect(lane.id)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(lane.id);
          }
        }}
      >
        <div className="labelCell">
          {hasChildren ? (
            <span
              role="button"
              tabIndex={0}
              className="chev"
              data-qid={`battle:lane:collapse:${lane.id}`}
              data-qs-action="BATTLE_LANE_COLLAPSE"
              title={isCollapsed ? `Expand child lanes for ${lane.name}` : `Collapse child lanes for ${lane.name}`}
              onClick={(event) => {
                event.stopPropagation();
                onToggleCollapse?.();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  event.stopPropagation();
                  onToggleCollapse?.();
                }
              }}
            >
              {chev}
            </span>
          ) : (
            <div className="chev" aria-hidden="true">{chev}</div>
          )}
          <div className="laneIcon">
            {isChild ? <Icons.GitBranch className="h-3.5 w-3.5" /> : <Icons.Bug className="h-3.5 w-3.5" />}
          </div>
          <div className="labelText min-w-0">
            <div className="name">{displayName}</div>
            <div className="payload">{lane.payloadId}</div>
          </div>
          <span className={cn("gen", lane.generation > 1 && "g2")}>GEN {lane.generation}</span>
        </div>
        <div className="track" data-lane-track>
          <div className="trackGrid" aria-hidden="true" />
          <div className="laneTop">
            {top.map((event) => (
              <LaneEventLabel key={event.id} event={event} band="top" allottedSeconds={allottedSeconds} />
            ))}
          </div>
          <div className="laneMidAbove">
            {above.map((event) => (
              <LaneEventLabel key={event.id} event={event} band="above" allottedSeconds={allottedSeconds} />
            ))}
          </div>
          <div className="laneCenter">
            <div className={cn("line", lane.lineColor)} style={{ left: trackLeft, width: trackWidthPx }} />
            {icons.map((event, index) => (
              <LaneEventMarker key={event.id} event={event} laneId={lane.id} laneName={lane.name} index={index} allottedSeconds={allottedSeconds} onSelect={onSelect} />
            ))}
          </div>
          <div className="laneBottom">
            {bottom.map((event) => (
              <LaneEventLabel key={event.id} event={event} band="below" allottedSeconds={allottedSeconds} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const lineClass = lane.lineColor === "green" ? "battle-line-green" : lane.lineColor === "purple" ? "battle-line-purple" : "battle-line-red";
  const terminalVariant = lane.terminal === "blocked" ? "blue" : lane.terminal === "none" ? "yellow" : "green";
  const isActiveFinisherTarget = activeFinisher?.laneId === lane.id;
  const workerSuffix = lane.name === displayName ? null : lane.name.slice(displayName.length).trim();
  const laidOut = layoutLaneEvents(lane.events.filter((event) => !isChild || event.x >= lane.xStart - 1), { flipBands: isChild });
  const icons = laidOut.filter((event) => event.labelBand === "none");
  const above = laidOut.filter((event) => event.labelBand === "above");
  const below = laidOut.filter((event) => event.labelBand === "below");
  const runnerCollides = icons.some((event) => Math.abs(event.x - lane.runnerX) < 4);

  return (
    <motion.div
      ref={ref}
      data-lane-row
      data-lane-id={lane.id}
      layout
      className={cn(
        "relative grid min-h-[108px] border-b border-white/[.055] transition-colors",
        isSelected && "bg-battle-green/7 ring-1 ring-inset ring-battle-green/25",
        isActiveFinisherTarget && "bg-battle-blue/10",
        isDimmed && "opacity-70"
      )}
    >
      <div
        className={cn(
          "absolute top-[18px] z-30 flex min-h-[76px] items-center gap-2",
          isChild ? "left-[92px]" : "left-4",
        )}
      >
        <button
          type="button"
          data-qid={`battle:lane:${lane.id}`}
          data-qs-action="BATTLE_LANE_SELECT"
          title={`Select receipt-backed lane ${lane.name}`}
          onClick={() => onSelect(lane.id)}
          className={cn(
            "flex min-h-[76px] flex-1 items-center gap-2 rounded-xl border px-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40",
            "border-battle-red/30 bg-battle-panel/95 shadow-acrylic hover:bg-white/[.045]",
            isSelected && "border-battle-green/35 bg-battle-green/10"
          )}
        >
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-battle-red/55 bg-battle-panel2 text-battle-red shadow-acrylic">
            <Icons.Bug className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <div className="truncate text-sm font-black text-white">{displayName}</div>
              <Badge variant={terminalVariant} className="shrink-0">{lane.terminal === "none" ? "ACTIVE" : lane.terminal}</Badge>
            </div>
            <div className="mt-0.5 truncate text-[11px] font-medium text-slate-500">{workerSuffix ? `${workerSuffix} · ${lane.payloadId}` : lane.payloadId}</div>
            <div className="mt-1 flex min-w-0 flex-wrap gap-1.5">
              <Badge variant="green">GEN {lane.generation}</Badge>
            </div>
          </div>
        </button>
        {hasChildren ? (
          <button
            type="button"
            data-qid={`battle:lane:collapse:${lane.id}`}
            data-qs-action="BATTLE_LANE_COLLAPSE"
            title={isCollapsed ? `Expand child lanes for ${lane.name}` : `Collapse child lanes for ${lane.name}`}
            className="grid h-11 min-h-11 w-11 min-w-11 shrink-0 place-items-center rounded-md border border-white/10 bg-black/20 text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
            onClick={() => onToggleCollapse?.()}
          >
            <Icons.ChevronDown className={cn("h-4 w-4 transition-transform", isCollapsed && "-rotate-90")} />
          </button>
        ) : null}
      </div>

      <div
        role="button"
        tabIndex={0}
        data-qid={`battle:track:${lane.id}`}
        data-qs-action="BATTLE_LANE_SELECT"
        title={`Select timeline track for ${lane.name}`}
        onClick={() => onSelect(lane.id)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(lane.id);
          }
        }}
        data-lane-track
        className="battle-track-grid relative block min-h-[108px] w-full cursor-pointer overflow-visible text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
      >
        <div className="battle-lane-band battle-lane-band-above pointer-events-none absolute inset-x-0 top-[14px] h-4">
          {above.map((event) => (
            <LaneEventLabel key={event.id} event={event} band="above" allottedSeconds={allottedSeconds} />
          ))}
        </div>
        <div className="battle-lane-band battle-lane-band-center absolute inset-x-0 top-1/2 h-8 -translate-y-1/2">
          <div className={cn("absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full", lineClass)} style={{ left: trackLeft, width: trackWidthPx }} />
          {icons.map((event, index) => (
            <LaneEventMarker key={event.id} event={event} laneId={lane.id} laneName={lane.name} index={index} allottedSeconds={allottedSeconds} onSelect={onSelect} />
          ))}
        </div>
        <div className="battle-lane-band battle-lane-band-below pointer-events-none absolute inset-x-0 bottom-[14px] h-4">
          {below.map((event) => (
            <LaneEventLabel key={event.id} event={event} band="below" allottedSeconds={allottedSeconds} />
          ))}
        </div>
        <div className={cn("absolute z-30 -translate-x-1/2", runnerCollides ? "top-[34%]" : "top-1/2 -translate-y-1/2")} style={{ left: leftPxFromLaneX(lane.runnerX) }}>
          <RunnerHud state={lane.runnerState} verb={isSelected ? lane.runnerVerb : undefined} selected={isSelected} />
        </div>
      </div>
    </motion.div>
  );
});
