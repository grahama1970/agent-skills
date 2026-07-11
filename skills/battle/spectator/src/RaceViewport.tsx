import { useMemo, useEffect, useState, useRef, useCallback, type ReactNode } from "react";
import type { BlueFinisherState, Lane } from "./lib/battle-types";
import { activeBattleFixture, battleBluePatchActionsForView } from "./lib/battle-data";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { isBattleReceiptReplayView, lanesVisibleAtPlayhead, secondsFromOverlayTrackPointer, secondsFromTimelinePointer } from "./lib/battle-receipt-replay";
import { isBattleLiveView } from "./lib/battle-transport-registry";
import { mockupAllottedSeconds, mockupBlueStripStats, mockupClockFromTrackPct, mockupOverviewMarks, mockupPlayheadSeconds, mockupTimelineTicks } from "./lib/mockup-design-fixture";
import { BlueControlStrip } from "./BlueControlStrip";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Icons } from "./battle-icons";
import { LaneRow } from "./LaneRow";
import { BattleLineageFlow } from "./BattleLineageFlow";
import { BattlePlayheadCursor } from "./BattlePlayheadCursor";
import { BattleTimelineAxis } from "./BattleTimelineAxis";
import { BattleTimelineProvider, useBattleTimelineScale } from "./BattleTimelineProvider";
import { TimelineOverview } from "./TimelineOverview";
import { warnMarkerOverlaps } from "./lib/verify-lane-marker-layout";
import {
  clampTimelineZoom,
  overviewMarksFromLanes,
  stepTimelineZoom,
  TIMELINE_ZOOM_DEFAULT,
  timelineContentWidth,
  overviewViewportStyle,
  playheadLeftPx,
  scrollLeftForPlayhead,
} from "./lib/timeline-playback";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { cn } from "./lib/utils";
import { isBattlePixiEngine } from "./lib/is-battle-pixi-engine";
import { activeReceiptBeatAtPlayhead, receiptBeatToEffectCue, type ReceiptBeat } from "./lib/battle-receipt-beats";
import { useBattleReceiptDirector } from "./hooks/useBattleReceiptDirector";
import { battlePixiTestModeFromUrl } from "./lib/is-battle-pixi-test-mode";
import { buildRaceEngineInput, buildRaceEngineRowLayout } from "./lib/build-race-engine-input";
import { battleTimelineDomain } from "./lib/battle-timeline-domain";
import type { BattleEffectCue, BattleEvent } from "./lib/battle-types";
import { BattleRacePixiSpike } from "./engine/BattleRacePixiSpike";

export type RaceViewportFilter = "all" | "useful" | "blue" | "receipt" | "red" | "handoff";

type Props = {
  lanes: Lane[];
  receiptFixture?: import("./lib/battle-types").BattleNormalizedUxFixture | null;
  selectedId: string;
  activeFinisher?: BlueFinisherState | null;
  onSelect: (id: string) => void;
  query: string;
  filter?: RaceViewportFilter | string;
  speed?: string;
  playing?: boolean;
  battleEvents?: BattleEvent[];
  soundEnabled?: boolean;
  onReplayCue?: (cue: BattleEffectCue) => void;
  onReceiptBeat?: (beat: ReceiptBeat) => void;
  onPlayheadSeconds?: (seconds: number) => void;
  onUserScrubSeconds?: (seconds: number) => void;
  highlightReel?: boolean;
  onHighlightReelChange?: (enabled: boolean) => void;
  highlightJumpToken?: number;
  onPlayingChange?: (playing: boolean) => void;
};

