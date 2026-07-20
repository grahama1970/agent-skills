import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createBattleTimeScale, laneXToMs } from "./lib/battle-timeline-scale";
import { BATTLE_LANE_LABEL_PX } from "./lib/layout-constants";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";

type BattleTimelineScaleValue = {
  allottedMs: number;
  trackWidth: number;
  setTrackRef: (node: HTMLDivElement | null) => void;
  leftPxFromLaneX: (laneX: number) => number;
  leftPxFromMs: (ms: number) => number;
  leftPxFromSeconds: (seconds: number) => number;
  msFromLaneX: (laneX: number) => number;
  secondsFromLaneX: (laneX: number) => number;
};

const BattleTimelineScaleContext = createContext<BattleTimelineScaleValue | null>(null);

export function useBattleTimelineScale() {
  const value = useContext(BattleTimelineScaleContext);
  if (!value) {
    throw new Error("useBattleTimelineScale must be used within BattleTimelineProvider");
  }
  return value;
}

type Props = {
  allottedSeconds: number;
  /** Exact world content width used by the PixiJS scene. When provided, the DOM
      overlay scale is driven from it (single source of truth) so DOM labels and
      the playhead cursor never drift from the WebGL sprites/lines — instead of a
      separately-measured DOM element width, which can disagree with the canvas. */
  contentWidth?: number;
  children: ReactNode;
};

export function BattleTimelineProvider({ allottedSeconds, contentWidth, children }: Props) {
  const [trackNode, setTrackNode] = useState<HTMLDivElement | null>(null);
  const [trackWidth, setTrackWidth] = useState(0);
  const allottedMs = Math.max(1, allottedSeconds) * 1000;
  const designView = isBattleDesignView();
  const measuredTrackWidth = designView ? Math.max(0, trackWidth - BATTLE_LANE_LABEL_PX) : trackWidth;
  // Unify with the Pixi canvas: prefer the exact contentWidth (matches
  // secondsToWorldX in battle-pixi-scene.ts, no padding); fall back to the
  // measured element width only when the caller can't supply it.
  const laneTrackWidth = contentWidth != null && contentWidth > 0 ? contentWidth : measuredTrackWidth;

  const setTrackRef = useCallback((node: HTMLDivElement | null) => {
    setTrackNode(node);
  }, []);

  useEffect(() => {
    if (!trackNode) {
      setTrackWidth(0);
      return;
    }

    const measure = () => {
      setTrackWidth(trackNode.getBoundingClientRect().width);
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(trackNode);
    return () => observer.disconnect();
  }, [trackNode]);

  const scale = useMemo(
    () => createBattleTimeScale(allottedMs, laneTrackWidth),
    [allottedMs, laneTrackWidth]
  );

  const msFromLaneX = useCallback((laneX: number) => laneXToMs(laneX, allottedMs), [allottedMs]);

  const value = useMemo<BattleTimelineScaleValue>(
    () => ({
      allottedMs,
      trackWidth: laneTrackWidth,
      setTrackRef,
      leftPxFromLaneX: (laneX) => scale(msFromLaneX(laneX)),
      leftPxFromMs: (ms) => scale(ms),
      leftPxFromSeconds: (seconds) => scale(Math.max(0, seconds) * 1000),
      msFromLaneX,
      secondsFromLaneX: (laneX) => msFromLaneX(laneX) / 1000,
    }),
    [allottedMs, laneTrackWidth, setTrackRef, scale, msFromLaneX]
  );

  return (
    <BattleTimelineScaleContext.Provider value={value}>{children}</BattleTimelineScaleContext.Provider>
  );
}
