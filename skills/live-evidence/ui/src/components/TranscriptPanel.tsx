import { MessageSquareText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatClock } from "@/lib/utils";
import type { TranscriptEvent } from "@/types";

export function TranscriptPanel({ transcript }: { transcript: TranscriptEvent[] }) {
  const visible = transcript.slice(-18);
  return (
    <Card className="flex min-h-0 flex-1 flex-col">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-3">
        <div className="flex items-center gap-2">
          <MessageSquareText aria-hidden="true" className="size-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold text-[var(--foreground)]">Live transcript</h2>
        </div>
        <Badge variant="muted">{transcript.length} turns</Badge>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 px-3 pb-3">
        <ScrollArea className="h-full space-y-2 pr-1" aria-live="polite" aria-label="Live transcript">
          {visible.length === 0 ? (
            <div className="grid min-h-40 place-items-center px-6 text-center text-xs leading-5 text-[var(--muted-foreground)]">
              Start a listener or replay the fixture. Stable interviewer turns appear here.
            </div>
          ) : (
            visible.map((event) => (
              <article
                key={event.event_id}
                className={`mb-2 rounded-xl border px-3 py-2.5 ${
                  event.speaker === "interviewer"
                    ? "border-white/[0.08] bg-white/[0.035]"
                    : "border-[var(--accent)]/10 bg-[var(--accent)]/[0.035]"
                } ${event.kind === "interim" ? "opacity-55" : "opacity-100"}`}
              >
                <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.13em] text-[var(--muted-foreground)]">
                  <span>{event.speaker === "graham" ? "You" : event.speaker}</span>
                  <span>{formatClock(event.created_at)}</span>
                </div>
                <p className="mt-1.5 text-xs leading-5 text-[var(--foreground)]/90">{event.text}</p>
              </article>
            ))
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
