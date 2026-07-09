import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Toaster, toast } from "sonner";
import { Button } from "./ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "./ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { battleBluePatchActionsForView, battleEventsForView, battleLanesForView, battleLeaderboardForView } from "./lib/battle-data";
import { replayTickerEventsForPlayhead } from "./lib/battle-replay-cues";
import { battleTimelineDomain } from "./lib/battle-timeline-domain";
import type { BattleEffectCue } from "./lib/battle-types";
import { collectReceiptBeats, receiptBeatsVisibleAtPlayhead, type ReceiptBeat } from "./lib/battle-receipt-beats";
import { isBattleDesignView, mockupDefaultSelectedLaneId } from "./lib/battle-mockup-lanes";
import { isBattleReceiptReplayView } from "./lib/battle-receipt-replay";
import { battleHungerGamesDeathDemoFromUrl } from "./lib/is-battle-hg-death-demo";
import { useReceiptReplayFixture } from "./hooks/useReceiptReplayFixture";
import { BATTLE_MOCKUP_AGENT_PANE_PX, BATTLE_MOCKUP_FOOTER_PX, BATTLE_MOCKUP_LEFT_RAIL_PX, BATTLE_MOCKUP_LEGEND_PX } from "./lib/layout-constants";
import { BattleMockupFooter } from "./BattleMockupFooter";
import { cn } from "./lib/utils";
import { useBattleSound } from "./hooks/useBattleSound";
import { BattleHeader } from "./BattleHeader";
import { BattleHungerGamesDeathAnnouncement } from "./BattleHungerGamesDeathAnnouncement";
import { hungerGamesDeathCard, type HungerGamesDeathCard } from "./lib/battle-hunger-games-notifications";
import { RaceViewport } from "./RaceViewport";
import { SpectatorRail } from "./SpectatorRail";
import { AgentDetailPane } from "./AgentDetailPane";
import { Icons } from "./battle-icons";
import type { BattleEvent, BattleNormalizedUxFixture } from "./lib/battle-types";
import "./battle-race.css";
import "./battle-mockup-elements.css";

type BattleFilter = "all" | "red" | "blue" | "useful" | "receipt";

