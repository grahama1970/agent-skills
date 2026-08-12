import { Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function CurrentThread({ thread }: { thread: string }) {
  return (
    <Card className="overflow-hidden border-[var(--accent)]/10">
      <CardContent className="relative p-4">
        <div className="absolute inset-y-0 left-0 w-0.5 bg-gradient-to-b from-[var(--accent)] to-transparent" />
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
          <Sparkles aria-hidden="true" className="size-3" />
          Current thread
        </div>
        <p className="mt-2 line-clamp-2 text-sm font-medium leading-5 text-[var(--foreground)]">
          {thread}
        </p>
      </CardContent>
    </Card>
  );
}
