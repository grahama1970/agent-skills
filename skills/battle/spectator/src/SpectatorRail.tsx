import { useMemo, useState } from "react";
import type { Lane, LeaderboardEntry } from "./lib/battle-types";
import { activeBattleFixture, battleLanesForView } from "./lib/battle-data";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { mockupAgentStatus, mockupRaceLeaders, mockupScoreboard } from "./lib/mockup-design-fixture";
import { Icons } from "./battle-icons";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { leaderboardEntryForLane, receiptBackedTerminalStatus, terminalStatusCounts } from "./lib/battle-lane-lifecycle-evidence";
import { cn } from "./lib/utils";
import { formatReceiptScore } from "./lib/format-receipt-score";

type Props = {
  receiptFixture?: import("./lib/battle-types").BattleNormalizedUxFixture | null;
  leaderboard: LeaderboardEntry[];
  selectedId?: string;
  playheadSeconds?: number;
  onSelect: (id: string) => void;
};

export function SpectatorRail({ receiptFixture, leaderboard, selectedId, playheadSeconds = 0, onSelect }: Props) {
  const designView = isBattleDesignView();
  const activeLanes = battleLanesForView(undefined, receiptFixture);
  useRegisterAction("battle:leaderboard:select", { action: "BATTLE_LEADERBOARD_SELECT", label: "Select Battle Leaderboard Entry", description: "Select a receipt-backed Battle lane from the spectator rail", tags: ["battle", "receipt-backed"] });

  const entries = designView
    ? mockupRaceLeaders.map((entry) => ({
        rank: entry.rank,
        laneId: entry.laneId,
        name: entry.name,
        status: entry.status,
        time: entry.time,
        proofMode: "receipt_backed_fixture" as const,
        summary: `Gen ${entry.generation}`,
      }))
    : leaderboard.length > 0
      ? leaderboard
      : activeLanes
          .map((lane, index) => leaderboardEntryForLane(lane, index + 1))
          .filter((entry): entry is LeaderboardEntry => Boolean(entry));

  const scoreboard = activeBattleFixture(receiptFixture).scoreboard;

  const [agentSearchQuery, setAgentSearchQuery] = useState("");
  const rosterAgents = useMemo(() => {
    const base = activeLanes.map((lane) => {
      const receiptStatus = receiptBackedTerminalStatus(lane);
      const status = receiptStatus === "survivor" ? "survivor" : receiptStatus ?? "running";
      const role = lane.selected ? "selected" : lane.runner_up ? "runner-up" : null;
      return {
        laneId: lane.id,
        name: lane.name,
        status,
        summary: lane.summary ?? lane.mutationRationale ?? `${lane.team} · gen ${lane.generation}`,
        metric: `G${lane.generation}${role ? ` · ${role}` : ""}`,
      };
    });
    const q = agentSearchQuery.trim().toLowerCase();
    if (!q) return base;
    return base.filter(
      (agent) =>
        agent.name.toLowerCase().includes(q) ||
        agent.summary.toLowerCase().includes(q) ||
        agent.laneId.toLowerCase().includes(q),
    );
  }, [activeLanes, agentSearchQuery]);
  const hasReceiptScores = typeof scoreboard?.red_score === "number" || typeof scoreboard?.blue_score === "number";
  const evidenceFrames = useMemo(() => receiptEvidenceFrames(activeLanes, playheadSeconds), [activeLanes, playheadSeconds]);

  return (
    <aside className={cn("min-h-0 overflow-hidden", designView ? "leftRail battle-mockup-left-rail battle-mockup-panel" : "grid grid-rows-[auto_auto_minmax(0,1fr)] gap-3")}>
      {designView ? (
        <Panel title="Race Leaders" designView={designView}>
          {entries.slice(0, 4).map((entry) => (
            <button
              key={entry.laneId}
              data-qid={`battle:leaderboard:item:${entry.laneId}`}
              data-qs-action="BATTLE_LEADERBOARD_SELECT"
              title={`Select ${entry.name}`}
              type="button"
              onClick={() => onSelect(entry.laneId)}
              className={cn("leaderItem", selectedId === entry.laneId && "selected")}
            >
              <span className={cn("rank", entry.rank === 1 ? "r1" : entry.rank === 2 ? "r2" : entry.rank === 3 ? "r3" : "")}>{entry.rank}</span>
              <span className="min-w-0">
                <span className="liName">{entry.name}</span>
                <span className="liGen">{entry.summary ?? "receipt-backed Battle proof"}</span>
              </span>
              <span className={cn("liRight", entry.status === "blocked" ? "text-battle-blue" : "text-battle-green")}>
                <StatusIcon status={entry.status} />
                {entry.time}
              </span>
            </button>
          ))}
        </Panel>
      ) : (
        <Panel title="Agents" designView={false} count={activeLanes.length}>
          <input
            type="text"
            value={agentSearchQuery}
            onChange={(event) => setAgentSearchQuery(event.target.value)}
            placeholder="Filter agents…"
            aria-label="Filter agents"
            className="roster-search-input"
            data-qid="battle:roster:search"
            data-qs-action="BATTLE_ROSTER_SEARCH"
            title="Filter Battle agents"
          />
          <div className="agent-roster-list">
            {rosterAgents.length === 0 ? (
              <div className="agent-roster-empty">no agents match “{agentSearchQuery}”</div>
            ) : (
              rosterAgents.map((agent) => (
                <button
                  key={agent.laneId}
                  data-qid={`battle:leaderboard:item:${agent.laneId}`}
                  data-qs-action="BATTLE_LEADERBOARD_SELECT"
                  title={`Select ${agent.name}`}
                  type="button"
                  onClick={() => onSelect(agent.laneId)}
                  className={cn("agent-row", selectedId === agent.laneId && "selected")}
                >
                  <span className={cn("status-dot", agent.status)} aria-hidden="true" />
                  <span className="agent-name">
                    <span className="an-title">{agent.name}</span>
                    <span className="an-sub">{agent.summary}</span>
                  </span>
                  <span className="agent-metric">{agent.metric}</span>
                </button>
              ))
            )}
          </div>
        </Panel>
      )}

      {/* Team Standings panel removed: the red/blue standing is already shown in the
          top scorecard, so a left-rail duplicate is redundant. */}

      {!designView ? (
        <Panel title="Live Evidence" designView={false} count={evidenceFrames.revealed.length}>
          <div className="receipt-evidence-panel" data-qid="battle:left-pane:live-evidence">
            <div className="receipt-evidence-clock" data-qid="battle:left-pane:live-evidence:clock">
              receipt playhead {formatRailSeconds(playheadSeconds)}
            </div>
            <div className="receipt-evidence-counts">
              <span>stdout {evidenceFrames.stdoutCount}</span>
              <span>stderr {evidenceFrames.stderrCount}</span>
              <span>events {evidenceFrames.eventCount}</span>
            </div>
            <div className="receipt-evidence-list">
              {evidenceFrames.revealed.length ? (
                evidenceFrames.revealed.slice(-4).map((frame) => (
                  <button
                    key={frame.key}
                    type="button"
                    className="receipt-evidence-row"
                    data-qid={`battle:left-pane:live-evidence:${frame.kind}:${frame.laneId}`}
                    data-qs-action="BATTLE_EVIDENCE_SELECT"
                    title={`${frame.laneName}: ${frame.text}`}
                    onClick={() => onSelect(frame.laneId)}
                  >
                    <span className={`receipt-evidence-kind ${frame.kind}`}>{frame.kind}</span>
                    <span className="receipt-evidence-body">
                      <span className="receipt-evidence-meta">{formatRailSeconds(frame.atSeconds)} · {frame.laneId}</span>
                      <span className="receipt-evidence-text">{frame.text}</span>
                    </span>
                  </button>
                ))
              ) : (
                <div className="receipt-evidence-empty">No receipt stdout/stderr frame has crossed this playhead yet.</div>
              )}
            </div>
            {evidenceFrames.next ? (
              <div className="receipt-evidence-next" data-qid="battle:left-pane:live-evidence:next">
                next {formatRailSeconds(evidenceFrames.next.atSeconds)} · {evidenceFrames.next.laneId} · {evidenceFrames.next.kind}
              </div>
            ) : null}
          </div>
        </Panel>
      ) : null}

      <Panel title="Agent Status" designView={designView} className={designView ? "min-h-0 flex-1" : undefined}>
        {designView
          ? mockupAgentStatus.map((row) => (
              <div key={row.label} className="statusRow">
                <span className={mockStatusTone(row.tone)}>{mockStatusIcon(row.label)}</span>
                {row.label} <b>{row.value}</b>
              </div>
            ))
          : (
            <>
              {(() => {
                const counts = terminalStatusCounts(activeLanes);
                const usefulCount = activeLanes.reduce((n, lane) => n + lane.events.filter((event) => event.proven && event.kind === "useful").length, 0);
                return (
                  <>
                    {counts.running ? <ReceiptStatusLine icon={<Icons.Activity className="h-4 w-4" />} label="Running" value={String(counts.running)} tone="text-battle-cyan" /> : null}
                    <ReceiptStatusLine icon={<Icons.ShieldCheck className="h-4 w-4" />} label="Qualified" value={String(counts.survivor)} tone="text-battle-green" />
                    {counts.blocked ? <ReceiptStatusLine icon={<Icons.ShieldX className="h-4 w-4" />} label="Blocked" value={String(counts.blocked)} tone="text-battle-blue" /> : null}
                    {counts.killed ? <ReceiptStatusLine icon={<Icons.Skull className="h-4 w-4" />} label="Killed" value={String(counts.killed)} tone="text-battle-red" /> : null}
                    {usefulCount ? <ReceiptStatusLine icon={<Icons.Lightbulb className="h-4 w-4" />} label="Useful" value={String(usefulCount)} tone="text-battle-yellow" /> : null}
                    {counts.promoted ? <ReceiptStatusLine icon={<Icons.ShieldCheck className="h-4 w-4" />} label="Promoted" value={String(counts.promoted)} tone="text-battle-green" /> : null}
                    {counts.fastest_crash ? <ReceiptStatusLine icon={<Icons.Rocket className="h-4 w-4" />} label="Fastest crash" value={String(counts.fastest_crash)} tone="text-slate-500" /> : null}
                  </>
                );
              })()}
            </>
          )}
      </Panel>
    </aside>
  );
}

