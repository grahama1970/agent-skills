import { cn } from "./lib/utils";
import { formatReceiptScore } from "./lib/format-receipt-score";
import { Button } from "./ui/button";
import type { BattleEvent } from "./lib/battle-types";
import { activeBattleFixture } from "./lib/battle-data";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import {
  mockupArenaLabel,
  mockupDifficultyLabel,
  mockupHeaderClock,
  mockupLiveEvents,
  mockupScoreboard,
} from "./lib/mockup-design-fixture";
import { Icons } from "./battle-icons";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { BattleHungerGamesDeathAnnouncement } from "./BattleHungerGamesDeathAnnouncement";
import type { HungerGamesDeathCard } from "./lib/battle-hunger-games-notifications";

type Props = {
  receiptFixture?: import("./lib/battle-types").BattleNormalizedUxFixture | null;
  events: BattleEvent[];
  onTestSound: (cue: string) => void;
  onSelectActor: (id: string) => void;
  onOpenJsonl: () => void;
  deathAnnouncement?: HungerGamesDeathCard | null;
  onDismissDeathAnnouncement?: () => void;
};

export function BattleHeader({ receiptFixture, events, onSelectActor, onOpenJsonl, deathAnnouncement = null, onDismissDeathAnnouncement }: Props) {
  useRegisterAction("battle:events:rail", { action: "BATTLE_EVENTS_OPEN", label: "Open Battle Receipt Events", description: "Open the receipt-backed Battle event stream popover", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:events:item", { action: "BATTLE_EVENT_SELECT", label: "Select Battle Event Actor", description: "Select the lane associated with a receipt-backed Battle event", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:events:view-all", { action: "BATTLE_EVENTS_VIEW_ALL", label: "View All Battle Receipts", description: "Open the full receipt-backed Battle event list", tags: ["battle", "receipt-backed"] });

  const designView = isBattleDesignView();
  const fixture = activeBattleFixture(receiptFixture);
  const scenario = fixture.scenario;
  const scoreboard = fixture.scoreboard;
  const clock = fixture.battle_clock;
  const endpoint = scenario?.public_entrypoint ?? "/api/import-zip";
  const cwe = scenario?.cwe ?? "CWE-22";
  const family = scenario?.hidden_vulnerability_family ?? "Zip Slip path traversal";
  const battleTitle = fixture.spectator_shell?.battle_title ?? `${fixture.battle_id?.toUpperCase() ?? "BATTLE-004"} · POST ${endpoint}`;
  const arenaLabel = designView ? mockupArenaLabel() : "ZIP_SLIP_ARB";
  const difficultyLabel = designView ? mockupDifficultyLabel() : "JUDGE";

  function selectEvent(event: BattleEvent) {
    const candidate =
      event.actor_id.startsWith("payload")
        ? event.actor_id
        : event.red_lane_id ?? event.payload_id ?? event.target_actor_ids?.find((id) => id.startsWith("payload"));
    if (candidate) onSelectActor(candidate);
  }

  if (designView) {
    return (
      <header className="topbar">
        <div className="headerBlock">
          <div className="title">
            <h1>BATTLE-004 · POST {endpoint}</h1>
            <p>
              {cwe} Zip Slip <span className="dim">·</span> autonomous exploit agents evolve under pressure <span className="dim">·</span> fastest proven crash wins
            </p>
          </div>
          <div className="metaInline">
            <span><b>Arena</b> {arenaLabel}</span>
            <span><b>Objective</b> Prevent archive path traversal</span>
            <span><b>Target</b> POST {endpoint}</span>
            <span><b>Difficulty</b> {difficultyLabel}</span>
            <span className="roundClock"><b>Round Time</b> {mockupHeaderClock().elapsed} / {mockupHeaderClock().allotted}</span>
          </div>
        </div>

        <div className="score battle-score-block">
          <div className="scoreSide red" data-testid="score-red">
            <div className="scoreLabel">RED TEAM</div>
            <div className="scoreValueRow">
              <div className="scoreIcon"><Icons.Bug aria-hidden="true" /></div>
              <div className="scoreNum">{mockupScoreboard().red}</div>
            </div>
          </div>
          <div className="vs">VS</div>
          <div className="scoreSide blue">
            <div className="scoreLabel">BLUE TEAM</div>
            <div className="scoreValueRow">
              <div className="scoreNum">{mockupScoreboard().blue}</div>
              <div className="scoreIcon"><Icons.Shield aria-hidden="true" /></div>
            </div>
          </div>
        </div>

        <div className="liveEvents battle-live-events">
          <div className="liveEventsHead"><span className="dot red" aria-hidden="true" /> LIVE EVENTS</div>
          {mockupLiveEvents.map((event) => (
            <button
              key={event.id}
              type="button"
              data-qid={`battle:events:item:${event.id}`}
              data-qs-action="BATTLE_EVENT_SELECT"
              title={`Select live event ${event.highlight}`}
              className="liveEventRow battle-live-event-row w-full text-left transition-colors hover:bg-white/[.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
              onClick={() => event.laneId && onSelectActor(event.laneId)}
            >
              <span className="leTime">{event.time}</span>
              <span className="leIconSlot" style={{ color: event.iconTone === "green" ? "#3cf07a" : event.iconTone === "blue" ? "#5aadff" : "#ff4d5c" }}>
                <MockLiveIcon icon={event.icon} />
              </span>
              <span className="leText">
                {event.prefix}
                <b className={event.highlightTone}>{event.highlight}</b>
              </span>
            </button>
          ))}
        </div>
      </header>
    );
  }

  return (
    <header className="relative grid min-h-0 grid-cols-[minmax(0,1fr)_430px] items-center gap-4 overflow-hidden rounded-2xl border border-white/10 bg-battle-panel/80 px-4 py-3 shadow-acrylic backdrop-blur-2xl max-[1500px]:grid-cols-[minmax(0,1fr)_380px]">
      <div className="grid min-w-0 max-w-[700px] grid-rows-[auto_auto] gap-3 self-stretch max-[1500px]:max-w-[520px]">
        <div className="flex min-w-0 items-center gap-3">
          <div className="shrink-0 rounded-xl border border-battle-red/30 bg-battle-red/10 p-2 text-battle-red shadow-redGlow">
            <Icons.Swords className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-black tracking-tight text-white 2xl:text-3xl">{battleTitle}</h1>
            <p className="mt-1 truncate text-sm font-medium text-slate-400">{`${cwe} · ${family} · autonomous exploit agents evolve under pressure · fastest proven crash wins`}</p>
          </div>
        </div>
        <div className="grid min-h-[45px] grid-cols-[.75fr_1.4fr_1.25fr_.7fr_.9fr] overflow-hidden rounded-lg border border-white/10 bg-black/10">
          <Fact label="Arena" value={arenaLabel} title={scenario?.scenario_id ?? arenaLabel} />
          <Fact label="Objective" value="Prevent archive path traversal" />
          <Fact label="Target" value={`POST ${endpoint}`} />
          <Fact label="Difficulty" value={difficultyLabel} />
          <Fact label="Round time" value={`${formatSeconds(clock?.elapsed_seconds)} / ${formatSeconds(clock?.allotted_seconds)}`} />
        </div>
      </div>

      <div className="battle-score-block pointer-events-auto absolute left-1/2 top-1/2 grid h-[84px] w-[430px] -translate-x-1/2 -translate-y-1/2 grid-cols-[1fr_44px_1fr] overflow-hidden rounded-2xl border border-white/10 bg-[rgba(3,8,15,.62)] shadow-acrylic max-[1500px]:w-[390px]">
        <ScoreCell label="Red Team" sub="Exploit Agents" value={formatReceiptScore(scoreboard?.red_score)} tone="red" icon={<Icons.Bug className="h-7 w-7" />} align="left" />
        <div className="flex items-center justify-center border-x border-white/10 bg-black/25 text-[11px] font-black tracking-[0.24em] text-slate-500">VS</div>
        <ScoreCell label="Blue Team" sub="Patch Agents" value={formatReceiptScore(scoreboard?.blue_score)} tone="blue" icon={<Icons.Shield className="h-7 w-7" />} align="right" />
      </div>

      <div className="flex min-w-0 items-start justify-end gap-2">
        <div className={cn("battle-live-events", deathAnnouncement && "has-death-announcement")}>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">
            <span className="h-2 w-2 rounded-full bg-battle-red shadow-redGlow" /> LIVE EVENTS
          </div>
          <BattleHungerGamesDeathAnnouncement card={deathAnnouncement} onDismiss={onDismissDeathAnnouncement ?? (() => undefined)} />
          {events.slice(-3).reverse().map((event, index) => (
            <button key={`${event.id}:${index}`} type="button" data-qid={`battle:events:item:${event.id}`} data-qs-action="BATTLE_EVENT_SELECT" title={`Select receipt event ${event.id}`} onClick={() => selectEvent(event)} className="battle-live-event-row w-full text-left transition-colors hover:bg-white/[.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40">
              <span className="battle-live-event-time">{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
              <EventIcon event={event} />
              <ReceiptLiveEventText event={event} />
            </button>
          ))}
        </div>
        <Button data-qid="battle:events:view-all" data-qs-action="BATTLE_EVENTS_VIEW_ALL" variant="outline" size="icon" className="h-11 min-h-11 w-11 min-w-11 shrink-0" title="View all receipt-backed events" onClick={onOpenJsonl}>
          <Icons.FileJson className="h-5 w-5" />
        </Button>
      </div>
    </header>
  );
}

function Fact({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0 border-r border-white/10 px-3 py-2 last:border-r-0">
      <div className="truncate text-[10px] font-black uppercase tracking-[.12em] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-[12px] font-black text-white" title={title ?? value}>{value}</div>
    </div>
  );
}

function ScoreCell({ label, sub, value, tone, icon, align }: { label: string; sub: string; value: string; tone: "red" | "blue"; icon: React.ReactNode; align: "left" | "right" }) {
  const color = tone === "red" ? "text-battle-red" : "text-battle-blue";
  const glow = tone === "red" ? "from-battle-red/10 to-transparent" : "from-battle-blue/10 to-transparent";
  return (
    <div className={`flex h-full items-center gap-3 bg-gradient-to-r ${glow} px-4 ${align === "right" ? "flex-row-reverse text-right" : ""}`}>
      <div className="min-w-0">
        <div className={`text-[10px] font-black uppercase tracking-[0.16em] ${color}`}>{label}</div>
        <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-slate-500">{sub}</div>
      </div>
      <div className={`flex items-center gap-2 ${color}`}>
        {align === "left" ? icon : null}
        <div className="text-[34px] font-black leading-none">{value}</div>
        {align === "right" ? icon : null}
      </div>
    </div>
  );
}

function EventIcon({ event }: { event: BattleEvent }) {
  if (event.event_type === "replay.killed") return <Icons.Skull className="h-4 w-4 text-battle-red" />;
  if (event.event_type === "replay.blocked") return <Icons.ShieldCheck className="h-4 w-4 text-battle-green" />;
  if (event.event_type === "replay.blue_blast") return <Icons.Crosshair className="h-4 w-4 text-battle-blue" />;
  if (event.event_type === "judge.verdict") return <Icons.ShieldCheck className="h-4 w-4 text-battle-green" />;
  if (event.event_type === "blue.blocked_red") return <Icons.ShieldX className="h-4 w-4 text-battle-blue" />;
  if (event.event_type === "blue.patch_deployed") return <Icons.Shield className="h-4 w-4 text-battle-blue" />;
  if (event.team === "red") return <Icons.Bug className="h-4 w-4 text-battle-red" />;
  if (event.event_type === "tau.handoff_created") return <Icons.GitBranch className="h-4 w-4 text-battle-purple" />;
  return <Icons.Activity className="h-4 w-4 text-battle-yellow" />;
}

function ReceiptLiveEventText({ event }: { event: BattleEvent }) {
  const prefix = event.ui.notification_prefix;
  const highlight = event.ui.notification_highlight;
  const tone = event.ui.notification_highlight_tone ?? (event.team === "blue" ? "blue" : event.team === "red" ? "red" : "green");
  if (prefix && highlight) {
    return (
      <span className="min-w-0 truncate">
        {prefix}
        <b className={tone}>{highlight}</b>
      </span>
    );
  }
  return <span className="min-w-0 truncate">{event.ui.notification ?? event.summary}</span>;
}


function MockLiveIcon({ icon }: { icon: "rocket" | "shield" | "shield-check" | "bug" }) {
  if (icon === "rocket") return <Icons.Rocket className="leIconSvg" />;
  if (icon === "shield-check") return <Icons.ShieldCheck className="leIconSvg" />;
  if (icon === "shield") return <Icons.Shield className="leIconSvg" />;
  return <Icons.Bug className="leIconSvg" />;
}

function formatSeconds(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--:--";
  const total = Math.max(0, Math.floor(value));
  const min = Math.floor(total / 60).toString().padStart(2, "0");
  const sec = (total % 60).toString().padStart(2, "0");
  return `${min}:${sec}`;
}
