import { ArrowRight, Search } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { RetrievalLane } from "@/types";

interface ManualSearchProps {
  busy: boolean;
  onSearch: (query: string, lane: RetrievalLane) => void;
}

export function ManualSearch({ busy, onSearch }: ManualSearchProps) {
  const [query, setQuery] = useState("");
  const [lane, setLane] = useState<RetrievalLane>("memory");

  useRegisterAction({
    element_id: "live-evidence:search:query",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SEARCH_QUERY_EDIT",
    label: "Edit evidence query",
    description: "Enter a bounded query for an explicit evidence search",
  });
  useRegisterAction({
    element_id: "live-evidence:search:lane",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SEARCH_LANE_SELECT",
    label: "Select retrieval lane",
    description: "Select Memory, current source, Brave, or Dogpile for a manual query",
  });
  useRegisterAction({
    element_id: "live-evidence:search:submit",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SEARCH_SUBMIT",
    label: "Run manual evidence search",
    description: "Run the typed query through the selected retrieval lane",
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const clean = query.trim();
    if (clean.length < 2) return;
    onSearch(clean, lane);
    setQuery("");
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
          <Search aria-hidden="true" className="size-3" />
          Explicit search
        </div>
        <p className="text-xs leading-5 text-[var(--muted-foreground)]">
          External lanes run only when you ask. The full transcript is never forwarded.
        </p>
      </CardHeader>
      <CardContent>
        <form className="space-y-2.5" onSubmit={submit}>
          <Input
            data-qid="live-evidence:search:query"
            data-qs-action="LIVE_EVIDENCE_SEARCH_QUERY_EDIT"
            title="Enter a bounded evidence query"
            aria-label="Manual evidence query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find proof for…"
            autoComplete="off"
          />
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <select
              data-qid="live-evidence:search:lane"
              data-qs-action="LIVE_EVIDENCE_SEARCH_LANE_SELECT"
              title="Select the retrieval lane"
              aria-label="Retrieval lane"
              className="h-10 rounded-xl border border-white/10 bg-black/20 px-3 text-xs text-[var(--foreground)] outline-none focus-visible:border-[var(--accent)]/45 focus-visible:ring-2 focus-visible:ring-[var(--accent)]/20"
              value={lane}
              onChange={(event) => setLane(event.target.value as RetrievalLane)}
            >
              <option value="memory">Graph Memory</option>
              <option value="ripgrep">Current source</option>
              <option value="brave">Brave</option>
              <option value="dogpile">Dogpile deep research</option>
            </select>
            <Button
              data-qid="live-evidence:search:submit"
              data-qs-action="LIVE_EVIDENCE_SEARCH_SUBMIT"
              title="Run the manual evidence search"
              type="submit"
              size="icon"
              disabled={busy || query.trim().length < 2}
              aria-label="Run manual evidence search"
            >
              <ArrowRight aria-hidden="true" className="size-4" />
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
