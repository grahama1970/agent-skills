import { ScanSearch } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function EmptyEvidence() {
  return (
    <Card className="relative flex min-h-[360px] flex-1 items-center justify-center overflow-hidden border-[var(--accent)]/10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_25%,rgba(62,211,194,0.09),transparent_42%)]" />
      <CardContent className="relative max-w-md p-8 text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl border border-[var(--accent)]/20 bg-[var(--accent)]/[0.07]">
          <ScanSearch aria-hidden="true" className="size-6 text-[var(--accent)]" />
        </div>
        <p className="mt-5 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
          Evidence surface ready
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.025em] text-[var(--foreground)]">
          Stay in the conversation.
        </h2>
        <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">
          A source-bound talking point will appear when the interviewer asks a substantive question or names a watched project.
        </p>
      </CardContent>
    </Card>
  );
}