export function RaceViewport({ lanes, receiptFixture, selectedId, activeFinisher, onSelect, query, filter = "all", speed = "1x", playing = false, battleEvents = [], soundEnabled = false, onReplayCue, onReceiptBeat, onPlayheadSeconds, onUserScrubSeconds, highlightReel = false, onHighlightReelChange, highlightJumpToken = 0, onPlayingChange }: Props) {
  useRegisterAction("battle:timeline:scroll", { action: "BATTLE_TIMELINE_SCROLL", label: "Scroll Battle Timeline", description: "Scroll the receipt-backed Battle timeline horizontally.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:timeline:zoom", { action: "BATTLE_TIMELINE_ZOOM", label: "Zoom Battle Timeline", description: "Adjust the Battle timeline zoom.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:timeline:zoom:out", { action: "BATTLE_TIMELINE_ZOOM", label: "Zoom Battle Timeline Out", description: "Zoom the Battle timeline out.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:timeline:zoom:in", { action: "BATTLE_TIMELINE_ZOOM", label: "Zoom Battle Timeline In", description: "Zoom the Battle timeline in.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:marker:select", { action: "BATTLE_MARKER_SELECT", label: "Select Battle Lane Marker", description: "Select the Battle lane associated with a timeline marker.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:lane:select", { action: "BATTLE_LANE_SELECT", label: "Select Battle Lane", description: "Select a Battle lane on the race timeline.", tags: ["battle", "timeline"] });
  useRegisterAction("battle:lane:collapse", { action: "BATTLE_LANE_COLLAPSE", label: "Toggle Battle Lane Children", description: "Expand or collapse child lanes for a parent Battle lane.", tags: ["battle", "timeline"] });

  const [zoom, setZoom] = useState(1);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set(lanes.filter((lane) => lane.children?.length && lane.expanded === false).map((lane) => lane.id)));
  const designView = isBattleDesignView();
  const receiptReplay = isBattleReceiptReplayView() || isBattleLiveView();
  const pixiEngine = isBattlePixiEngine();
  const fixture = useMemo(
    () => activeBattleFixture(receiptFixture ?? undefined),
    [receiptReplay, designView, receiptFixture, typeof window !== "undefined" ? window.location.hash : ""],
  );
  const timeline = fixture.timeline;
  const clock = fixture.battle_clock;
  const timelineDomain = useMemo(() => battleTimelineDomain(fixture, designView), [designView, fixture]);
  const allotted = timelineDomain.allottedSeconds;
  const testModeFromUrl = battlePixiTestModeFromUrl();
  const [playheadSeconds, setPlayheadSeconds] = useState(() => testModeFromUrl?.currentSeconds ?? timelineDomain.currentSeconds);

  useEffect(() => {
    const testMode = battlePixiTestModeFromUrl();
    setPlayheadSeconds(testMode?.currentSeconds ?? timelineDomain.currentSeconds);
  }, [timelineDomain.currentSeconds, receiptReplay, typeof window !== "undefined" ? window.location.hash : ""]);

  const effectivePlayheadSeconds = testModeFromUrl?.freezeTime ? testModeFromUrl.currentSeconds : playheadSeconds;

  useEffect(() => {
    onPlayheadSeconds?.(effectivePlayheadSeconds);
  }, [effectivePlayheadSeconds, onPlayheadSeconds]);


  const [scrollMetrics, setScrollMetrics] = useState({ scrollLeft: 0, scrollWidth: 0, viewportWidth: 0 });
  const scrollRef = useRef<HTMLDivElement>(null);
  const lanesContainerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const rowRefCallbacks = useRef<Map<string, (node: HTMLDivElement | null) => void>>(new Map());
  const getRowRef = useCallback((laneId: string) => {
    if (!rowRefCallbacks.current.has(laneId)) {
      rowRefCallbacks.current.set(laneId, (node) => {
        if (node) rowRefs.current.set(laneId, node);
        else rowRefs.current.delete(laneId);
      });
    }
    return rowRefCallbacks.current.get(laneId)!;
  }, []);

  const selectedLane = lanes.find((lane) => lane.id === selectedId);
  const childIds = useMemo(() => new Set(lanes.filter((lane) => lane.parentId).map((lane) => lane.id)), [lanes]);
  const lineageLanes = useMemo(() => {
    if (!receiptReplay) return lanes;
    return lanesVisibleAtPlayhead(lanes, fixture, effectivePlayheadSeconds);
  }, [effectivePlayheadSeconds, fixture, lanes, receiptReplay]);

  const visibleLanes = useMemo(() => {
    const q = query.trim().toLowerCase();
    return lineageLanes.filter((lane) => {
      if (lane.parentId && collapsed.has(lane.parentId)) return false;
      const queryMatch =
        !q ||
        [lane.name, lane.payloadId, lane.runnerState, lane.mutationRationale, ...(lane.inheritedContext ?? [])]
          .join(" ")
          .toLowerCase()
          .includes(q);
      const filterMatch =
        filter === "all" ||
        (filter === "red" && lane.team === "red") ||
        (filter === "useful" && lane.events.some((event) => event.kind === "useful")) ||
        (filter === "blue" && lane.events.some((event) => event.kind === "blue_blast" || event.kind === "blocked")) ||
        (filter === "receipt" && lane.events.some((event) => event.proven)) ||
        (filter === "handoff" && lane.events.some((event) => event.kind === "handoff"));
      return queryMatch && filterMatch;
    });
  }, [lineageLanes, query, filter, collapsed]);

  const layoutKey = `${visibleLanes.map((lane) => lane.id).join(",")}|${zoom}|${[...collapsed].sort().join(",")}`;
  const contentWidth = timelineContentWidth(zoom);
  const ticks = designView ? mockupTimelineTicks() : buildTicks({ maxX: timeline?.max_x ?? 100, allotted });
  const playheadLeft = playheadLeftPx(playheadSeconds, allotted, contentWidth);
  const playheadPct = contentWidth ? (playheadLeft / contentWidth) * 100 : 0;
  const overviewMarks = useMemo(
    () => (designView ? mockupOverviewMarks() : overviewMarksFromLanes(lanes, allotted)),
    [designView, lanes, allotted],
  );
  const overviewTrackWidth = Math.max(120, scrollMetrics.viewportWidth - 280);
  const overviewViewport = overviewViewportStyle({
    scrollLeft: scrollMetrics.scrollLeft,
    scrollWidth: scrollMetrics.scrollWidth,
    viewportWidth: scrollMetrics.viewportWidth,
    trackWidth: overviewTrackWidth,
  });
  const maxScroll = Math.max(0, scrollMetrics.scrollWidth - scrollMetrics.viewportWidth);
  const showScrollHint = maxScroll > 8 && scrollMetrics.scrollLeft < maxScroll - 8;

  const syncScrollMetrics = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    setScrollMetrics({
      scrollLeft: node.scrollLeft,
      scrollWidth: node.scrollWidth,
      viewportWidth: node.clientWidth,
    });
  }, []);


  const scrubPlayheadFromClientX = useCallback(
    (clientX: number, trackRect: DOMRect, mode: "overlay" | "timeline") => {
      if (receiptReplay && fixture.battle_timeline_control?.controls?.can_scrub === false) return;
      const next =
        mode === "overlay"
          ? secondsFromOverlayTrackPointer(clientX, trackRect, allotted)
          : secondsFromTimelinePointer(
              clientX,
              trackRect,
              scrollRef.current?.scrollLeft ?? scrollMetrics.scrollLeft,
              contentWidth,
              allotted,
            );
      setPlayheadSeconds(next);
      onUserScrubSeconds?.(next);
    },
    [allotted, contentWidth, fixture.battle_timeline_control?.controls?.can_scrub, onUserScrubSeconds, receiptReplay, scrollMetrics.scrollLeft],
  );

  const onOverlayScrubPointer = useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      if (!receiptReplay && !designView) return;
      scrubPlayheadFromClientX(event.clientX, event.currentTarget.getBoundingClientRect(), "overlay");
    },
    [designView, receiptReplay, scrubPlayheadFromClientX],
  );

  const onTimelineScrubPointer = useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      if (!receiptReplay && !designView) return;
      scrubPlayheadFromClientX(event.clientX, event.currentTarget.getBoundingClientRect(), receiptReplay ? "overlay" : "timeline");
    },
    [designView, receiptReplay, scrubPlayheadFromClientX],
  );

  const followPlayhead = useCallback(
    (behavior: ScrollBehavior = playing ? "auto" : "smooth") => {
      const node = scrollRef.current;
      if (!node) return;
      const nextLeft = scrollLeftForPlayhead({
        playheadLeft: playheadLeftPx(playheadSeconds, allotted, contentWidth),
        viewportWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
      });
      if (Math.abs(node.scrollLeft - nextLeft) > 1) node.scrollTo({ left: nextLeft, behavior });
      syncScrollMetrics();
    },
    [allotted, contentWidth, playheadSeconds, playing, syncScrollMetrics]
  );

  const focusTimelineAtSeconds = useCallback(
    (seconds: number, behavior: ScrollBehavior = "smooth") => {
      const node = scrollRef.current;
      if (!node) return;
      const left = scrollLeftForPlayhead({
        playheadLeft: playheadLeftPx(seconds, allotted, contentWidth),
        viewportWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
      });
      if (Math.abs(node.scrollLeft - left) > 1) node.scrollTo({ left, behavior });
      syncScrollMetrics();
    },
    [allotted, contentWidth, syncScrollMetrics],
  );

  const director = useBattleReceiptDirector({
    fixture,
    lanes,
    playheadSeconds: effectivePlayheadSeconds,
    enabled: receiptReplay && !testModeFromUrl?.freezeTime,
    handlers: {
      onBeat: (beat) => {
        onReceiptBeat?.(beat);
        onReplayCue?.(receiptBeatToEffectCue(beat));
      },
      focusCamera: (beat, behavior = "smooth") => {
        if (!pixiEngine || !receiptReplay) return;
        focusTimelineAtSeconds(beat.camera.focusSeconds, behavior);
        onSelect(beat.laneId);
      },
    },
  });

  const receiptBeatForPlayhead = useMemo(
    () => activeReceiptBeatAtPlayhead(director.beats, effectivePlayheadSeconds, director.activeBeat),
    [director.activeBeat, director.beats, effectivePlayheadSeconds],
  );

  useEffect(() => {
    if (!highlightJumpToken) return;
    const jump = director.jumpToNextHighlight(effectivePlayheadSeconds);
    if (!jump) return;
    const preSeconds = jump.beat.camera.focusSeconds - jump.preRollSeconds;
    setPlayheadSeconds(preSeconds);
    focusTimelineAtSeconds(preSeconds, "auto");
    window.setTimeout(() => {
      setPlayheadSeconds(jump.beat.camera.focusSeconds);
      focusTimelineAtSeconds(jump.beat.camera.focusSeconds, "smooth");
    }, jump.beat.camera.preRollMs);
  }, [director, effectivePlayheadSeconds, focusTimelineAtSeconds, highlightJumpToken]);

  useEffect(() => {
    if (!playing || !highlightReel || !receiptReplay) return;
    const beats = director.heroBeats;
    if (!beats.length) return;
    const multiplier = Number.parseFloat(speed) || 1;
    let idx = beats.findIndex((beat) => beat.atSeconds >= effectivePlayheadSeconds - 0.15);
    if (idx < 0) idx = 0;
    let cancelled = false;
    let timer: number | undefined;

    const jumpTo = (beatIndex: number) => {
      if (cancelled) return;
      const beat = beats[beatIndex];
      if (!beat) {
        onPlayingChange?.(false);
        return;
      }
      const preRollMs = beat.camera.preRollMs / multiplier;
      const postRollMs = beat.camera.postRollMs / multiplier;
      const preSeconds = beat.camera.focusSeconds - beat.camera.preRollMs / 1000;
      setPlayheadSeconds(preSeconds);
      focusTimelineAtSeconds(preSeconds, "auto");
      onSelect(beat.laneId);
      timer = window.setTimeout(() => {
        if (cancelled) return;
        setPlayheadSeconds(beat.camera.focusSeconds);
        focusTimelineAtSeconds(beat.camera.focusSeconds, "smooth");
        timer = window.setTimeout(() => {
          if (cancelled) return;
          jumpTo(beatIndex + 1);
        }, postRollMs);
      }, preRollMs);
    };

    jumpTo(idx);
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [director.heroBeats, effectivePlayheadSeconds, focusTimelineAtSeconds, highlightReel, onPlayingChange, onSelect, playing, receiptReplay, speed]);

  useEffect(() => {
    if (!playing || highlightReel) return;
    const multiplier = Number.parseFloat(speed) || 1;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setPlayheadSeconds((value) => {
        const next = value + dt * multiplier;
        return next >= allotted ? 0 : next;
      });
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [allotted, playing, speed]);

  useEffect(() => {
    followPlayhead(playing ? "auto" : "smooth");
  }, [playheadSeconds, contentWidth, playing, followPlayhead]);

  useEffect(() => {
    syncScrollMetrics();
    const node = scrollRef.current;
    if (!node) return;
    const onScroll = () => {
      syncScrollMetrics();
      if (receiptReplay && pixiEngine) director.pauseCameraFollow();
    };
    node.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", syncScrollMetrics);
    followPlayhead("auto");
    return () => {
      node.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", syncScrollMetrics);
    };
  }, [contentWidth, director.pauseCameraFollow, pixiEngine, receiptReplay, visibleLanes.length, followPlayhead, syncScrollMetrics]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      setZoom((value) => stepTimelineZoom(value, event.deltaY < 0 ? 1 : -1));
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    const container = lanesContainerRef.current;
    if (!container) return;
    const id = window.requestAnimationFrame(() => warnMarkerOverlaps(container));
    return () => window.cancelAnimationFrame(id);
  }, [visibleLanes, zoom, collapsed]);

  const scoreboard = fixture.scoreboard;
  const blockCount = useMemo(() => lanes.filter((lane) => lane.events.some((event) => event.kind === "blocked" || event.kind === "blue_blast")).length, [lanes]);

  const mockupBlue = mockupBlueStripStats();

  const pixiRowLayout = useMemo(() => buildRaceEngineRowLayout(visibleLanes), [visibleLanes]);
  const pixiEngineInput = useMemo(
    () =>
      buildRaceEngineInput({
        lanes: visibleLanes,
        selectedLaneId: selectedId || null,
        zoom,
        currentSeconds: effectivePlayheadSeconds,
        allottedSeconds: allotted,
        fixture,
        onSelectLane: onSelect,
        onSelectEvent: (eventId) => {
          const lane = visibleLanes.find((item) => item.events.some((event) => event.id === eventId));
          if (lane) onSelect(lane.id);
        },
        onEffectCue: onReplayCue,
        activeReceiptBeat: receiptBeatForPlayhead,
      }),
    [allotted, effectivePlayheadSeconds, fixture, onReplayCue, onSelect, receiptBeatForPlayhead, selectedId, visibleLanes, zoom],
  );
  const pixiRowsHeight = useMemo(
    () => pixiRowLayout.reduce((max, row) => Math.max(max, row.topPx + row.heightPx), 0),
    [pixiRowLayout],
  );

  const shellClass = cn(
    "flex min-h-0 flex-1 flex-col overflow-hidden",
    designView ? "center battle-mockup-panel battle-mockup-center" : cn("rounded-2xl border-battle-cyan/20", receiptReplay && "justify-start"),
  );

  const timelineBody = (
    <>
      <BattleTimelineAxis ticks={ticks} allottedSeconds={allotted} />
      <div ref={lanesContainerRef} className={designView ? cn("rows", pixiEngine && "pixiRowsHost") : cn("relative", receiptReplay ? (pixiEngine ? "battle-receipt-pixi-rows" : "min-h-0") : "min-h-[calc(100%-2.25rem)]")}>
        {!designView ? <BattlePlayheadCursor playheadSeconds={playheadSeconds} /> : null}
        {visibleLanes.map((lane) => (
          <LaneRow
            ref={getRowRef(lane.id)}
            key={lane.id}
            lane={lane}
            hasChildren={Boolean(lane.children?.length)}
            isCollapsed={collapsed.has(lane.id)}
            isChild={childIds.has(lane.id)}
            onToggleCollapse={() =>
              setCollapsed((previous) => {
                const next = new Set(previous);
                if (next.has(lane.id)) next.delete(lane.id);
                else next.add(lane.id);
                return next;
              })
            }
            isSelected={lane.id === selectedId}
            isDimmed={Boolean(selectedId && selectedLane && lane.id !== selectedId)}
            activeFinisher={activeFinisher}
            onSelect={onSelect}
            allottedSeconds={allotted}
            hideTrack={pixiEngine}
          />
        ))}
        {(!pixiEngine || designView) ? (
          <BattleLineageFlow
            lanes={lanes}
            visibleLaneIds={visibleLanes.map((lane) => lane.id)}
            collapsed={collapsed}
            containerRef={lanesContainerRef}
            rowRefs={rowRefs}
            layoutKey={layoutKey}
          />
        ) : null}
        {pixiEngine ? (
          <BattleRacePixiSpike
            lanes={visibleLanes}
            rowLayout={pixiRowLayout}
            input={pixiEngineInput}
            contentWidth={contentWidth}
            allottedSeconds={allotted}
            scrollLeft={scrollMetrics.scrollLeft}
            onScrollLeftChange={(left) => {
              const node = scrollRef.current;
              if (!node) return;
              node.scrollLeft = left;
              syncScrollMetrics();
            }}
            heightPx={pixiRowsHeight}
            playing={playing}
            collapsedParentIds={collapsed}
          />
        ) : null}
      </div>
      {(designView || receiptReplay) ? (
        <div className="playheadOverlay" aria-hidden="true">
          <div />
          <div
            className="playheadTrack"
            data-qid="battle:timeline:scrub"
            onClick={onOverlayScrubPointer}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") setPlayheadSeconds((value) => Math.max(0, value - 1));
              if (event.key === "ArrowRight") setPlayheadSeconds((value) => Math.min(allotted, value + 1));
            }}
            role="slider"
            tabIndex={0}
            aria-valuemin={0}
            aria-valuemax={allotted}
            aria-valuenow={playheadSeconds}
            aria-label="Battle timeline playhead scrub"
          >
            <BattlePlayheadCursor playheadSeconds={playheadSeconds} />
          </div>
        </div>
      ) : null}
    </>
  );

  const timelineChrome = (
    <>
      {(designView || receiptReplay) ? (
        <div className="graphTitleBar">
          Evolution &amp; Progress Graph
          <span className="zoomHint">· Zoom <span id="zoomState">{Math.round(zoom * 100)}%</span></span>
          <div className="zoomBtns">
            <button type="button" className="zoomBtn min-h-11 min-w-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40" data-qid="battle:timeline:zoom:out" data-qs-action="BATTLE_TIMELINE_ZOOM" title="Zoom Battle timeline out (Ctrl + scroll also works)" onClick={() => setZoom((value) => stepTimelineZoom(value, -1))}>−</button>
            <button type="button" className="zoomBtn min-h-11 min-w-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40" data-qid="battle:timeline:zoom:in" data-qs-action="BATTLE_TIMELINE_ZOOM" title="Zoom Battle timeline in (Ctrl + scroll also works)" onClick={() => setZoom((value) => stepTimelineZoom(value, 1))}>+</button>
          </div>
                    <span className="playheadLabel">PLAYHEAD {receiptReplay ? formatSeconds(playheadSeconds) : `${mockupClockFromTrackPct((playheadSeconds / Math.max(1, allotted)) * 100)}:32`}</span>
          {receiptReplay && pixiEngine && !director.cameraFollow ? (
            <button
              type="button"
              className="ml-2 rounded-md border border-battle-cyan/30 bg-battle-cyan/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.08em] text-battle-cyan"
              data-qid="battle:timeline:resume-follow"
              data-qs-action="BATTLE_CAMERA_RESUME_FOLLOW"
              onClick={() => director.resumeCameraFollow()}
            >
              Resume follow
            </button>
          ) : null}
        </div>
      ) : (
        <div className="flex min-h-[36px] items-center justify-between gap-3 border-b border-battle-blue/[.07] bg-[rgba(3,8,15,.35)] px-4 py-1">
          <div className="min-w-0 text-[10px] font-black uppercase tracking-[0.08em] text-slate-500">
            Evolution &amp; Progress Graph <span className="ml-2 font-semibold normal-case tracking-normal text-slate-600">· Zoom {Math.round(zoom * 100)}%</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="hidden items-center gap-2 pr-2 text-[10px] font-black uppercase tracking-[0.08em] text-battle-cyan sm:flex">
              <span className="h-3.5 w-0.5 bg-battle-cyan shadow-blueGlow" aria-hidden="true" />
              {playing ? "PLAYHEAD" : "NOW"} {formatSeconds(playheadSeconds)}
            </div>
            <Button data-qid="battle:timeline:zoom:out" data-qs-action="BATTLE_TIMELINE_ZOOM" title="Zoom Battle timeline out (Ctrl + scroll also works)" variant="outline" size="sm" className="min-h-9 min-w-9" onClick={() => setZoom((value) => stepTimelineZoom(value, -1))}>−</Button>
            <Button data-qid="battle:timeline:zoom:in" data-qs-action="BATTLE_TIMELINE_ZOOM" title="Zoom Battle timeline in (Ctrl + scroll also works)" variant="outline" size="sm" className="min-h-9 min-w-9" onClick={() => setZoom((value) => stepTimelineZoom(value, 1))}>+</Button>
            <Button data-qid="battle:timeline:zoom:fit" data-qs-action="BATTLE_TIMELINE_ZOOM" title="Reset timeline zoom to 100% and center on playhead" variant="outline" size="sm" className="min-h-9 px-2 text-[10px]" onClick={() => setZoom(TIMELINE_ZOOM_DEFAULT)}>Fit</Button>
          </div>
        </div>
      )}

      <TimelineOverview marks={overviewMarks} viewportStyle={overviewViewport} showScrollHint={showScrollHint} designView={designView} onScrub={receiptReplay || designView ? onTimelineScrubPointer : undefined} />

      {designView ? (
        <div className="graphWrapHost">
          <div
            ref={scrollRef}
            id="graphWrap"
            data-qid="battle:timeline:scroll"
            data-qs-action="BATTLE_TIMELINE_SCROLL"
            title="Scrollable Battle timeline"
            className="graphWrap"
          >
            <BattleTimelineCanvas contentWidth={contentWidth} designView>
              {timelineBody}
            </BattleTimelineCanvas>
          </div>
          <div className={`graphScrollHint${showScrollHint ? "" : " hidden"}`}>
            <span>More outcomes →</span>
          </div>
        </div>
      ) : (
        <div className="relative min-h-0 flex-1">
          <div
            ref={scrollRef}
            data-qid="battle:timeline:scroll"
            data-qs-action="BATTLE_TIMELINE_SCROLL"
            title="Scrollable receipt-backed Battle timeline"
            className="battle-timeline-scroll h-full overflow-auto bg-battle-panel/45"
          >
            <BattleTimelineCanvas contentWidth={contentWidth}>{timelineBody}</BattleTimelineCanvas>
          </div>
          <div className={`battle-scroll-edge-hint pointer-events-none absolute bottom-3 right-4 z-20 ${showScrollHint ? "" : "hidden"}`}>
            More outcomes →
          </div>
        </div>
      )}
    </>
  );

  const providerBody = (
    <BattleTimelineProvider allottedSeconds={allotted}>
      <BlueControlStrip
        actions={battleBluePatchActionsForView(fixture)}
        allottedSeconds={allotted}
        interventionCount={designView ? mockupBlue.interventions : scoreboard?.blue_success_count}
        blockCount={designView ? mockupBlue.blocks : blockCount > 0 ? blockCount : undefined}
      />
      {timelineChrome}
    </BattleTimelineProvider>
  );

  if (designView) {
    return <div className={shellClass}>{providerBody}</div>;
  }

  return <Card className={shellClass}>{providerBody}</Card>;
}

