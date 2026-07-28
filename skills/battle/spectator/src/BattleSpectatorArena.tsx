import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Toaster, toast } from "sonner";
import { Button } from "./ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "./ui/sheet";
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
import { BattleProofCardRoute } from "./proof-card/BattleProofCardRoute";
import { BattleProofNav } from "./proof-card/BattleProofNav";
import { isBattleProofCardView } from "./lib/battle-proof-card-registry";
import { BattleSynthesisRoute } from "./synthesis/BattleSynthesisRoute";
import { isBattleSynthesisView } from "./lib/battle-synthesis-registry";
import { BattleCompileRoute } from "./compile/BattleCompileRoute";
import { isBattleCompileView } from "./lib/battle-compile-registry";
import { BattleRuntimeRoute } from "./runtime/BattleRuntimeRoute";
import { isBattleRuntimeView } from "./lib/battle-runtime-registry";
import { BattlePopulationRoute } from "./population/BattlePopulationRoute";
import { isBattlePopulationView } from "./lib/battle-population-registry";
import { isBattleMusicView } from "./lib/battle-music-registry";
import { BattleMusicRoute } from "./music/BattleMusicRoute";
import { BattleGeneticLifecycleBanner } from "./BattleGeneticLifecycleBanner";
import { geneticLifecycleViewModel } from "./lib/battle-genetic-lifecycle";
import { BattleLineageComparisonPanel } from "./lineage/BattleLineageComparisonPanel";
import { BattleCampaignStoryPanel } from "./BattleCampaignStoryPanel";
import { buildCampaignStory, campaignChapterAtPlayhead, soundCaptionForCue } from "./lib/battle-campaign-story";
import { battleCampaignPresentationFromUrl, isBattleCampaignView } from "./lib/battle-campaign-registry";
import { buildBattleRoundIntro } from "./lib/battle-round-intro";
import { BattleRoundStoryIntro } from "./BattleRoundStoryIntro";
import { scoreCaptionForCue, scoreTriggerForEffectCue, scoreTriggerForReceiptBeat } from "./lib/battle-score-bindings";
import { spriteIdForLane } from "./engine/battle-lane-variant-map";
import { BattleLiveTransportBanner } from "./BattleLiveTransportBanner";
import { useBattleLiveTransport } from "./hooks/useBattleLiveTransport";
import { BattleReceiptFooter } from "./BattleReceiptFooter";
import { cn } from "./lib/utils";
import { useBattleSound } from "./hooks/useBattleSound";
import { useBattleScore } from "./hooks/useBattleScore";
import { BattleHeader } from "./BattleHeader";
import { BattleHungerGamesDeathAnnouncement } from "./BattleHungerGamesDeathAnnouncement";
import { hungerGamesDeathCard, type HungerGamesDeathCard } from "./lib/battle-hunger-games-notifications";
import { RaceViewport } from "./RaceViewport";
import { SpectatorRail } from "./SpectatorRail";
import { AgentDetailPane } from "./AgentDetailPane";
import { BattleToolbar } from "./BattleToolbar";
import { Icons } from "./battle-icons";
import type { BattleEvent, BattleNormalizedUxFixture } from "./lib/battle-types";
import "./battle-race.css";
import "./battle-mockup-elements.css";

type BattleFilter = "all" | "red" | "blue" | "useful" | "handoff" | "receipt";

