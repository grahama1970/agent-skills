import { useLayoutEffect, useState, type RefObject } from "react";
import type { Lane } from "./lib/battle-types";
import { computeLineageLayout, handoffTimelineX } from "./lib/layout-lineage-rails";
import { spawnBranchPath } from "./lib/spawn-branch-path";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";

type Props = {
  lanes: Lane[];
  visibleLaneIds: string[];
  collapsed: Set<string>;
  containerRef: RefObject<HTMLDivElement | null>;
  rowRefs: RefObject<Map<string, HTMLDivElement>>;
  layoutKey: string;
};

type RowRect = {
  id: string;
  top: number;
  height: number;
  trackLeft: number;
  trackWidth: number;
};

type MockupRail = { parentId: string; top: number; height: number };
type MockupConnector = { childId: string; top: number; left: number; width: number };

function measureRowRects(
  lanes: Lane[],
  visible: Set<string>,
  container: HTMLDivElement,
  rowRefs: RefObject<Map<string, HTMLDivElement>>,
): RowRect[] {
  const containerRect = container.getBoundingClientRect();
  return lanes
    .filter((lane) => visible.has(lane.id))
    .map((lane) => {
      const row = rowRefs.current?.get(lane.id);
      const track = row?.querySelector<HTMLElement>("[data-lane-track]");
      if (!row || !track) return null;
      const rowRect = row.getBoundingClientRect();
      const trackRect = track.getBoundingClientRect();
      return {
        id: lane.id,
        top: rowRect.top - containerRect.top,
        height: rowRect.height,
        trackLeft: trackRect.left - containerRect.left,
        trackWidth: trackRect.width,
      };
    })
    .filter(Boolean) as RowRect[];
}

function computeMockupRails(
  lanes: Lane[],
  rowRects: RowRect[],
  collapsed: Set<string>,
): { rails: MockupRail[]; connectors: MockupConnector[] } {
  const rectById = Object.fromEntries(rowRects.map((row) => [row.id, row]));
  const rails: MockupRail[] = [];
  const connectors: MockupConnector[] = [];

  for (const parent of lanes) {
    const childIds = parent.children?.length
      ? parent.children
      : lanes.filter((lane) => lane.parentId === parent.id).map((lane) => lane.id);
    if (!childIds.length || collapsed.has(parent.id)) continue;

    const parentRect = rectById[parent.id];
    const childRects = childIds.map((id) => rectById[id]).filter(Boolean) as RowRect[];
    if (!parentRect || !childRects.length) continue;

    const top = parentRect.top + parentRect.height * 0.5;
    const lastChild = childRects[childRects.length - 1];
    const bottom = lastChild.top + lastChild.height * 0.5;
    rails.push({ parentId: parent.id, top, height: Math.max(8, bottom - top) });

    const handoffX = handoffTimelineX(parent) ?? parent.xEnd * 0.72;
    for (const childRect of childRects) {
      const child = lanes.find((lane) => lane.id === childRect.id);
      if (!child || childRect.trackWidth <= 0) continue;
      const fromX = childRect.trackLeft + (handoffX / 100) * childRect.trackWidth;
      const toX = childRect.trackLeft + ((child.xStart + 1.5) / 100) * childRect.trackWidth;
      connectors.push({
        childId: child.id,
        top: childRect.top + childRect.height * 0.5,
        left: fromX,
        width: Math.max(0, toX - fromX),
      });
    }
  }

  return { rails, connectors };
}

export function BattleLineageFlow({
  lanes,
  visibleLaneIds,
  collapsed,
  containerRef,
  rowRefs,
  layoutKey,
}: Props) {
  const designView = isBattleDesignView();
  const [branches, setBranches] = useState<ReturnType<typeof computeLineageLayout>["branches"]>([]);
  const [mockupRails, setMockupRails] = useState<MockupRail[]>([]);
  const [mockupConnectors, setMockupConnectors] = useState<MockupConnector[]>([]);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    let cancelled = false;

    const measure = () => {
      if (cancelled) return;
      const container = containerRef.current;
      if (!container) return;

      const containerRect = container.getBoundingClientRect();
      const visible = new Set(visibleLaneIds);
      const rowRects = measureRowRects(lanes, visible, container, rowRefs);

      if (designView) {
        const layout = computeMockupRails(lanes, rowRects, collapsed);
        setMockupRails(layout.rails);
        setMockupConnectors(layout.connectors);
        setBranches([]);
        setSvgSize({ width: 0, height: 0 });
        return;
      }

      setMockupRails([]);
      setMockupConnectors([]);
      setSvgSize({ width: containerRect.width, height: containerRect.height });
      setBranches(
        computeLineageLayout({
          lanes,
          rowRects: rowRects.map((row) => ({
            ...row,
            top: row.top + containerRect.top,
          })),
          collapsed,
          containerTop: containerRect.top,
        }).branches
      );
    };

    const schedule = () => window.requestAnimationFrame(() => window.requestAnimationFrame(measure));
    schedule();

    const container = containerRef.current;
    const scrollParent = container?.closest(".graphWrap, .battle-timeline-scroll");
    window.addEventListener("resize", schedule);
    scrollParent?.addEventListener("scroll", schedule, { passive: true });
    const observer = container ? new ResizeObserver(schedule) : null;
    if (container && observer) observer.observe(container);

    return () => {
      cancelled = true;
      window.removeEventListener("resize", schedule);
      scrollParent?.removeEventListener("scroll", schedule);
      observer?.disconnect();
    };
  }, [lanes, visibleLaneIds, collapsed, containerRef, rowRefs, layoutKey, designView]);

  if (designView) {
    if (!mockupRails.length && !mockupConnectors.length) return null;
    return (
      <>
        {mockupRails.map((rail) => (
          <div
            key={rail.parentId}
            className="branchRail"
            style={{ top: `${rail.top}px`, height: `${rail.height}px` }}
            aria-hidden="true"
          />
        ))}
        {mockupConnectors.map((connector) => (
          <div
            key={connector.childId}
            className="spawnConnector"
            style={{
              top: `${connector.top}px`,
              left: `${connector.left}px`,
              width: `${connector.width}px`,
            }}
            aria-hidden="true"
          />
        ))}
      </>
    );
  }

  if (!branches.length) return null;

  return (
    <svg
      className="battle-lineage-svg pointer-events-none absolute inset-0 z-[5] overflow-visible"
      width={svgSize.width || undefined}
      height={svgSize.height || undefined}
      aria-hidden="true"
      data-testid="battle-lineage-svg"
    >
      {branches.map((branch) => (
        <path
          key={`${branch.parentId}->${branch.childId}`}
          d={spawnBranchPath(branch)}
          className="battle-lineage-branch"
          fill="none"
        />
      ))}
    </svg>
  );
}