function BattleTimelineCanvas({ contentWidth, children, designView = false }: { contentWidth: number; children: ReactNode; designView?: boolean }) {
  const { setTrackRef } = useBattleTimelineScale();

  if (designView) {
    return (
      <div className="graph" ref={setTrackRef} style={{ minWidth: contentWidth }} data-battle-timeline-track>
        <div className="timelineShell">{children}</div>
      </div>
    );
  }

  return (
    <div ref={setTrackRef} className="relative min-h-full" style={{ width: contentWidth }} data-battle-timeline-track>
      {children}
    </div>
  );
}

function buildTicks({ maxX, allotted }: { maxX: number; allotted: number }) {
  const safeMax = Math.max(100, maxX);
  const values = [0, 20, 40, 60, 80, 100];
  return values.map((x) => ({ x: (x / safeMax) * 100, label: formatSeconds((x / 100) * allotted) }));
}

function formatSeconds(value: number) {
  const total = Math.max(0, Math.floor(value));
  const min = Math.floor(total / 60).toString().padStart(2, "0");
  const sec = (total % 60).toString().padStart(2, "0");
  return `${min}:${sec}`;
}

function LegendItem({ icon, label, color }: { icon: ReactNode; label: string; color: string }) {
  return <span className={`inline-flex items-center gap-1.5 ${color}`}>{icon}<span className="text-slate-400">{label}</span></span>;
}