export function BattleSpectatorArena() {
  const [routeEpoch, setRouteEpoch] = useState(0);
  useEffect(() => {
    const onHashChange = () => setRouteEpoch((value) => value + 1);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return <BattleSpectatorArenaContent key={routeEpoch} routeEpoch={routeEpoch} />;
}

function BattleSpectatorArenaContent({ routeEpoch }: { routeEpoch: number }) {
  if (isBattleMusicView()) return <BattleMusicRoute />;
  if (isBattlePopulationView()) return <BattlePopulationRoute />;
  if (isBattleRuntimeView()) return <BattleRuntimeRoute />;
  if (isBattleCompileView()) return <BattleCompileRoute />;
  if (isBattleSynthesisView()) return <BattleSynthesisRoute />;
  if (isBattleProofCardView()) return <BattleProofCardRoute />;

  const { isReceiptRoute, fixture: receiptFixture, error: receiptError, loading: receiptLoading } = useReceiptReplayFixture();
  const liveTransport = useBattleLiveTransport();
  const receiptReplay = isReceiptRoute && !liveTransport.isLiveRoute;
  const liveReplay = liveTransport.isLiveRoute;
  const typedReceiptFixture = (
    liveReplay ? liveTransport.companion : receiptFixture
  ) as BattleNormalizedUxFixture | null;
  const streamReady = !liveReplay || Boolean(typedReceiptFixture);
  const receiptReady = (!receiptReplay || Boolean(typedReceiptFixture)) && streamReady;
  const transportLoading = liveReplay && liveTransport.loading;
  const transportError = liveReplay ? liveTransport.error : null;

  const designView = isBattleDesignView();
  const mockupShell = designView || receiptReplay || liveReplay;
  const receiptChrome = (receiptReplay || liveReplay) && !designView;
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
  const [mode, setMode] = useState("spectator");
  const [query, setQuery] = useState("");
  const [speed, setSpeed] = useState("1x");
  const [playing, setPlaying] = useState(false);
  const [filter, setFilter] = useState<BattleFilter>("all");
  const [leftPaneOpen, setLeftPaneOpen] = useState(true);
  const [rightPaneOpen, setRightPaneOpen] = useState(true);
  const [jsonlOpen, setJsonlOpen] = useState(false);
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [deathAnnouncement, setDeathAnnouncement] = useState<HungerGamesDeathCard | null>(null);
  const [highlightReel, setHighlightReel] = useState(false);
  const [highlightJumpToken, setHighlightJumpToken] = useState(0);
  const deathBeatRef = useRef<string | null>(null);

  useEffect(() => {
    if (!typedReceiptFixture) return;
    if (liveReplay && liveTransport.model?.followLive) {
      const liveSeconds = liveTransport.model.liveSeconds;
      setPlayheadSeconds((prev) => (Math.abs(prev - liveSeconds) < 0.001 ? prev : liveSeconds));
      return;
    }
    if (liveReplay) return;
    setPlayheadSeconds(battleTimelineDomain(typedReceiptFixture, false).currentSeconds);
  }, [typedReceiptFixture, liveReplay, liveTransport.model?.followLive, liveTransport.model?.liveSeconds]);

  useEffect(() => {
    if (!receiptReplay || !receiptReady || !battleHungerGamesDeathDemoFromUrl()) return;
    const lane = initialLanes.find((item) => item.team === "red") ?? initialLanes[0];
    if (!lane) return;
    setDeathAnnouncement(hungerGamesDeathCard(lane, typedReceiptFixture ?? undefined));
  }, [initialLanes, receiptReady, receiptReplay, typedReceiptFixture]);
  const { enabled, arm, play, getContext } = useBattleSound();
  const score = useBattleScore(getContext);

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

  const geneticModel = useMemo(
    () => (typedReceiptFixture ? geneticLifecycleViewModel(typedReceiptFixture) : null),
    [typedReceiptFixture],
  );
  const campaignView = isBattleCampaignView();
  const campaignPresentation = battleCampaignPresentationFromUrl();
  const campaignStory = useMemo(
    () => (campaignView && typedReceiptFixture ? buildCampaignStory(typedReceiptFixture) : null),
    [campaignView, typedReceiptFixture],
  );
  const activeCampaignChapter = useMemo(
    () => campaignChapterAtPlayhead(campaignStory, playheadSeconds),
    [campaignStory, playheadSeconds],
  );
  const [soundCaption, setSoundCaption] = useState<string | null>(null);
  const [roundIntroOpen, setRoundIntroOpen] = useState(() => !battleCampaignPresentationFromUrl().skipIntro);
  const [overturePlaying, setOverturePlaying] = useState(false);
  const roundIntro = useMemo(
    () => (campaignView && typedReceiptFixture ? buildBattleRoundIntro(typedReceiptFixture, campaignStory) : null),
    [campaignStory, campaignView, typedReceiptFixture],
  );
  useEffect(() => {
    setRoundIntroOpen(!campaignPresentation.skipIntro);
    setOverturePlaying(false);
    score.stopAll();
  }, [campaignPresentation.skipIntro, campaignView, score.stopAll, typedReceiptFixture?.battle_id]);
  useEffect(() => () => score.stopAll(), [score.stopAll]);

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
    if (campaignPresentation.mute) return;
    if (beat.react.soundCue && beat.react.soundCue !== "none") {
      playCue(beat.react.soundCue);
      setSoundCaption(soundCaptionForCue(beat.react.soundCue, beat.kind as never));
    }
    const scoreTrigger = scoreTriggerForReceiptBeat(beat);
    if (!scoreTrigger) return;
    if (scoreTrigger.kind === "cue") {
      void score.playCue(scoreTrigger.cueId).then(() => {
        setSoundCaption(scoreCaptionForCue(scoreTrigger.cueId));
      });
      return;
    }
    const lane = initialLanes.find((item) => item.id === beat.laneId);
    const spriteId = lane ? spriteIdForLane(lane, typedReceiptFixture?.sprite_theme) : null;
    if (!spriteId) return;
    void score.playMotif(spriteId).then((ok) => {
      if (ok) setSoundCaption(`Sprite motif (${spriteId}) — entrance receipt.`);
    });
  }, [campaignPresentation.mute, initialLanes, score, typedReceiptFixture?.sprite_theme]);

  const handleReplayCue = useCallback((cue: BattleEffectCue) => {
    if (campaignPresentation.mute) return;
    if (cue.soundCue && cue.soundCue !== "none") {
      playCue(cue.soundCue);
      setSoundCaption(soundCaptionForCue(cue.soundCue));
    }
    const scoreTrigger = scoreTriggerForEffectCue(cue);
    if (!scoreTrigger) return;
    if (scoreTrigger.kind === "cue") {
      void score.playCue(scoreTrigger.cueId).then(() => {
        setSoundCaption(scoreCaptionForCue(scoreTrigger.cueId));
      });
      return;
    }
    const lane = initialLanes.find((item) => item.id === cue.laneId);
    const spriteId = lane ? spriteIdForLane(lane, typedReceiptFixture?.sprite_theme) : null;
    if (!spriteId) return;
    void score.playMotif(spriteId).then((ok) => {
      if (ok) setSoundCaption(`Sprite motif (${spriteId}) — entrance receipt.`);
    });
  }, [campaignPresentation.mute, initialLanes, score, typedReceiptFixture?.sprite_theme]);

  const handlePlayheadSeconds = useCallback((seconds: number) => {
    setPlayheadSeconds(seconds);
  }, []);

  const handleUserScrubSeconds = useCallback(
    (seconds: number) => {
      if (!liveReplay) return;
      liveTransport.scrubToSeconds(seconds);
    },
    [liveReplay, liveTransport.scrubToSeconds],
  );

  const tickerEvents = useMemo(() => {
    if (!receiptReplay || !typedReceiptFixture) return battleEvents;
    return replayTickerEventsForPlayhead(battleEvents, typedReceiptFixture, initialLanes, playheadSeconds);
  }, [battleEvents, initialLanes, playheadSeconds, receiptReplay, typedReceiptFixture]);

  function selectActor(id: string) {
    const exists = initialLanes.some((lane) => lane.id === id);
    if (!exists) return;
    setSelectedId(id);
    if (campaignPresentation.mute) return;
    const lane = initialLanes.find((item) => item.id === id);
    if (!lane) return;
    const spriteId = spriteIdForLane(lane, typedReceiptFixture?.sprite_theme);
    void score.playMotif(spriteId).then((ok) => {
      if (ok) {
        arm();
        setSoundCaption(`Sprite motif (${spriteId}) — actor focus.`);
      }
    });
  }

  function showProof(label: string) {
    toast("Receipt-backed proof", {
      description: label,
      icon: <Icons.FileJson className="h-4 w-4" />
    });
  }

  if ((receiptReplay && receiptLoading) || transportLoading) {
    return <div className="grid h-full place-items-center text-slate-300">{liveReplay ? "Loading live transport package…" : "Loading receipt replay fixture…"}</div>;
  }
  if (receiptReplay && !receiptReady && !receiptLoading && !receiptError) {
    return <div className="grid h-full place-items-center text-red-300">BATTLE RECEIPT BLOCKED: fixture missing</div>;
  }

  if (receiptReplay && receiptError) {
    return <div className="grid h-full place-items-center text-red-300">BATTLE RECEIPT BLOCKED: {receiptError}</div>;
  }

  if (liveReplay && transportError) {
    return (
      <div className="grid h-full place-items-center text-red-300" data-qid="battle:live:blocked">
        BATTLE LIVE TRANSPORT BLOCKED: {transportError.title} — {transportError.detail}
      </div>
    );
  }

  if (liveReplay && !receiptReady && !transportLoading && !transportError) {
    return <div className="grid h-full place-items-center text-red-300">BATTLE LIVE TRANSPORT BLOCKED: companion fixture missing</div>;
  }

  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-hidden text-slate-100", mockupShell ? "battle-mockup-app p-4" : "p-3 2xl:p-4")} style={{ boxSizing: "border-box" }}>
      <Toaster theme="dark" richColors position="top-right" />
      {(receiptReplay || liveReplay || mockupShell) ? <BattleProofNav /> : null}
      {liveTransport.isLiveRoute && (liveTransport.contractModel || liveTransport.model) ? (
        <div className="mx-auto mb-2 max-w-[1672px]">
          <BattleLiveTransportBanner
            mode={liveTransport.mode}
            model={liveTransport.model}
            contractModel={liveTransport.contractModel}
            sseClient={liveTransport.sseClient}
            onReturnToLive={liveTransport.returnToLive}
            onRecover={liveTransport.recoverFromGap}
          />
        </div>
      ) : null}
      {geneticModel ? (
        <div className="mx-auto mb-2 max-w-[1672px]">
          <BattleGeneticLifecycleBanner model={geneticModel} fixture={typedReceiptFixture} />
        </div>
      ) : null}
      {receiptReplay ? (
        <div className="mx-auto mb-2 w-full max-w-[1672px] shrink-0 overflow-y-auto" style={{ maxHeight: "32vh" }} data-qid="battle:adaptive-lineage:panel">
          {typedReceiptFixture ? <BattleLineageComparisonPanel fixture={typedReceiptFixture} sourceBound /> : null}
        </div>
      ) : null}
      {roundIntro && roundIntroOpen ? (
        <div className="mx-auto mb-2 max-w-[1672px]">
          <BattleRoundStoryIntro
            intro={roundIntro}
            audioPlaying={overturePlaying}
            onArmAudio={() => {
              arm();
              void score.playCue("death_clock_overture").then(() => {
                setOverturePlaying(true);
                setSoundCaption(scoreCaptionForCue("death_clock_overture"));
              });
            }}
            onStopAudio={() => {
              score.stopAll();
              setOverturePlaying(false);
              setSoundCaption("Death Clock overture stopped.");
            }}
            onSkip={() => {
              score.stopAll();
              setOverturePlaying(false);
              setRoundIntroOpen(false);
            }}
            onStartArena={() => {
              score.stopAll();
              setOverturePlaying(false);
              setRoundIntroOpen(false);
              setPlaying(true);
              if (!campaignPresentation.mute) {
                void score.startLoop().then(() => {
                  setSoundCaption(scoreCaptionForCue("live_arena_loop"));
                });
              } else {
                setSoundCaption("Arena entered after Death Clock round intro.");
              }
            }}
          />
        </div>
      ) : null}
      {campaignStory ? (
        <div className="mx-auto mb-2 max-w-[1672px]">
          <BattleCampaignStoryPanel
            story={campaignStory}
            activeChapter={activeCampaignChapter}
            soundCaption={soundCaption}
            soundEnabled={enabled}
            reducedMotion={campaignPresentation.reducedMotion}
            particles={campaignPresentation.particles}
            onArmSound={() => {
              arm();
              setSoundCaption("Sound armed for receipt-backed campaign cues.");
            }}
            onSelectChapter={(chapter) => {
              setPlayheadSeconds(chapter.atSeconds);
              setPlaying(false);
              setSoundCaption(chapter.soundCaption);
            }}
          />
        </div>
      ) : null}
      {!mockupShell ? (
        <div className="mx-auto mb-2 w-full max-w-[1920px] shrink-0">
          <BattleToolbar mode={mode} setMode={setMode} filter={filter} setFilter={setFilter} query={query} setQuery={setQuery} />
        </div>
      ) : null}
      <div
        className={cn(
          "mx-auto grid min-h-0 w-full flex-1",
          mockupShell
            ? "battle-mockup-shell"
            : "max-w-[1920px] grid-rows-[142px_minmax(0,1fr)_34px_104px] gap-2.5"
        )}
        style={
          mockupShell
            ? {
                ["--battle-shell-legend-height" as string]: `${BATTLE_MOCKUP_LEGEND_PX}px`,
                ["--battle-shell-footer-height" as string]: `${receiptChrome ? 104 : BATTLE_MOCKUP_FOOTER_PX}px`,
              }
            : { gridTemplateRows: "142px minmax(0, 1fr) 34px 104px" }
        }
      >
        <BattleHeader receiptFixture={typedReceiptFixture} events={tickerEvents} onTestSound={playCue} onSelectActor={selectActor} onOpenJsonl={() => setJsonlOpen(true)} deathAnnouncement={deathAnnouncement} onDismissDeathAnnouncement={() => setDeathAnnouncement(null)} />

        <div
          className={cn(
            "grid min-h-0",
            mockupShell
              ? "battle-mockup-main"
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
          <div className="battle-spectator-rail-slot h-full min-h-0 min-w-0 overflow-hidden">
            <button
              type="button"
              className="battle-pane-toggle battle-pane-toggle-left"
              data-qid="battle:pane:left-toggle"
              data-qs-action="BATTLE_PANE_LEFT_TOGGLE"
              title={leftPaneOpen ? "Collapse left evidence pane" : "Expand left evidence pane"}
              aria-expanded={leftPaneOpen}
              onClick={() => setLeftPaneOpen((value) => !value)}
            >
              {leftPaneOpen ? "Hide" : "Show"}
            </button>
            {leftPaneOpen ? <SpectatorRail receiptFixture={typedReceiptFixture} leaderboard={leaderboard} selectedId={selectedLane?.id} onSelect={selectActor} /> : null}
          </div>
          <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
            <RaceViewport lanes={initialLanes} receiptFixture={typedReceiptFixture} selectedId={selectedLane?.id ?? ""} activeFinisher={null} onSelect={selectActor} query={query} filter={filter} speed={speed} playing={playing} battleEvents={battleEvents} soundEnabled={enabled} onReplayCue={handleReplayCue} onReceiptBeat={handleReceiptBeat} onPlayheadSeconds={handlePlayheadSeconds} onUserScrubSeconds={handleUserScrubSeconds} highlightReel={highlightReel} onHighlightReelChange={setHighlightReel} highlightJumpToken={highlightJumpToken} onPlayingChange={setPlaying} />
          </div>
          {selectedLane ? (
            <div className="battle-agent-pane-slot h-full min-h-0 min-w-0 overflow-hidden">
              <button
                type="button"
                className="battle-pane-toggle battle-pane-toggle-right"
                data-qid="battle:pane:right-toggle"
                data-qs-action="BATTLE_PANE_RIGHT_TOGGLE"
                title={rightPaneOpen ? "Collapse right detail pane" : "Expand right detail pane"}
                aria-expanded={rightPaneOpen}
                onClick={() => setRightPaneOpen((value) => !value)}
              >
                {rightPaneOpen ? "Hide" : "Show"}
              </button>
              {rightPaneOpen ? <AgentDetailPane lane={selectedLane} lanes={initialLanes} events={battleEvents} activeFinisher={null} onSound={playCue} /> : null}
            </div>
          ) : null}
        </div>

        {designView ? (
          <>
            <BattleMockupLegend />
            <BattleMockupFooter playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} filter={filter} setFilter={setFilter} enabled={enabled} arm={arm} highlightReel={highlightReel} onHighlightReelChange={setHighlightReel} onJumpToNextHighlight={() => setHighlightJumpToken((value) => value + 1)} />
          </>
        ) : receiptChrome ? (
          <>
            <BattleMockupLegend />
            <BattleReceiptFooter
              playing={playing}
              setPlaying={setPlaying}
              speed={speed}
              setSpeed={setSpeed}
              filter={filter}
              setFilter={setFilter}
              enabled={enabled}
              arm={arm}
              highlightReel={highlightReel}
              onHighlightReelChange={setHighlightReel}
              onJumpToNextHighlight={() => setHighlightJumpToken((value) => value + 1)}
              receiptStreamButton={
                <>
                  <Button data-qid="battle:control:event:blue-patch" data-qs-action="BATTLE_RECEIPT_PROOF_SELECT" title="Show Blue patch receipt proof" variant="outline" size="sm" className="min-h-11" onClick={() => showProof("Blue worker patch receipts are materialized and receipt-backed.")}><Icons.Shield className="h-4 w-4" /> Blue patch proof</Button>
                  <Button data-qid="battle:control:event:blue-block" data-qs-action="BATTLE_RECEIPT_PROOF_SELECT" title="Show Blue block receipt proof" variant="outline" size="sm" className="min-h-11" onClick={() => showProof("Blue block proof comes only from Judge BLUE_SUCCESS attempts.")}><Icons.ShieldX className="h-4 w-4" /> Blue block proof</Button>
                  <LogSheet open={jsonlOpen} onOpenChange={setJsonlOpen} events={battleEvents} />
                </>
              }
            />
          </>
        ) : null}
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
