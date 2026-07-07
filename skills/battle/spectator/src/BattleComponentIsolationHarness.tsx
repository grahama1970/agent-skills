import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import "./battle-race.css";
import { BattleHeader } from "./BattleHeader";
import { BattleTimelineAxis } from "./BattleTimelineAxis";
import { BattlePlayheadCursor } from "./BattlePlayheadCursor";
import { BattleTimelineProvider, useBattleTimelineScale } from "./BattleTimelineProvider";
import { BlueControlStrip } from "./BlueControlStrip";
import { LaneRow } from "./LaneRow";
import { LaneEventMarker } from "./LaneEventMarker";
import { LaneEventLabel } from "./LaneEventLabel";
import { SpectatorRail } from "./SpectatorRail";
import { MockupAgentDetailPane } from "./MockupAgentDetailPane";
import { RunnerHud } from "./RunnerHud";
import { CampaignPulse } from "./CampaignPulse";
import { TimelineOverview } from "./TimelineOverview";
import { BattleToolbar, type BattleFilter } from "./BattleToolbar";
import { BattleLineageFlow } from "./BattleLineageFlow";
import { mockupDesignLanes } from "./lib/battle-mockup-lanes";
import {
  mockupAllottedSeconds,
  mockupPlayheadSeconds,
  mockupTimelineTicks,
} from "./lib/mockup-design-fixture";
import { battleEvents, bluePatchActions } from "./lib/battle-data";
import { layoutLaneEvents } from "./lib/layout-lane-events";

const ALLOTTED = mockupAllottedSeconds();
const SAMPLE_LANE = mockupDesignLanes.find((lane) => lane.id === "payload-857-A") ?? mockupDesignLanes[0];
const LINEAGE_LANES = mockupDesignLanes.slice(0, 4);

