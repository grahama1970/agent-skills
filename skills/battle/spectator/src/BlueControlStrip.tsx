import type { BluePatchAction } from "./lib/battle-types";
import { BATTLE_LANE_LABEL_PX } from "./lib/layout-constants";
import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { Icons } from "./battle-icons";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { cn } from "./lib/utils";
import { mockupClockFromTrackPct, mockupBlueStripStats } from "./lib/mockup-design-fixture";

type Props = {
  actions: BluePatchAction[];
  allottedSeconds: number;
  interventionCount?: number;
  blockCount?: number;
};

const MOCKUP_PATCH_LABELS = ["CanonGuard v1", "PathSanity Patch", "Boundary Shield"];
const MOCKUP_PATCH_LEFT = [18, 42, 68];
const MOCKUP_PATCH_CLOCKS = ["10:06:12", "10:08:47", "10:11:23"];

function patchClock(xStart: number, allottedSeconds: number) {
  const total = Math.max(0, Math.floor((xStart / 100) * allottedSeconds));
  const min = Math.floor(total / 60).toString().padStart(2, "0");
  const sec = (total % 60).toString().padStart(2, "0");
  return `${min}:${sec}`;
}

export function BlueControlStrip({ actions, allottedSeconds, interventionCount, blockCount }: Props) {
  const designView = isBattleDesignView();
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const stats = mockupBlueStripStats();
  const interventions = interventionCount ?? (designView ? stats.interventions : actions.length);
  const blocks = blockCount ?? (designView ? stats.blocks : 2);
  const markers = MOCKUP_PATCH_LABELS.map((label, index) => ({
    id: actions[index]?.id ?? `mockup-patch-${index}`,
    label,
    left: MOCKUP_PATCH_LEFT[index],
    clock: designView ? MOCKUP_PATCH_CLOCKS[index] : patchClock(MOCKUP_PATCH_LEFT[index], allottedSeconds),
    detail: actions[index],
  }));

  if (designView) {
    return (
      <section className="blueStripCenter battle-blue-strip design">
        <div className="blueStripLabel">
          <div className="stripIconBox">
            <Icons.Shield className="h-4 w-4" />
          </div>
          <div>
            <div className="stripTitle">Blue Team Control Strip</div>
            <div className="stripSub">Active Patches &amp; Defensive Actions</div>
          </div>
          <div className="blueStat">
            Interventions <strong>{interventions}</strong> · Blocks <strong>{blocks}</strong>
          </div>
        </div>
        <div className="grid" style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px minmax(0, 1fr)` }}>
          <div aria-hidden="true" />
          <div className="bluePatchRow">
            {markers.map(({ id, label, left, clock, detail }) => (
              <div
                key={id}
                className="bluePatch"
                style={{ left: leftPxFromLaneX(left) }}
                title={detail ? `${label} · ${detail.agentName} · ${detail.receiptId}` : label}
              >
                <Icons.Shield className="h-3.5 w-3.5" />
                <span>{label}</span>
                <span className="bpSub">{clock}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="battle-blue-strip shrink-0 border-b border-battle-blue/10 bg-gradient-to-r from-[rgba(8,24,48,.85)] to-[rgba(4,12,24,.75)]">
      <div className="battle-blue-strip-label grid items-center gap-3 px-3 py-2" style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px minmax(0, 1fr) auto` }}>
        <div className="stripIconBox shrink-0">
          <Icons.Shield className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="text-[11px] font-black uppercase tracking-[0.08em] text-battle-blue">Blue Team Control Strip</div>
          <div className="mt-0.5 truncate text-[11px] font-semibold text-slate-500">Active Patches &amp; Defensive Actions</div>
        </div>
        <div className="battle-blue-strip-stat whitespace-nowrap text-[11px] font-semibold text-slate-500">
          Interventions <strong className="text-battle-blue">{interventions}</strong> · Blocks <strong className="text-battle-blue">{blocks}</strong>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px minmax(0, 1fr)` }}>
        <div aria-hidden="true" />
        <div className="battle-blue-patch-row relative h-[34px] border-b border-battle-blue/[.06] bg-[rgba(4,10,18,.35)]">
          <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-battle-blue/35" />
          {markers.map(({ id, label, left, clock, detail }) => (
            <div key={id} className="battle-blue-patch absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: leftPxFromLaneX(left) }} title={detail ? `${label} · ${detail.agentName}` : label}>
              <Icons.Shield className="h-3.5 w-3.5 text-battle-blue" />
              <span className="max-w-[112px] truncate text-[8.5px] font-bold text-battle-blue">{label}</span>
              <span className="font-mono text-[8px] text-slate-500">{clock}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