export function BattleSpectatorArena() {
  const [routeEpoch, setRouteEpoch] = useState(0);
  useEffect(() => {
    const onHashChange = () => setRouteEpoch((value) => value + 1);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const { isReceiptRoute, fixture: receiptFixture, error: receiptError, loading: receiptLoading } = useReceiptReplayFixture();
  const receiptReplay = isReceiptRoute;
  const typedReceiptFixture = receiptFixture as BattleNormalizedUxFixture | null;
  const receiptReady = !receiptReplay || Boolean(typedReceiptFixture);

  const mockupShell = isBattleDesignView() || receiptReplay;
  const initialLanes = useMemo(() => (receiptReady ? battleLanesForView(undefined, typedReceiptFixture) : []), [routeEpoch, receiptReady, typedReceiptFixture]);
  const battleEvents = useMemo(() => (receiptReady ? battleEventsForView(typedReceiptFixture) : []), [routeEpoch, receiptReady, typedReceiptFixture]);
  const leaderboard = useMemo(() => (receiptReady ? battleLeaderboardForView(typedReceiptFixture) : []), [routeEpoch, receiptReady, typedReceiptFixture]);
  useRegisterAction("battle:control:sound-arm", { action: "BATTLE_SOUND_ARM", label: "Arm Battle Sound", description: "Enable local sound cues for receipt-backed Battle events when a cue exists", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:speed", { action: "BATTLE_SPEED_SET", label: "Set Battle Replay Speed", description: "Change the receipt-backed Battle replay speed control", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:focus", { action: "BATTLE_FILTER_SET", label: "Set Battle Focus", description: "Filter receipt-backed Battle lanes.", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:stream:jsonl-open", { action: "BATTLE_JSONL_STREAM_OPEN", label: "Open Receipt Event Stream", description: "Open the receipt-backed Battle event stream sheet", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:sheet:close", { action: "BATTLE_SHEET_CLOSE", label: "Close Battle Sheet", description: "Close the receipt-backed Battle event stream sheet", tags: ["battle", "receipt-backed"] });

  const firstReplayLane = initialLanes.find((lane) => lane.replay)?.id;
  const defaultLaneId = isBattleDesignView() ? mockupDefaultSelectedLaneId() : (firstReplayLane ?? initialLanes[0]?.id ?? "");
  const [selectedId, setSelectedId] = useState(defaultLaneId);
  const [speed, setSpeed] = useState("1x");
  const [playing, setPlaying] = useState(false);
  const [filter, setFilter] = useState<BattleFilter>("all");
  const [jsonlOpen, setJsonlOpen] = useState(false);
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [deathAnnouncement, setDeathAnnouncement] = useState<HungerGamesDeathCard | null>(null);
  const [highlightReel, setHighlightReel] = useState(false);
  const [highlightJumpToken, setHighlightJumpToken] = useState(0);
  const deathBeatRef = useRef<string | null>(null);

  useEffect(() => {
    if (!typedReceiptFixture) return;
    setPlayheadSeconds(battleTimelineDomain(typedReceiptFixture, false).currentSeconds);
  }, [typedReceiptFixture]);

  useEffect(() => {
    if (!receiptReplay || !receiptReady || !battleHungerGamesDeathDemoFromUrl()) return;
    const lane = initialLanes.find((item) => item.team === "red") ?? initialLanes[0];
    if (!lane) return;
    setDeathAnnouncement(hungerGamesDeathCard(lane, typedReceiptFixture ?? undefined));
  }, [initialLanes, receiptReady, receiptReplay, typedReceiptFixture]);
  const { enabled, arm, play } = useBattleSound();

  const selectedLane = useMemo(
    () => initialLanes.find((lane) => lane.id === selectedId) ?? initialLanes[0] ?? null,
    [initialLanes, selectedId],
  );

  useEffect(() => {
    if (!initialLanes.length) return;
    const exists = initialLanes.some((lane) => lane.id === selectedId);
    if (exists) return;
    const firstReplayLane = initialLanes.find((lane) => lane.replay)?.id;
    setSelectedId(firstReplayLane ?? initialLanes[0]?.id ?? "");
  }, [initialLanes, selectedId]);

  function playCue(cue: string) {
    if (!cue || cue === "none") return;
    arm();
    play(cue as never);
  }

  const receiptBeats = useMemo(
    () => (receiptReplay && typedReceiptFixture ? collectReceiptBeats(typedReceiptFixture, initialLanes) : []),
    [initialLanes, receiptReplay, typedReceiptFixture],
  );

  useEffect(() => {
    if (!receiptReplay || !typedReceiptFixture) return;
    const beat = receiptBeatsVisibleAtPlayhead(receiptBeats, playheadSeconds, 1).at(-1) ?? null;
    const showDeath = Boolean(beat?.react.deathCard && playheadSeconds + 0.05 >= beat.atSeconds);
    if (!showDeath) {
      if (deathBeatRef.current !== null) {
        deathBeatRef.current = null;
        setDeathAnnouncement(null);
      }
      return;
    }
    if (deathBeatRef.current === beat!.id) return;
    deathBeatRef.current = beat!.id;
    const lane = initialLanes.find((item) => item.id === beat!.laneId);
    if (!lane) return;
    setDeathAnnouncement(hungerGamesDeathCard(lane, typedReceiptFixture));
  }, [initialLanes, playheadSeconds, receiptBeats, receiptReplay, typedReceiptFixture]);

  const handleReceiptBeat = useCallback((beat: ReceiptBeat) => {
    if (beat.react.soundCue && beat.react.soundCue !== "none") playCue(beat.react.soundCue);
  }, []);

  const handleReplayCue = useCallback((cue: BattleEffectCue) => {
    if (cue.soundCue && cue.soundCue !== "none") playCue(cue.soundCue);
  }, []);

  const tickerEvents = useMemo(() => {
    if (!receiptReplay || !typedReceiptFixture) return battleEvents;
    return replayTickerEventsForPlayhead(battleEvents, typedReceiptFixture, initialLanes, playheadSeconds);
  }, [battleEvents, initialLanes, playheadSeconds, receiptReplay, typedReceiptFixture]);

  function selectActor(id: string) {
    const exists = initialLanes.some((lane) => lane.id === id);
    if (exists) setSelectedId(id);
  }

  function showProof(label: string) {
    toast("Receipt-backed proof", {
      description: label,
      icon: <Icons.FileJson className="h-4 w-4" />
    });
  }

  if (receiptReplay && receiptLoading) {
    return <div className="grid h-full place-items-center text-slate-300">Loading receipt replay fixture…</div>;
  }
  if (receiptReplay && !receiptReady && !receiptLoading && !receiptError) {
    return <div className="grid h-full place-items-center text-red-300">BATTLE RECEIPT BLOCKED: fixture missing</div>;
  }

  if (receiptReplay && receiptError) {
    return <div className="grid h-full place-items-center text-red-300">BATTLE RECEIPT BLOCKED: {receiptError}</div>;
  }

  return (
    <div className={cn("h-full min-h-0 overflow-hidden text-slate-100", mockupShell ? "battle-mockup-app p-4" : "p-3 2xl:p-4")}>
      <Toaster theme="dark" richColors position="top-right" />
      <div
        className={cn(
          "mx-auto grid h-full min-h-0",
          mockupShell
            ? "battle-mockup-shell max-w-[1672px] gap-2.5"
            : "max-w-[1920px] grid-rows-[142px_minmax(0,1fr)_34px_56px] gap-2.5"
        )}
        style={
          mockupShell
            ? {
                gridTemplateRows: `auto minmax(0, 1fr) ${BATTLE_MOCKUP_LEGEND_PX}px ${BATTLE_MOCKUP_FOOTER_PX}px`,
              }
            : undefined
        }
      >
        <BattleHeader receiptFixture={typedReceiptFixture} events={tickerEvents} onTestSound={playCue} onSelectActor={selectActor} onOpenJsonl={() => setJsonlOpen(true)} deathAnnouncement={deathAnnouncement} onDismissDeathAnnouncement={() => setDeathAnnouncement(null)} />

        <div
          className={cn(
            "grid min-h-0",
            mockupShell
              ? "battle-mockup-main grid-cols-[var(--battle-left-rail)_minmax(0,1fr)_var(--battle-agent-pane)] gap-2.5"
              : "grid-cols-[240px_minmax(0,1fr)_385px] gap-3"
          )}
          style={
            mockupShell
              ? {
                  ["--battle-left-rail" as string]: `${BATTLE_MOCKUP_LEFT_RAIL_PX}px`,
                  ["--battle-agent-pane" as string]: `${BATTLE_MOCKUP_AGENT_PANE_PX}px`,
                }
              : undefined
          }
        >
          <SpectatorRail receiptFixture={typedReceiptFixture} leaderboard={leaderboard} selectedId={selectedLane?.id} onSelect={selectActor} />
          <RaceViewport lanes={initialLanes} receiptFixture={typedReceiptFixture} selectedId={selectedLane?.id ?? ""} activeFinisher={null} onSelect={selectActor} query="" filter={filter} speed={speed} playing={playing} battleEvents={battleEvents} soundEnabled={enabled} onReplayCue={handleReplayCue} onReceiptBeat={handleReceiptBeat} onPlayheadSeconds={setPlayheadSeconds} highlightReel={highlightReel} onHighlightReelChange={setHighlightReel} highlightJumpToken={highlightJumpToken} onPlayingChange={setPlaying} />
          {selectedLane ? <AgentDetailPane lane={selectedLane} lanes={initialLanes} events={battleEvents} activeFinisher={null} onSound={playCue} /> : null}
        </div>

        {mockupShell ? (
          <>
            <BattleMockupLegend />
            <BattleMockupFooter playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} filter={filter} setFilter={setFilter} enabled={enabled} arm={arm} highlightReel={highlightReel} onHighlightReelChange={setHighlightReel} onJumpToNextHighlight={() => setHighlightJumpToken((value) => value + 1)} />
          </>
        ) : (
          <>
        <div className="battle-footer-legend flex min-h-[34px] items-center gap-4 rounded-xl border border-white/10 bg-[rgba(3,8,15,.45)] px-4 py-1.5 text-[10.5px] font-semibold text-slate-400"><span className="battle-label mr-1">Legend</span><span className="inline-flex items-center gap-1.5 text-battle-red"><Icons.Bug className="h-3.5 w-3.5" /><span className="text-slate-400">Exploit progress</span></span><span className="inline-flex items-center gap-1.5 text-battle-blue"><Icons.ShieldX className="h-3.5 w-3.5" /><span className="text-slate-400">Blue intervention / block</span></span><span className="inline-flex items-center gap-1.5 text-battle-yellow"><Icons.Lightbulb className="h-3.5 w-3.5" /><span className="text-slate-400">Useful signal</span></span><span className="inline-flex items-center gap-1.5 text-battle-green"><Icons.FileJson className="h-3.5 w-3.5" /><span className="text-slate-400">Receipt-backed proof</span></span></div>
        <footer className="flex min-h-[56px] items-center justify-between gap-3 rounded-2xl border border-white/10 bg-battle-panel/80 px-3 py-2 shadow-acrylic backdrop-blur-xl">
          <div className="flex min-w-0 items-center gap-3">
            <Button data-qid="battle:control:playhead" data-qs-action="BATTLE_REPLAY_PLAYHEAD_TOGGLE" title={playing ? "Pause receipt replay playhead" : "Play receipt replay playhead"} variant={playing ? "green" : "outline"} size="icon" className="min-h-11 min-w-11" onClick={() => setPlaying((value) => !value)}>
              {playing ? <Icons.Pause className="h-4 w-4" /> : <Icons.Play className="h-4 w-4" />}
            </Button>
            <Button data-qid="battle:control:highlight-next" data-qs-action="BATTLE_HIGHLIGHT_NEXT" title="Jump playhead to next receipt-backed highlight" variant="outline" size="sm" className="min-h-11" onClick={() => setHighlightJumpToken((value) => value + 1)}>Next highlight</Button>
            <Button data-qid="battle:control:highlight-reel" data-qs-action="BATTLE_HIGHLIGHT_REEL_TOGGLE" title={highlightReel ? "Disable highlight-reel transport" : "Play highlight reel (jump between proven terminal beats)"} variant={highlightReel ? "green" : "outline"} size="sm" className="min-h-11" onClick={() => setHighlightReel((value) => !value)}>{highlightReel ? "Highlights on" : "Highlights"}</Button>
            <span className="battle-label mr-2 hidden sm:inline">Spectator mode</span><Button data-qid="battle:control:sound-arm" data-qs-action="BATTLE_SOUND_ARM" title="Arm sound for receipt-backed events with explicit cues" variant="outline" size="sm" className="min-h-11" onClick={arm}>
              <Icons.Eye className="h-4 w-4" /> Spectator mode <span className={enabled ? "text-battle-green" : "text-slate-500"}>{enabled ? "LIVE" : "click to arm"}</span>
            </Button>
            <span className="battle-label mr-2 hidden sm:inline">Speed</span><ToggleGroup className="min-h-11" data-qid="battle:control:speed" data-qs-action="BATTLE_SPEED_SET" title="Set receipt-backed replay speed" type="single" value={speed} onValueChange={(value) => value && setSpeed(value)}>
              {["1x", "2x", "4x", "8x"].map((item) => (
                <ToggleGroupItem key={item} data-qid={`battle:control:speed:${item}`} data-qs-action="BATTLE_SPEED_SET" title={`Set replay speed to ${item}`} value={item} className="h-11 min-h-11 min-w-11 px-3">{item}</ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>

          <div className="flex min-w-0 flex-1 items-center justify-center gap-2">
            <span className="battle-label mr-2">Focus</span>
            {[
              ["all", "All Lanes"],
              ["red", "Red Team"],
              ["blue", "Blue Team"],
              ["useful", "Useful"],
              ["receipt", "Receipts"]
            ].map(([id, label]) => (
              <Button
                key={id}
                data-qid={`battle:toolbar:filter:${id}`}
                data-qs-action="BATTLE_FILTER_SET"
                title={`Focus ${label}`}
                variant={filter === id ? "green" : "outline"}
                size="sm"
                className="min-h-11"
                onClick={() => setFilter(id as BattleFilter)}
              >
                {label}
              </Button>
            ))}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button data-qid="battle:control:event:blue-patch" data-qs-action="BATTLE_RECEIPT_PROOF_SELECT" title="Show Blue patch receipt proof" variant="outline" size="sm" className="min-h-11" onClick={() => showProof("Blue worker patch receipts are materialized and receipt-backed.")}><Icons.Shield className="h-4 w-4" /> Blue patch proof</Button>
            <Button data-qid="battle:control:event:blue-block" data-qs-action="BATTLE_RECEIPT_PROOF_SELECT" title="Show Blue block receipt proof" variant="outline" size="sm" className="min-h-11" onClick={() => showProof("Blue block proof comes only from Judge BLUE_SUCCESS attempts.")}><Icons.ShieldX className="h-4 w-4" /> Blue block proof</Button>
            <LogSheet open={jsonlOpen} onOpenChange={setJsonlOpen} events={battleEvents} />
          </div>
        </footer>
          </>
        )}
      </div>
    </div>
  );
}


function BattleMockupLegend() {
  return (
    <div className="footerLegend">
      <b>LEGEND:</b>
      <span style={{ color: "var(--battle-red, #ff4d5c)" }}>— Exploit Progress</span>
      <span style={{ color: "var(--battle-blue, #5aadff)" }}>
        <Icons.Shield className="h-3 w-3" /> Blue Intervention
      </span>
      <span>
        <Icons.ShieldX className="h-3 w-3 text-battle-blue" /> Blocked (Handoff)
      </span>
      <span style={{ color: "var(--battle-red, #ff4d5c)" }}>
        <Icons.Skull className="h-3 w-3" /> Killed
      </span>
      <span style={{ color: "var(--battle-yellow, #ffd24d)" }}>
        <Icons.Lightbulb className="h-3 w-3" /> Useful Signal
      </span>
      <span style={{ color: "var(--battle-green, #3cf07a)" }}>
        <Icons.ShieldCheck className="h-3 w-3" /> Promoted / Survivor
      </span>
      <span style={{ color: "var(--battle-green, #3cf07a)" }}>
        <Icons.Rocket className="h-3 w-3" /> Fastest Crash
      </span>
    </div>
  );
}

function LogSheet({ open, onOpenChange, events }: { open: boolean; onOpenChange: (open: boolean) => void; events: BattleEvent[] }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <Button data-qid="battle:stream:jsonl-open" data-qs-action="BATTLE_JSONL_STREAM_OPEN" title="Open receipt-backed event stream" variant="outline" size="sm" className="min-h-11"><Icons.FileJson className="h-4 w-4" /> Receipt stream</Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Receipt-backed BATTLE-004 events</SheetTitle>
        </SheetHeader>
        <p className="mb-4 text-sm text-slate-400">Static adapter output from BATTLE-004 worker-matrix receipts. No live stream, Blue kill, fastest crash, promotion, or child spawn is synthesized.</p>
        <div className="space-y-3 overflow-auto pb-10">
          {events.map((event: BattleEvent) => (
            <pre key={event.id} className="overflow-auto rounded-xl border border-white/10 bg-black/35 p-3 text-xs leading-5 text-slate-300">{JSON.stringify(event, null, 2)}</pre>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
