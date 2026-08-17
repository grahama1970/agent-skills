import { Binary, Braces, DatabaseZap, Globe2, MessagesSquare, SearchCode } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatLatency } from "@/lib/utils";
import type { LaneActivity, RetrievalLane } from "@/types";

const LANE_META: Record<RetrievalLane, { label: string; icon: typeof DatabaseZap }> = {
  memory: { label: "Graph Memory", icon: DatabaseZap },
  code: { label: "Indexed code", icon: Braces },
  ripgrep: { label: "Current source", icon: SearchCode },
  ask: { label: "Ask solver", icon: MessagesSquare },
  brave: { label: "Brave", icon: Globe2 },
  dogpile: { label: "Dogpile", icon: Binary },
};

function stateColor(state: LaneActivity["state"]): string {
  if (state === "ok") return "bg-emerald-300";
  if (state === "running") return "bg-[var(--accent)] animate-pulse";
  if (state === "degraded" || state === "error") return "bg-amber-300";
  return "bg-white/25";
}

export function RetrievalRail({ lanes }: { lanes: LaneActivity[] }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
            Retrieval fabric
          </p>
          <h2 className="mt-1 text-sm font-semibold text-[var(--foreground)]">Evidence lanes</h2>
        </div>
        <Badge variant="muted">Local first</Badge>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {lanes.map((lane) => {
          const meta = LANE_META[lane.lane];
          const Icon = meta.icon;
          return (
            <div
              key={lane.lane}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl border border-transparent px-2.5 py-2.5 transition hover:border-white/[0.06] hover:bg-white/[0.025]"
            >
              <div className="relative grid size-8 place-items-center rounded-lg bg-white/[0.045] text-[var(--muted-foreground)]">
                <Icon aria-hidden="true" className="size-3.5" />
                <span className={`absolute -right-0.5 -top-0.5 size-2 rounded-full ring-2 ring-[var(--panel)] ${stateColor(lane.state)}`} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-xs font-medium text-[var(--foreground)]/90">{meta.label}</p>
                  {lane.result_count > 0 ? <span className="text-[10px] text-[var(--accent)]">{lane.result_count}</span> : null}
                </div>
                <p className="mt-0.5 truncate text-[10px] text-[var(--muted-foreground)]">{lane.detail}</p>
              </div>
              <span className="text-[10px] tabular-nums text-[var(--muted-foreground)]">
                {formatLatency(lane.latency_ms)}
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