type ReceiptEvidenceFrame = {
  key: string;
  laneId: string;
  laneName: string;
  kind: "stdout" | "stderr" | "event";
  atSeconds: number;
  text: string;
};

function receiptEvidenceFrames(lanes: Lane[], playheadSeconds: number): { revealed: ReceiptEvidenceFrame[]; next: ReceiptEvidenceFrame | null; stdoutCount: number; stderrCount: number; eventCount: number } {
  const frames: ReceiptEvidenceFrame[] = [];
  for (const lane of lanes) {
    const laneAt = lane.first_active_segment_elapsed_seconds ?? lane.visible_from_elapsed_seconds ?? lane.start_elapsed_seconds ?? 0;
    for (const [index, text] of (lane.stdout ?? []).entries()) {
      if (isReceiptText(text)) frames.push({ key: `${lane.id}:stdout:${index}`, laneId: lane.id, laneName: lane.name, kind: "stdout", atSeconds: laneAt, text });
    }
    for (const [index, text] of (lane.stderr ?? []).entries()) {
      if (isReceiptText(text)) frames.push({ key: `${lane.id}:stderr:${index}`, laneId: lane.id, laneName: lane.name, kind: "stderr", atSeconds: laneAt, text });
    }
    for (const event of lane.events) {
      if (!event.proven) continue;
      const atSeconds = event.elapsed_seconds ?? event.at_seconds ?? laneAt;
      frames.push({
        key: `${lane.id}:event:${event.id}`,
        laneId: lane.id,
        laneName: lane.name,
        kind: "event",
        atSeconds,
        text: event.label || event.kind,
      });
    }
  }
  frames.sort((a, b) => a.atSeconds - b.atSeconds || a.key.localeCompare(b.key));
  const revealed = frames.filter((frame) => frame.atSeconds <= playheadSeconds + 0.05);
  return {
    revealed,
    next: frames.find((frame) => frame.atSeconds > playheadSeconds + 0.05) ?? null,
    stdoutCount: revealed.filter((frame) => frame.kind === "stdout").length,
    stderrCount: revealed.filter((frame) => frame.kind === "stderr").length,
    eventCount: revealed.filter((frame) => frame.kind === "event").length,
  };
}

