import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Bug, Database, FileJson, Network, Play, Radio, Search, ShieldX, Terminal } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import type { BattleEvent, BattleNetworkSummary, BattleReceiptRef, BattleReplayRef, BlueFinisherState, Lane, ProofMode } from "./lib/battle-types";
import type { BattleLiveEventV1 } from "./lib/battle-transport-types";
import {
  currentBattleLiveBusSnapshot,
  subscribeBattleLiveBus,
  type BattleLiveBusSnapshot,
} from "./lib/battle-live-sse-runtime";
import { laneLifecycleEvidenceView } from "./lib/battle-lane-lifecycle-evidence";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { MockupAgentDetailPane } from "./MockupAgentDetailPane";

type Props = { lane: Lane; lanes: Lane[]; events: BattleEvent[]; activeFinisher: BlueFinisherState | null; onSound?: (cue: string) => void };
type TraceField = "observation" | "hypothesis" | "action" | "result" | "learned" | "next_move";
const TRACE_FIELDS: Array<[TraceField, string]> = [["observation", "Observation"], ["hypothesis", "Hypothesis"], ["action", "Action"], ["result", "Result"], ["learned", "Learned"], ["next_move", "Next move"]];

export function AgentDetailPane({ lane, lanes, events, activeFinisher, onSound }: Props) {
  void lanes;
  if (isBattleDesignView()) return <MockupAgentDetailPane lane={lane} />;
  void activeFinisher;
  void onSound;
  useRegisterAction("battle:agent-pane:tab:summary", { action: "BATTLE_AGENT_PANE_TAB_SUMMARY", label: "Show Battle Agent Summary", description: "Show the Summary tab in the Battle agent detail pane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:turns", { action: "BATTLE_AGENT_PANE_TAB_TURNS", label: "Show Battle Agent Turns", description: "Show the public Battle event trace for the selected lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:logs", { action: "BATTLE_AGENT_PANE_TAB_LOGS", label: "Show Battle Agent Logs", description: "Show receipt-backed JSON events for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:skills", { action: "BATTLE_AGENT_PANE_TAB_SKILLS", label: "Show Battle Agent Skills", description: "Show emitted skills/tools for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:receipts", { action: "BATTLE_AGENT_PANE_TAB_RECEIPTS", label: "Show Battle Agent Receipts", description: "Show proof artifacts for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:proof:docker-replay", { action: "BATTLE_AGENT_PANE_DOCKER_REPLAY", label: "Show Docker Replay Proof", description: "Show the receipt-backed Docker/Judge replay proof for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:live", { action: "BATTLE_AGENT_PANE_TAB_LIVE", label: "Show Battle Agent Live Stream", description: "Show the live streaming stdout/stderr console and packet/network panel for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });

  const lifecycle = useMemo(() => laneLifecycleEvidenceView(lane), [lane]);
  const model = useMemo(() => buildModel(lane, events), [lane, events]);
  const replay = model.replay;

  // Live SSE frames fan in from the shared bus (useBattleLiveTransport owns the single EventSource).
  const liveBus = useBattleLiveBus();
  const liveConsole = useMemo(() => liveConsoleLinesForLane(liveBus.events, lane), [liveBus.events, lane]);
  const livePackets = useMemo(() => livePacketEventsForLane(liveBus.events, lane), [liveBus.events, lane]);
  const liveStdout = useMemo(() => latestNonEmpty(liveConsole.filter((line) => line.stream === "stdout").map((line) => line.text)), [liveConsole]);
  const liveStderr = useMemo(() => latestNonEmpty(liveConsole.filter((line) => line.stream === "stderr").map((line) => line.text)), [liveConsole]);

  return (
    <aside className="flex h-full min-h-0 w-full flex-col" data-qid={`battle:agent-pane:${lane.id}`} title={`Agent detail for ${lane.name}`}>
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl p-0">
        <header className="border-b border-white/10 bg-gradient-to-r from-white/[.035] to-transparent p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0"><div className="battle-label">Agent Detail</div><div className="mt-0.5 text-xs font-semibold leading-snug text-slate-400">Selected agent cockpit</div></div>
            <ProofBadge mode={model.proofMode} />
          </div>
          <div className="flex items-start gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-xl border border-battle-red/45 bg-battle-red/12 text-battle-red shadow-redGlow"><Bug className="h-7 w-7" /></div>
            <div className="min-w-0 flex-1">
              <h2 className="mt-1 truncate text-lg font-black text-white">{lane.name}</h2>
              <div className="mt-1 truncate text-xs text-slate-400">Gen {lane.generation} · {lane.payloadId}</div>
              <div className="mt-1 flex items-center gap-1.5 truncate font-mono text-[10px] text-slate-600"><Bot className="h-3 w-3 shrink-0" /> {model.agentId}</div>
            </div>
          </div>
        </header>

        {replay ? <ReplayPanel replay={replay} /> : lifecycle.scoreSemantics?.schema === "battle.adaptive_lineage_lane_score_semantics.v1" ? <AdaptiveQualificationPanel lifecycle={lifecycle} lane={lane} /> : <NoReplayPanel />}

        <LifecycleEvidencePanel lifecycle={lifecycle} />

        <Tabs defaultValue="summary" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="grid w-full grid-cols-6 rounded-none border-b border-white/10 bg-black/20">
            <TabsTrigger data-qid="battle:agent-pane:tab:summary" data-qs-action="BATTLE_AGENT_PANE_TAB_SUMMARY" value="summary" title="Show Summary tab" className="min-h-11 px-1 text-[11px]">Summary</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:live" data-qs-action="BATTLE_AGENT_PANE_TAB_LIVE" value="live" title="Show live streaming stdout/stderr console and packet panel" className="min-h-11 px-1 text-[11px]">
              <span className="flex items-center gap-1"><Radio className={`h-3.5 w-3.5 ${liveBus.meta.status === "open" || liveBus.meta.status === "following" ? "text-battle-green" : ""}`} />Live{liveConsole.length || livePackets.length ? <span className="rounded bg-white/10 px-1 text-[9px]">{liveConsole.length + livePackets.length}</span> : null}</span>
            </TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:turns" data-qs-action="BATTLE_AGENT_PANE_TAB_TURNS" value="turns" title="Show Turns tab" className="min-h-11 px-1 text-[11px]">Turns</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:logs" data-qs-action="BATTLE_AGENT_PANE_TAB_LOGS" value="logs" title="Show Logs tab" className="min-h-11 px-1 text-[11px]">Logs</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:skills" data-qs-action="BATTLE_AGENT_PANE_TAB_SKILLS" value="skills" title="Show Skills tab" className="min-h-11 px-1 text-[11px]">Skills</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:receipts" data-qs-action="BATTLE_AGENT_PANE_TAB_RECEIPTS" value="receipts" title="Show Receipts tab" className="min-h-11 px-1 text-[11px]">Receipts</TabsTrigger>
          </TabsList>
          <div className="min-h-0 flex-1 overflow-auto p-2.5">
            <TabsContent value="summary" className="mt-0 space-y-2"><CurrentTurn model={model} /><TraceCard trace={model.trace} /><OutputCard stdout={liveStdout || model.stdout} stderr={liveStderr || model.stderr} live={Boolean(liveStdout || liveStderr)} /><SkillsCard skills={model.skills} /></TabsContent>
            <TabsContent value="live" className="mt-0 space-y-2"><LiveStreamPanel meta={liveBus.meta} console={liveConsole} packets={livePackets} isLiveRoute={liveBus.meta.status !== "idle"} /></TabsContent>
            <TabsContent value="turns" className="mt-0 space-y-2">{model.turnEvents.length ? model.turnEvents.map((event) => <TurnEvent key={event.id} event={event} />) : <EmptyState label="No Battle turns emitted." />}</TabsContent>
            <TabsContent value="logs" className="mt-0 space-y-3">{model.relatedEvents.map((event) => <EventRow key={event.id} event={event} />)}<RawJson events={model.relatedEvents} /></TabsContent>
            <TabsContent value="skills" className="mt-0 space-y-2">{model.skills.length ? model.skills.map((skill) => <SkillRow key={`${skill.name}-${skill.receipt_id ?? "no-receipt"}`} skill={skill} />) : <EmptyState label="No skills/tools emitted for this lane." />}</TabsContent>
            <TabsContent value="receipts" className="mt-0 space-y-3"><ReceiptsCard receipts={model.receipts} /></TabsContent>
          </div>
        </Tabs>
      </Card>
    </aside>
  );
}

function ReplayPanel({ replay }: { replay: BattleReplayRef }) {
  const qid = `battle:agent-pane:replay:${replay.pair_id ?? replay.receipt_id}`;
  return (
    <section className="m-3 rounded-xl border border-battle-blue/40 bg-battle-blue/14 p-3 shadow-blueGlow">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><div className="battle-label text-battle-blue">Docker replay</div><div className="mt-1 text-lg font-black text-white">REPLAY IN DOCKER</div><div className="mt-1 truncate text-xs text-slate-400">{replay.can_execute_now ? "Executable replay endpoint available" : "Opens Judge replay receipt · not live execution"}</div></div>
        <ProofBadge mode={replay.proof_mode} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-400"><InfoLine label="red" value={replay.red_worker_id ?? "not emitted"} /><InfoLine label="blue" value={replay.blue_worker_id ?? "not emitted"} /></div>
      <Button data-qid={qid} data-qs-action="BATTLE_AGENT_PANE_DOCKER_REPLAY" title={replay.can_execute_now ? "Run Docker replay endpoint" : "Open receipt-backed Judge replay proof; this does not start live execution"} variant="green" className="mt-3 w-full min-h-11 justify-start text-left"><Play className="h-4 w-4" /> {replay.can_execute_now ? "RUN REPLAY IN DOCKER" : "OPEN REPLAY RECEIPT"}</Button>
    </section>
  );
}

function LifecycleEvidencePanel({ lifecycle }: { lifecycle: ReturnType<typeof laneLifecycleEvidenceView> }) {
  const packet = lifecycle.knowledgePacket;
  const promotion = lifecycle.memoryPromotion;
  const network = lifecycle.networkSummary;
  const calibration = lifecycle.scoreCalibration;
  const parentAnalysis =
    packet.present && packet.parent_analysis && Object.keys(packet.parent_analysis).length
      ? "inherited parent analysis attached"
      : "inherited parent analysis: not emitted";
  const material =
    packet.present ||
    promotion.present ||
    Boolean(calibration) ||
    network.available ||
    lifecycle.spawnRequestLabel !== "not emitted" ||
    lifecycle.tauBranchDecisionLabel !== "not emitted" ||
    lifecycle.childPlanLabel !== "not emitted" ||
    lifecycle.inheritedProbeLabel !== "not emitted";
  const [expanded, setExpanded] = useState(material);

  return (
    <section className="m-3 rounded-xl border border-white/10 bg-white/[.025] p-3" data-qid="battle:agent-pane:lifecycle-evidence" data-material={material ? "1" : "0"}>
      <div className="flex items-center justify-between gap-2">
        <div className="battle-label">Lifecycle evidence</div>
        <button
          type="button"
          className="rounded border border-white/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400 hover:border-white/20 hover:text-slate-200"
          data-qid="battle:agent-pane:lifecycle-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Hide" : "Show"}
        </button>
      </div>
      {!material ? (
        <p className="mt-2 text-xs leading-5 text-slate-500" data-qid="battle:agent-pane:lifecycle-empty">
          No adaptive-lifecycle receipts on this lane yet. Fail-closed: nothing invented.
        </p>
      ) : null}
      {expanded ? (
        <div className="mt-2 grid gap-2 text-xs">
          <LifecycleLine field="knowledge_packet" value={packet.present ? `${packet.status}${packet.packet_id ? ` · ${packet.packet_id}` : ""}` : "not emitted"} />
          <LifecycleLine field="child_ack" value={lifecycle.childAckLabel} />
          <LifecycleLine field="inherited_parent_analysis" value={parentAnalysis} />
          <LifecycleLine field="tau_branch_decision" value={lifecycle.tauBranchDecisionLabel} />
          <LifecycleLine field="spawn_request" value={lifecycle.spawnRequestLabel} />
          <LifecycleLine field="child_inherited_plan" value={lifecycle.childPlanLabel} />
          <LifecycleLine field="child_inherited_probe" value={lifecycle.inheritedProbeLabel} />
          <LifecycleLine field="memory_promotion" value={promotion.present ? `${promotion.durable_promoted ? "durable promoted" : "not promoted"} · ${promotion.reason ?? "receipt evaluated"}` : "not emitted"} />
          <LifecycleLine field="network_summary.available" value={network.available ? "true" : "false"} />
          <LifecycleLine field="network_summary.full_packet_capture_proven" value={network.full_packet_capture_proven ? "true" : "false"} />
          <LifecycleLine field="network_summary.reason" value={network.reason ?? "not emitted"} />
          <LifecycleLine field="packet capture" value={lifecycle.packetCaptureLabel} />
          <LifecycleLine field="score_calibration" value={calibration ? (calibration.outcome_class ?? "receipt-backed calibration attached") : "not emitted"} />
        </div>
      ) : null}
    </section>
  );
}

function LifecycleLine({ field, value }: { field: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-white/10 bg-black/20 px-2 py-1.5" data-battle-lifecycle-field={field}>
      <div className="battle-label truncate" title={field}>{field}</div>
      <div className="mt-0.5 truncate font-mono text-[11px] leading-snug text-slate-300" title={value}>{value}</div>
    </div>
  );
}

function NoReplayPanel() {
  return (
    <section className="m-3">
      <div className="battle-label mb-1">Docker replay</div>
      <div className="rounded-md border border-dashed border-white/20 bg-white/[.05] px-4 py-3 text-center text-sm italic text-slate-400">
        No Judge replay receipt is attached to this selected exploit lane.
      </div>
    </section>
  );
}

function AdaptiveQualificationPanel({ lifecycle, lane }: { lifecycle: ReturnType<typeof laneLifecycleEvidenceView>; lane: Lane }) {
  const semantics = lifecycle.scoreSemantics;
  const calibration = lifecycle.scoreCalibration;
  const rules = semantics?.rules ?? {};
  const confirmed = rules.vulnerable_original_confirmed ? "vulnerable original confirmed" : "vulnerable original not confirmed";
  const bypass = rules.patched_bypass ? "patched bypass observed" : "no patched bypass";
  return (
    <section className="m-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3" data-qid="battle:agent-pane:adaptive-qualification">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="battle-label text-emerald-200">Adaptive qualification</div>
          <div className="mt-1 text-lg font-black text-white">{semantics?.outcome_tier ?? "PASS"}</div>
          <div className="mt-1 text-xs leading-5 text-slate-300">{lane.name} · {semantics?.outcome_class ?? "receipt-backed node"}</div>
        </div>
        <ProofBadge mode={semantics?.proof_mode ?? lane.proofMode ?? "receipt_backed_fixture"} />
      </div>
      <div className="mt-2 grid gap-2 text-[11px] text-slate-300">
        <InfoLine label="Judge" value={`${confirmed} · ${bypass}`} />
        <InfoLine label="Basis" value={semantics?.score_basis ?? calibration?.formula ?? "adaptive lineage receipt"} />
      </div>
    </section>
  );
}

function CurrentTurn({ model }: { model: AgentPaneModel }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="text-xs font-black uppercase tracking-[.08em] text-battle-purple">Current loop · #{model.loopIndex}</div><div className="mt-1 text-sm leading-5 text-slate-300">{model.currentAction}</div><div className="mt-1 truncate font-mono text-xs text-slate-500">{model.turnId}</div></div><Badge variant="purple">{model.phase}</Badge></div></section>;
}

function TraceCard({ trace }: { trace: Record<TraceField, string | undefined> }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="battle-label">Public trace</div><div className="mt-2 grid gap-1.5">{TRACE_FIELDS.map(([key, label]) => <div key={key} className="grid grid-cols-[86px_1fr] gap-2 text-xs leading-5"><span className="battle-label">{label}</span><span className={trace[key] ? "text-slate-300" : "text-slate-600"}>{trace[key] || "not emitted"}</span></div>)}</div></section>;
}

function OutputCard({ stdout, stderr, live }: { stdout: string; stderr: string; live?: boolean }) {
  return <section className="grid grid-cols-2 gap-2"><InfoPanel label={live ? "stdout latest · live" : "stdout latest"} value={stdout} tone="text-slate-300" /><InfoPanel label={live ? "stderr latest · live" : "stderr latest"} value={stderr} tone="text-battle-red" /></section>;
}

function SkillsCard({ skills }: { skills: AgentPaneSkill[] }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="mb-2 battle-label">Skills / tools used</div><div className="flex flex-wrap gap-2">{skills.length ? skills.map((skill) => <SkillChip key={`${skill.name}-${skill.receipt_id ?? "no-receipt"}`} skill={skill} />) : <span className="text-xs text-slate-600">not emitted</span>}</div></section>;
}

function ReceiptsCard({ receipts }: { receipts: BattleReceiptRef[] }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="mb-2 battle-label">Receipts / proof</div><div className="space-y-2">{receipts.length ? receipts.map((receipt) => <ReceiptRow key={`${receipt.receipt_id}-${receipt.receipt_type}-${receipt.pair_id ?? "lane"}`} receipt={receipt} />) : <div className="text-xs text-slate-600">not emitted</div>}</div></section>;
}

function TurnEvent({ event }: { event: BattleEvent }) {
  return <div className="rounded-xl border border-white/10 bg-white/[.025] p-3"><div className="flex items-start gap-3"><div className="mt-0.5 text-battle-blue"><Terminal className="h-4 w-4" /></div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><div className="truncate font-black text-slate-100">{event.turn?.phase ?? event.event_type}</div><ProofBadge mode={event.proof_mode ?? "missing"} /></div><div className="mt-1 text-sm leading-5 text-slate-300">{event.turn?.current_action ?? event.summary}</div><div className="mt-2 text-xs text-battle-green">{event.public_trace?.learned || "not emitted"}</div></div></div></div>;
}

function EventRow({ event }: { event: BattleEvent }) {
  return <div className="grid grid-cols-[1fr_auto] gap-2 rounded-xl border border-white/10 bg-white/[.025] p-3 text-xs"><div className="min-w-0"><div className="truncate font-bold text-slate-100">{event.event_type}</div><div className="mt-1 truncate text-slate-400">{event.summary}</div></div><ProofBadge mode={event.proof_mode ?? "missing"} /></div>;
}

function RawJson({ events }: { events: BattleEvent[] }) {
  const [open, setOpen] = useState(false);
  return <section><div className="mb-2 flex items-center justify-between"><div className="battle-label">Raw JSON</div><Button data-qid="battle:agent-pane:logs:raw-toggle" data-qs-action="BATTLE_AGENT_PANE_LOGS_RAW_TOGGLE" title="Toggle raw receipt-backed event JSON" variant="ghost" onClick={() => setOpen((value) => !value)}>{open ? "Hide raw JSON" : "View raw JSON"}</Button></div>{open ? <pre className="max-h-64 overflow-auto rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-xs leading-6 text-slate-300">{events.map((event) => JSON.stringify(event)).join("\n") || "No related receipt-backed events."}</pre> : null}</section>;
}

function SkillRow({ skill }: { skill: AgentPaneSkill }) {
  return <div className="grid grid-cols-[1fr_74px_120px] items-center gap-2 rounded-xl border border-white/10 bg-white/[.025] px-3 py-2 text-sm"><div className="min-w-0"><div className="flex items-center gap-2 truncate font-bold text-slate-100"><SkillIcon name={skill.name} />{skill.name}</div><div className="truncate text-xs text-slate-500">{skill.summary || "not emitted"}</div></div><Badge variant={skill.kind === "tool" ? "blue" : "green"}>{skill.kind}</Badge><ProofBadge mode={skill.proof_mode} /></div>;
}

function SkillChip({ skill }: { skill: AgentPaneSkill }) {
  return <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-battle-green/25 bg-battle-green/10 px-2 py-1 text-xs font-bold text-battle-green" title={`${skill.kind} · ${proofLabel(skill.proof_mode)}`}><SkillIcon name={skill.name} /><span className="truncate">{skill.name}</span><span className="rounded border border-white/10 px-1 text-[9px] uppercase text-slate-400">{skill.kind}</span></span>;
}

function SkillIcon({ name }: { name: string }) {
  if (name.includes("docker") || name.includes("replay")) return <Play className="h-3.5 w-3.5 shrink-0" />;
  if (name.includes("search") || name.includes("scillm")) return <Search className="h-3.5 w-3.5 shrink-0" />;
  if (name.includes("memory") || name.includes("knowledge")) return <Database className="h-3.5 w-3.5 shrink-0" />;
  return <Bot className="h-3.5 w-3.5 shrink-0" />;
}

function ReceiptRow({ receipt }: { receipt: BattleReceiptRef }) {
  return <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 p-2"><div className="flex min-w-0 items-center gap-2 text-sm text-slate-200"><FileJson className="h-4 w-4 shrink-0 text-battle-blue" /><div className="min-w-0"><div className="truncate">{receipt.receipt_id}</div><div className="truncate text-xs text-slate-500">{receipt.receipt_type} · {receipt.summary || "receipt-backed artifact"}</div></div></div><ProofBadge mode={receipt.proof_mode} /></div>;
}

function InfoPanel({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <section className="min-w-0 rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="battle-label">{label}</div><div className={`mt-2 break-words font-mono text-xs leading-5 ${tone}`}>{value}</div></section>;
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded border border-white/10 bg-black/20 px-2 py-1"><span className="battle-label mr-1">{label}</span><span className="font-mono">{value}</span></div>;
}

function EmptyState({ label }: { label: string }) {
  return <div className="rounded-xl border border-white/10 bg-white/[.025] p-3 text-sm text-slate-500">{label}</div>;
}

function ProofBadge({ mode }: { mode: ProofMode }) {
  const label = proofLabel(mode);
  const variant = mode === "receipt_backed_fixture" ? "green" : mode === "live" ? "green" : mode === "fixture" ? "blue" : mode === "pending" ? "purple" : "red";
  return <Badge variant={variant} title={label}>{label}</Badge>;
}

function proofLabel(mode: ProofMode) {
  if (mode === "receipt_backed_fixture") return "RECEIPT-BACKED FIXTURE";
  if (mode === "live") return "LIVE PROOF";
  if (mode === "fixture") return "FIXTURE TRACE";
  if (mode === "mocked") return "MOCKED SKILL";
  if (mode === "pending") return "PROOF PENDING";
  return "MISSING PROOF";
}

type AgentPaneSkill = {
  name: string;
  kind: "skill" | "tool" | "unregistered";
  status: "running" | "ok" | "failed" | "mocked" | "pending";
  timestamp?: string;
  summary?: string;
  receipt_id?: string;
  proof_mode: ProofMode;
};

type AgentPaneModel = {
  laneName: string;
  agentId: string;
  turnId: string;
  loopIndex: number;
  phase: string;
  status: string;
  currentAction: string;
  trace: Record<TraceField, string | undefined>;
  stdout: string;
  stderr: string;
  skills: AgentPaneSkill[];
  receipts: BattleReceiptRef[];
  relatedEvents: BattleEvent[];
  turnEvents: BattleEvent[];
  proofMode: ProofMode;
  replay?: BattleReplayRef | null;
};

function terminalStatusLabel(lane: Lane): string {
  const semantics = lane.score_semantics ?? lane.cockpit?.score_semantics;
  const blueOutcome = lane.cockpit?.blue_outcome;
  if (semantics?.terminal_state && semantics.proof_mode === "receipt_backed_fixture") {
    return `${semantics.outcome_tier ?? semantics.outcome_class ?? semantics.terminal_state} · receipt-backed`;
  }
  if (blueOutcome?.proof_mode === "receipt_backed_fixture" && blueOutcome.status) {
    return `${blueOutcome.status} · receipt-backed`;
  }
  if (lane.terminal === "none") return "no receipt-backed terminal emitted";
  return `${lane.terminal} · awaiting receipt proof`;
}

function buildModel(lane: Lane, events: BattleEvent[]): AgentPaneModel {
  const relatedEvents = events.filter((event) => isRelatedEvent(event, lane));
  const primary = relatedEvents.find((event) => event.event_type === "blue.blocked_red") ?? relatedEvents.find((event) => event.event_type === "judge.verdict") ?? relatedEvents.find((event) => event.turn) ?? relatedEvents[0];
  const proofMode = lane.proofMode ?? primary?.proof_mode ?? "missing";
  const latestTurn = [...relatedEvents].reverse().find((event) => event.turn) ?? primary;
  const traceSource = [...relatedEvents].reverse().find((event) => event.public_trace)?.public_trace;
  const skills = uniqueSkills(relatedEvents.flatMap((event) => event.skills ?? []));
  const receipts = uniqueReceipts([...relatedEvents.flatMap((event) => event.receipts ?? []), ...(lane.receipts ?? []).map((receiptId) => ({ receipt_id: receiptId, receipt_type: "lane_receipt", summary: "Lane receipt reference.", proof_mode: proofMode }))]);
  const replay = lane.replay ?? relatedEvents.find((event) => event.replay)?.replay ?? null;
  return {
    laneName: lane.name,
    agentId: primary?.tau_subagent_id || primary?.actor_id || "receipt-backed-worker",
    turnId: latestTurn?.tau_turn_id || replay?.pair_id || "judge replay",
    loopIndex: latestTurn?.turn?.loop_index ?? 0,
    phase: latestTurn?.turn?.phase || primary?.event_type || "not emitted",
    status: terminalStatusLabel(lane),
    currentAction: latestTurn?.turn?.current_action || primary?.summary || "not emitted",
    trace: { observation: traceSource?.observation, hypothesis: traceSource?.hypothesis, action: traceSource?.action, result: traceSource?.result, learned: traceSource?.learned, next_move: traceSource?.next_move },
    stdout: latestNonEmpty([primary?.output?.stdout_excerpt, ...(lane.stdout ?? [])]) || "not emitted",
    stderr: latestNonEmpty([primary?.output?.stderr_excerpt, ...(lane.stderr ?? [])]) || "not emitted",
    skills,
    receipts,
    relatedEvents,
    turnEvents: relatedEvents.filter((event) => event.turn),
    proofMode,
    replay
  };
}

function isRelatedEvent(event: BattleEvent, lane: Lane) {
  return event.actor_id === lane.id || event.red_lane_id === lane.id || event.payload_id === lane.payloadId || event.target_actor_ids?.includes(lane.id) || event.target_actor_ids?.includes(lane.payloadId) || event.parent_id === lane.id || event.team === "judge";
}

function uniqueSkills(skills: AgentPaneSkill[]) {
  const seen = new Set<string>();
  return skills.filter((skill) => {
    const key = `${skill.name}-${skill.receipt_id ?? "no-receipt"}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueReceipts(receipts: BattleReceiptRef[]) {
  const byId = new Map<string, BattleReceiptRef>();
  for (const receipt of receipts) byId.set(`${receipt.receipt_id}-${receipt.receipt_type}-${receipt.pair_id ?? ""}`, receipt);
  return Array.from(byId.values());
}

function latestNonEmpty(values: Array<string | undefined>) {
  return values.filter((value): value is string => Boolean(value && value.trim() && value !== "not emitted")).at(-1);
}

// ---------------------------------------------------------------------------
// Live SSE lane streaming (stdout/stderr console + packet/network panel).
// Frames arrive via the shared bus published by useBattleLiveTransport's single
// EventSource; this pane never opens its own connection.
// ---------------------------------------------------------------------------

function useBattleLiveBus(): BattleLiveBusSnapshot {
  const [snapshot, setSnapshot] = useState<BattleLiveBusSnapshot>(() => currentBattleLiveBusSnapshot());
  useEffect(() => subscribeBattleLiveBus(setSnapshot), []);
  return snapshot;
}

type LiveConsoleLine = { key: string; seq: number; at: number; stream: "stdout" | "stderr"; text: string; proof: ProofMode; eventType: string };
type LivePacketEvent = { key: string; seq: number; at: number; eventType: string; summary: string; network?: BattleNetworkSummary; proof: ProofMode };

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function liveEventLaneIds(event: BattleLiveEventV1): Set<string> {
  const ids = new Set<string>();
  const add = (value: unknown) => { if (typeof value === "string" && value) ids.add(value); };
  const payload = asRecord(event.payload);
  add(event.lifecycle?.lane_id);
  add(payload.lane_id); add(payload.actor_id); add(payload.red_lane_id); add(payload.payload_id);
  if (Array.isArray(payload.target_actor_ids)) payload.target_actor_ids.forEach(add);
  const source = asRecord(payload.source_event);
  add(source.actor_id); add(source.lane_id); add(source.red_lane_id); add(source.payload_id);
  if (Array.isArray(source.target_actor_ids)) source.target_actor_ids.forEach(add);
  return ids;
}

function liveEventMatchesLane(event: BattleLiveEventV1, lane: Lane): boolean {
  const ids = liveEventLaneIds(event);
  return ids.has(lane.id) || ids.has(lane.payloadId);
}

function liveConsoleLinesForLane(events: BattleLiveEventV1[], lane: Lane): LiveConsoleLine[] {
  const lines: LiveConsoleLine[] = [];
  for (const event of events) {
    if (!liveEventMatchesLane(event, lane)) continue;
    const payload = asRecord(event.payload);
    const source = asRecord(payload.source_event);
    const output = asRecord(source.output ?? payload.output);
    const proof = (source.proof_mode ?? payload.proof_mode ?? "missing") as ProofMode;
    const streams: Array<["stdout" | "stderr", string]> = [["stdout", "stdout_excerpt"], ["stderr", "stderr_excerpt"]];
    for (const [stream, key] of streams) {
      const text = output[key];
      if (typeof text === "string" && text.trim() && text !== "not emitted") {
        lines.push({ key: `${event.seq}-${stream}`, seq: event.seq, at: event.at_seconds, stream, text, proof, eventType: event.event_type });
      }
    }
  }
  return lines;
}

function livePacketEventsForLane(events: BattleLiveEventV1[], lane: Lane): LivePacketEvent[] {
  const out: LivePacketEvent[] = [];
  for (const event of events) {
    if (!liveEventMatchesLane(event, lane)) continue;
    const payload = asRecord(event.payload);
    const source = asRecord(payload.source_event);
    const type = event.event_type.toLowerCase();
    const networkRaw = source.network_summary ?? source.network ?? payload.network_summary ?? payload.network;
    const packetRaw = source.packet ?? source.packets ?? payload.packet ?? payload.packets;
    if (!(type.includes("packet") || type.includes("network") || networkRaw || packetRaw)) continue;
    const summary = typeof source.summary === "string" && source.summary ? source.summary : typeof payload.summary === "string" ? (payload.summary as string) : "";
    out.push({
      key: `${event.seq}-pkt`,
      seq: event.seq,
      at: event.at_seconds,
      eventType: event.event_type,
      summary,
      network: networkRaw && typeof networkRaw === "object" ? (networkRaw as BattleNetworkSummary) : undefined,
      proof: (source.proof_mode ?? payload.proof_mode ?? "missing") as ProofMode,
    });
  }
  return out;
}

function liveStatusLabel(status: string): string {
  if (status === "open" || status === "following") return "STREAMING LIVE";
  if (status === "connecting") return "CONNECTING";
  if (status === "ended") return "STREAM ENDED";
  if (status === "gap_recovery") return "GAP · RECOVERING";
  if (status === "error") return "STREAM ERROR";
  if (status === "contract_only_blocked") return "CONTRACT ONLY · ADAPTER DOWN";
  if (status === "adapter_unavailable") return "ADAPTER UNAVAILABLE";
  return "IDLE";
}

function LiveStreamPanel({ meta, console, packets, isLiveRoute }: { meta: BattleLiveBusSnapshot["meta"]; console: LiveConsoleLine[]; packets: LivePacketEvent[]; isLiveRoute: boolean }) {
  const streaming = meta.status === "open" || meta.status === "following";
  const stdoutLines = console.filter((line) => line.stream === "stdout");
  const stderrLines = console.filter((line) => line.stream === "stderr");
  return (
    <section className="space-y-2" data-qid="battle:agent-pane:live-stream" data-live-status={meta.status}>
      <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[.025] px-3 py-2">
        <div className="flex items-center gap-2">
          <Radio className={`h-4 w-4 ${streaming ? "text-battle-green" : meta.status === "error" ? "text-battle-red" : "text-slate-500"}`} />
          <span className="battle-label">{liveStatusLabel(meta.status)}</span>
        </div>
        <span className="font-mono text-[10px] text-slate-500">seq {meta.appliedSeq}/{meta.lastSeq}</span>
      </div>
      {!isLiveRoute ? (
        <EmptyState label="Live SSE transport is not connected. Start ./run.sh serve-live-transport and open #battle/live to stream evidence." />
      ) : null}
      <LiveConsole label="stdout" icon="stdout" lines={stdoutLines} tone="text-slate-200" />
      <LiveConsole label="stderr" icon="stderr" lines={stderrLines} tone="text-battle-red" />
      <LivePacketPanel packets={packets} />
    </section>
  );
}

function LiveConsole({ label, lines, tone }: { label: string; icon: "stdout" | "stderr"; lines: LiveConsoleLine[]; tone: string }) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [lines.length]);
  return (
    <section className="rounded-lg border border-white/10 bg-black/40 p-2.5" data-qid={`battle:agent-pane:live-console:${label}`}>
      <div className="mb-1.5 flex items-center gap-1.5"><Terminal className="h-3.5 w-3.5 text-slate-500" /><span className="battle-label">{label} · live console</span><span className="ml-auto font-mono text-[10px] text-slate-600">{lines.length} lines</span></div>
      <div ref={scrollRef} className="max-h-40 overflow-auto rounded border border-white/5 bg-black/50 p-2 font-mono text-[11px] leading-5">
        {lines.length ? lines.map((line) => (
          <div key={line.key} className={`flex gap-2 ${tone}`} data-live-seq={line.seq}>
            <span className="shrink-0 text-slate-600">[{line.at.toFixed(1)}s·{line.eventType}]</span>
            <span className="break-all">{line.text}</span>
          </div>
        )) : <div className="text-slate-600">No live {label} frames for this lane yet.</div>}
      </div>
    </section>
  );
}

function LivePacketPanel({ packets }: { packets: LivePacketEvent[] }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5" data-qid="battle:agent-pane:live-packets">
      <div className="mb-1.5 flex items-center gap-1.5"><Network className="h-3.5 w-3.5 text-battle-blue" /><span className="battle-label">packet / network · live</span><span className="ml-auto font-mono text-[10px] text-slate-600">{packets.length}</span></div>
      <div className="space-y-1.5">
        {packets.length ? packets.map((packet) => (
          <div key={packet.key} className="rounded border border-white/10 bg-black/25 px-2 py-1.5 text-[11px]" data-live-seq={packet.seq}>
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-bold text-slate-200">{packet.eventType}</span>
              <ProofBadge mode={packet.proof} />
            </div>
            {packet.summary ? <div className="mt-0.5 truncate text-slate-400">{packet.summary}</div> : null}
            {packet.network ? (
              <div className="mt-1 grid grid-cols-2 gap-1 font-mono text-[10px] text-slate-500">
                <span>available: {String(packet.network.available)}</span>
                <span>full_capture_proven: {String(packet.network.full_packet_capture_proven ?? false)}</span>
                {packet.network.format ? <span>format: {packet.network.format}</span> : null}
                {packet.network.sha256 ? <span className="truncate">sha256: {packet.network.sha256.slice(0, 12)}…</span> : null}
              </div>
            ) : null}
          </div>
        )) : <div className="text-[11px] text-slate-600">No live packet/network frames for this lane yet.</div>}
      </div>
      <p className="mt-2 text-[10px] leading-4 text-slate-600">Live transport frames are receipt-backed transport records. This panel does not claim packet_level_behavior, exploit success, or Blue outcome unless a Judge/network receipt proves it.</p>
    </section>
  );
}