function IsolationPanel({
  id,
  title,
  children,
  className = "",
}: {
  id: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      data-isolation-component={id}
      data-testid={`isolation-${id}`}
      className={`overflow-hidden rounded-xl border border-white/10 bg-black/25 ${className}`}
    >
      <header className="border-b border-white/10 px-3 py-2 text-[10px] font-black uppercase tracking-[0.14em] text-cyan-300">
        {title}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

function TimelineCanvas({ width = 1100, children }: { width?: number; children: ReactNode }) {
  const { setTrackRef } = useBattleTimelineScale();

  return (
    <div
      ref={setTrackRef}
      style={{ width }}
      className="relative overflow-hidden rounded-lg border border-white/10 bg-battle-panel/45"
      data-battle-timeline-track
    >
      {children}
    </div>
  );
}

function TimelineShell({ children, width = 1100 }: { children: ReactNode; width?: number }) {
  return (
    <BattleTimelineProvider allottedSeconds={ALLOTTED}>
      <TimelineCanvas width={width}>{children}</TimelineCanvas>
    </BattleTimelineProvider>
  );
}

function HeaderIsolation() {
  return (
    <IsolationPanel id="battle-header" title="BattleHeader">
      <BattleHeader events={battleEvents} onTestSound={() => undefined} onSelectActor={() => undefined} onOpenJsonl={() => undefined} />
    </IsolationPanel>
  );
}

function SpectatorRailIsolation() {
  return (
    <IsolationPanel id="spectator-rail" title="SpectatorRail" className="max-w-[360px]">
      <SpectatorRail leaderboard={[]} onSelect={() => undefined} />
    </IsolationPanel>
  );
}

function AgentDetailIsolation() {
  return (
    <IsolationPanel id="mockup-agent-detail-pane" title="MockupAgentDetailPane" className="max-w-[380px]">
      <div className="h-[520px]">
        <MockupAgentDetailPane lane={SAMPLE_LANE} />
      </div>
    </IsolationPanel>
  );
}

function TimelineAxisIsolation() {
  return (
    <IsolationPanel id="battle-timeline-axis" title="BattleTimelineAxis">
      <TimelineShell>
        <BattleTimelineAxis ticks={mockupTimelineTicks()} allottedSeconds={ALLOTTED} />
      </TimelineShell>
    </IsolationPanel>
  );
}

function PlayheadIsolation() {
  return (
    <IsolationPanel id="battle-playhead-cursor" title="BattlePlayheadCursor">
      <TimelineShell>
        <div className="relative h-24">
          <BattlePlayheadCursor playheadSeconds={mockupPlayheadSeconds()} />
        </div>
      </TimelineShell>
    </IsolationPanel>
  );
}

function BlueStripIsolation() {
  return (
    <IsolationPanel id="blue-control-strip" title="BlueControlStrip">
      <TimelineShell>
        <BlueControlStrip actions={bluePatchActions} allottedSeconds={ALLOTTED} interventionCount={3} blockCount={2} />
      </TimelineShell>
    </IsolationPanel>
  );
}

function LaneRowIsolation() {
  return (
    <IsolationPanel id="lane-row" title="LaneRow">
      <TimelineShell>
        <LaneRow
          lane={SAMPLE_LANE}
          hasChildren={false}
          isSelected
          isDimmed={false}
          onSelect={() => undefined}
          allottedSeconds={ALLOTTED}
        />
      </TimelineShell>
    </IsolationPanel>
  );
}

function LaneMarkerIsolation() {
  const event = SAMPLE_LANE.events.find((item) => item.kind === "fastest_crash") ?? SAMPLE_LANE.events[0];
  return (
    <IsolationPanel id="lane-event-marker" title="LaneEventMarker">
      <TimelineShell width={700}>
        <div className="relative h-20">
          <LaneEventMarker
            event={event}
            laneId={SAMPLE_LANE.id}
            laneName={SAMPLE_LANE.name}
            index={0}
            allottedSeconds={ALLOTTED}
            onSelect={() => undefined}
          />
        </div>
      </TimelineShell>
    </IsolationPanel>
  );
}

function LaneLabelIsolation() {
  const laidOut = layoutLaneEvents(SAMPLE_LANE.events);
  const above = laidOut.find((event) => event.labelBand === "above");
  const below = laidOut.find((event) => event.labelBand === "below");
  return (
    <IsolationPanel id="lane-event-label" title="LaneEventLabel">
      <TimelineShell width={700}>
        <div className="relative h-24">
          {above ? <LaneEventLabel event={above} band="above" allottedSeconds={ALLOTTED} /> : null}
          {below ? <LaneEventLabel event={below} band="below" allottedSeconds={ALLOTTED} /> : null}
        </div>
      </TimelineShell>
    </IsolationPanel>
  );
}

function RunnerHudIsolation() {
  return (
    <IsolationPanel id="runner-hud" title="RunnerHud" className="max-w-[180px]">
      <div className="flex items-center justify-center py-6">
        <RunnerHud state="retry" verb="mutating payload" selected />
      </div>
    </IsolationPanel>
  );
}

function CampaignPulseIsolation() {
  return (
    <IsolationPanel id="campaign-pulse" title="CampaignPulse">
      <CampaignPulse />
    </IsolationPanel>
  );
}

function TimelineOverviewIsolation() {
  const marks = useMemo(
    () => [
      { id: "m1", leftPct: 18, tone: "blocked" as const, title: "spawn" },
      { id: "m2", leftPct: 62, tone: "crash" as const, title: "crash" },
    ],
    []
  );
  return (
    <IsolationPanel id="timeline-overview" title="TimelineOverview">
      <TimelineOverview marks={marks} viewportStyle={{ left: 12, width: 48 }} showScrollHint />
    </IsolationPanel>
  );
}

function ToolbarIsolation() {
  const [mode, setMode] = useState("spectator");
  const [filter, setFilter] = useState<BattleFilter>("all");
  const [query, setQuery] = useState("");
  return (
    <IsolationPanel id="battle-toolbar" title="BattleToolbar">
      <BattleToolbar mode={mode} setMode={setMode} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} />
    </IsolationPanel>
  );
}

function LineageFlowIsolation() {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const getRowRef = useCallback((id: string) => {
    return (node: HTMLDivElement | null) => {
      if (node) rowRefs.current.set(id, node);
      else rowRefs.current.delete(id);
    };
  }, []);

  return (
    <IsolationPanel id="battle-lineage-flow" title="BattleLineageFlow">
      <TimelineShell>
        <div ref={containerRef} className="relative min-h-[480px]">
          {LINEAGE_LANES.map((lane) => (
            <LaneRow
              key={lane.id}
              ref={getRowRef(lane.id)}
              lane={lane}
              hasChildren={Boolean(lane.children?.length)}
              isChild={lane.id.includes("-")}
              isSelected={lane.id === SAMPLE_LANE.id}
              isDimmed={false}
              onSelect={() => undefined}
              allottedSeconds={ALLOTTED}
            />
          ))}
          <BattleLineageFlow
            lanes={mockupDesignLanes}
            visibleLaneIds={LINEAGE_LANES.map((lane) => lane.id)}
            collapsed={new Set()}
            containerRef={containerRef}
            rowRefs={rowRefs}
            layoutKey="isolation"
          />
        </div>
      </TimelineShell>
    </IsolationPanel>
  );
}

export function BattleComponentIsolationHarness() {
  return (
    <div className="grid gap-4 p-4 text-slate-100" data-testid="battle-component-isolation-harness">
      <header>
        <h1 className="text-lg font-black">Battle Component Isolation Harness</h1>
        <p className="text-sm text-slate-400">Each panel mounts one production React component with mockup fixture data.</p>
      </header>
      <div className="grid gap-4 xl:grid-cols-2">
        <HeaderIsolation />
        <SpectatorRailIsolation />
        <AgentDetailIsolation />
        <ToolbarIsolation />
        <CampaignPulseIsolation />
        <TimelineOverviewIsolation />
        <TimelineAxisIsolation />
        <PlayheadIsolation />
        <BlueStripIsolation />
        <LaneRowIsolation />
        <LaneMarkerIsolation />
        <LaneLabelIsolation />
        <RunnerHudIsolation />
      </div>
      <LineageFlowIsolation />
    </div>
  );
}

export function isBattleComponentIsolationTest() {
  if (typeof window === "undefined") return false;
  const raw = window.location.hash.replace(/^#/, "").split("?")[0];
  const [project, ...rest] = raw.split("/");
  return project === "battle" && rest.includes("isolation");
}
