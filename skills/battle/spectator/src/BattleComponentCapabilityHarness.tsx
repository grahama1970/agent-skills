import { useMemo } from "react";
import { mockupDesignLanes } from "./lib/battle-mockup-lanes";
import { mockupAllottedSeconds } from "./lib/mockup-design-fixture";
import { computeLineageLayout } from "./lib/layout-lineage-rails";
import { spawnBranchPath } from "./lib/spawn-branch-path";
import { BATTLE_LANE_LABEL_PX } from "./lib/layout-constants";
import { BattleTimelineProvider, useBattleTimelineScale } from "./BattleTimelineProvider";
import { laneXToMs } from "./lib/battle-timeline-scale";

const ALLOTTED = mockupAllottedSeconds();

function D3TimelineCapabilityPanel() {
  const lanes = mockupDesignLanes.slice(0, 4);

  return (
    <BattleTimelineProvider allottedSeconds={ALLOTTED}>
      <D3TimelineCapabilityCanvas lanes={lanes} />
    </BattleTimelineProvider>
  );
}

function D3TimelineCapabilityCanvas({ lanes }: { lanes: typeof mockupDesignLanes }) {
  const { leftPxFromLaneX, leftPxFromSeconds, trackWidth, setTrackRef } = useBattleTimelineScale();

  return (
    <div
      data-capability="d3-timeline"
      data-testid="d3-timeline-capability"
      className="relative h-[320px] overflow-hidden rounded-xl border border-white/10 bg-black/30"
    >
      <div
        ref={setTrackRef}
        className="relative h-full w-full"
        data-battle-timeline-track
        data-timeline-width={trackWidth}
      >
        <div className="sticky top-0 z-10 h-8 border-b border-white/10 bg-black/40">
          {[0, 50, 100].map((pct) => (
            <div
              key={pct}
              data-capability-tick={pct}
              className="absolute top-2 -translate-x-1/2 text-[10px] text-slate-400"
              style={{ left: leftPxFromLaneX(pct) }}
            >
              tick-{pct}
            </div>
          ))}
        </div>
        <div
          data-capability-playhead
          className="pointer-events-none absolute bottom-0 top-8 z-20 w-0.5 bg-cyan-400"
          style={{ left: leftPxFromSeconds(ALLOTTED * 0.8) }}
        />
        {lanes.map((lane) => (
          <div
            key={lane.id}
            data-capability-row={lane.id}
            className="grid border-b border-white/5"
            style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px 1fr` }}
          >
            <div className="truncate px-2 py-3 text-[10px] font-bold text-slate-300">{lane.name}</div>
            <div className="relative h-14" data-lane-track>
              <div
                data-capability-item={`${lane.id}:span`}
                data-capability-dragging="false"
                className="pointer-events-none absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-red-400"
                style={{
                  left: leftPxFromLaneX(lane.xStart),
                  width: Math.max(4, leftPxFromLaneX(lane.xEnd) - leftPxFromLaneX(lane.xStart)),
                }}
              />
              <div
                data-capability-item={`${lane.id}:handoff`}
                data-capability-dragging="false"
                className="pointer-events-none absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-yellow-300"
                style={{ left: leftPxFromLaneX(lane.xEnd * 0.9) }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function D3LineageCapabilityPanel() {
  const branches = useMemo(() => {
    const lanes = mockupDesignLanes;
    const rowHeight = 56;
    const trackLeft = BATTLE_LANE_LABEL_PX;
    const trackWidth = 900;
    const rowRects = lanes.map((lane, index) => ({
      id: lane.id,
      top: index * rowHeight,
      height: rowHeight,
      trackLeft,
      trackWidth,
    }));
    return computeLineageLayout({ lanes, rowRects, collapsed: new Set(), containerTop: 0 }).branches;
  }, []);

  return (
    <div
      data-capability="d3-lineage"
      data-testid="d3-lineage-capability"
      className="relative h-[320px] overflow-hidden rounded-xl border border-white/10 bg-black/30"
    >
      <svg className="h-full w-full" data-testid="battle-lineage-svg">
        {branches.map((branch) => (
          <path
            key={`${branch.parentId}->${branch.childId}`}
            data-capability-branch={`${branch.parentId}->${branch.childId}`}
            d={spawnBranchPath(branch)}
            className="battle-lineage-branch"
            fill="none"
            stroke="rgba(255,255,255,0.35)"
            strokeWidth={1}
          />
        ))}
      </svg>
      <div data-capability-branch-count={branches.length} className="sr-only" />
    </div>
  );
}

export function BattleComponentCapabilityHarness() {
  return (
    <div className="grid gap-4 p-4 text-slate-100" data-testid="battle-component-capability-harness">
      <header>
        <h1 className="text-lg font-black">Battle Component Capability Harness</h1>
        <p className="text-sm text-slate-400">
          Live environment tests for D3 timeline scale and SVG lineage paths against mockup lane data.
        </p>
      </header>
      <section>
        <h2 className="mb-2 text-xs font-black uppercase tracking-widest text-cyan-300">D3 time scale</h2>
        <D3TimelineCapabilityPanel />
      </section>
      <section>
        <h2 className="mb-2 text-xs font-black uppercase tracking-widest text-cyan-300">D3 lineage paths</h2>
        <D3LineageCapabilityPanel />
      </section>
    </div>
  );
}

export function isBattleComponentCapabilityTest() {
  if (typeof window === "undefined") return false;
  const raw = window.location.hash.replace(/^#/, "").split("?")[0];
  const [project, ...rest] = raw.split("/");
  return project === "battle" && rest.includes("component-test");
}

export { laneXToMs };
