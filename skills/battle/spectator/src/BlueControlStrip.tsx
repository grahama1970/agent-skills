import type { BluePatchAction } from "./lib/battle-types";
import { BATTLE_LANE_LABEL_PX } from "./lib/layout-constants";
import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { Icons } from "./battle-icons";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { isBattleReceiptReplayView } from "./lib/battle-receipt-replay";
import { formatReceiptCount } from "./lib/format-receipt-score";
import { cn } from "./lib/utils";
import { mockupClockFromTrackPct, mockupBlueStripStats } from "./lib/mockup-design-fixture";
import { clusterBlueMarkers, type BlueStripMarker } from "./lib/battle-blue-strip-markers";

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
  const receiptView = isBattleReceiptReplayView();
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const stats = mockupBlueStripStats();
  const interventions = interventionCount ?? (designView ? stats.interventions : receiptView ? undefined : actions.length);
  const blocks = blockCount ?? (designView ? stats.blocks : receiptView ? undefined : undefined);
  const interventionLabel = formatReceiptCount(interventions);
  const blockLabel = formatReceiptCount(blocks);
  const rawMarkers: BlueStripMarker[] = designView
    ? MOCKUP_PATCH_LABELS.map((label, index) => ({
        id: actions[index]?.id ?? `mockup-patch-${index}`,
        label,
        left: MOCKUP_PATCH_LEFT[index],
        clock: MOCKUP_PATCH_CLOCKS[index],
      }))
    : actions.map((action) => ({
        id: action.id,
        label: action.name,
        left: action.xStart,
        clock: patchClock(action.xStart, allottedSeconds),
        detailLabel: `${action.name} · ${action.agentName} · ${action.receiptId}`,
      }));
  const markers = designView
    ? rawMarkers.map((marker) => ({ ...marker, stacked: 1, title: marker.label }))
    : clusterBlueMarkers(rawMarkers);

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
            Interventions <strong>{interventionLabel}</strong> · Blocks <strong>{blockLabel}</strong>
          </div>
        </div>
        <div className="grid" style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px minmax(0, 1fr)` }}>
          <div aria-hidden="true" />
          <div className="bluePatchRow">
            {markers.map(({ id, label, left, clock }) => (
              <div
                key={id}
                className="bluePatch"
                style={{ left: leftPxFromLaneX(left) }}
                title={label}
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
          Interventions <strong className="text-battle-blue">{interventionLabel}</strong> · Blocks <strong className="text-battle-blue">{blockLabel}</strong>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: `${BATTLE_LANE_LABEL_PX}px minmax(0, 1fr)` }}>
        <div aria-hidden="true" />
        <div className="battle-blue-patch-row relative h-[34px] overflow-hidden border-b border-battle-blue/[.06] bg-[rgba(4,10,18,.35)]" data-qid="battle:blue-strip:patches">
          <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-battle-blue/35" />
          {!designView && markers.length === 0 ? (
            <div className="absolute inset-0 grid place-items-center text-[10px] font-semibold text-slate-500">Blue patch actions not emitted</div>
          ) : null}
          {markers.map(({ id, left, clock, title, stacked }) => (
            <div key={id} className="battle-blue-patch absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2" style={{ left: leftPxFromLaneX(left) }} title={title} data-qid="battle:blue-strip:patch" data-stacked={stacked}>
              <Icons.Shield className="h-3.5 w-3.5 text-battle-blue" />
              <span className="font-mono text-[8px] leading-none text-slate-500">{stacked > 1 ? `${clock} · +${stacked - 1}` : clock}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