function isReceiptText(value: string | undefined): value is string {
  return Boolean(value && value.trim() && value !== "not emitted");
}

function formatRailSeconds(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function Panel({ title, children, designView = false, className, count }: { title: string; children: React.ReactNode; designView?: boolean; className?: string; count?: number }) {
  return (
    <section className={cn(designView ? cn("railBlock", className) : "overflow-hidden rounded-2xl border border-white/10 bg-battle-panel/70 p-3 shadow-acrylic backdrop-blur-xl", className)}>
      {designView ? (
        <div className="railHead">{title}</div>
      ) : (
        <div className="left-pane-section-header">
          {title}
          {typeof count === "number" ? <span className="section-count">{count}</span> : null}
        </div>
      )}
      {children}
    </section>
  );
}

function StandRow({ tone, icon, label, sub, score }: { tone: "red" | "blue"; icon: React.ReactNode; label: string; sub: string; score: string }) {
  return (
    <div className={`standRow ${tone}`}>
      <div className="standIcon">{icon}</div>
      <div>
        <div className="standName">{label}</div>
        <div className="standSub">{sub}</div>
      </div>
      <div className="standScore">{score}</div>
    </div>
  );
}

function mockStatusIcon(label: string) {
  if (label === "Running") return <Icons.Activity className="h-3.5 w-3.5" />;
  if (label === "Blocked") return <Icons.ShieldX className="h-3.5 w-3.5" />;
  if (label === "Killed") return <Icons.Skull className="h-3.5 w-3.5" />;
  if (label === "Useful") return <Icons.Lightbulb className="h-3.5 w-3.5" />;
  if (label === "Promoted") return <Icons.ShieldCheck className="h-3.5 w-3.5" />;
  return <Icons.Rocket className="h-3.5 w-3.5" />;
}

function mockStatusTone(tone: "cyan" | "blue" | "red" | "yellow" | "green") {
  if (tone === "cyan") return "text-battle-cyan";
  if (tone === "blue") return "text-battle-blue";
  if (tone === "red") return "text-battle-red";
  if (tone === "yellow") return "text-battle-yellow";
  return "text-battle-green";
}

function ReceiptStanding({ icon, label, sub, value, tone }: { icon: React.ReactNode; label: string; sub: string; value: string; tone: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[.035] p-3">
      <div className="flex items-center gap-2.5">
        <span className={tone}>{icon}</span>
        <div>
          <div className={`text-[12px] font-black ${tone}`}>{label}</div>
          <div className="text-[10px] text-slate-500">{sub}</div>
        </div>
      </div>
      <div className={`text-2xl font-black ${tone}`}>{value}</div>
    </div>
  );
}

function ReceiptStatusLine({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 py-2 last:border-0">
      <span className="flex items-center gap-2 text-xs font-bold uppercase text-slate-400">
        <span className={tone}>{icon}</span>
        {label}
      </span>
      <span className={`font-mono text-sm font-black ${tone}`}>{value}</span>
    </div>
  );
}

function StatusIcon({ status }: { status: LeaderboardEntry["status"] }) {
  if (status === "fastest_crash") return <Icons.Rocket className="h-4 w-4 text-battle-green" />;
  if (status === "promoted" || status === "survivor") return <Icons.ShieldCheck className="h-4 w-4 text-battle-green" />;
  if (status === "killed") return <Icons.Skull className="h-4 w-4 text-battle-red" />;
  return <Icons.ShieldX className="h-4 w-4 text-battle-blue" />;
}
