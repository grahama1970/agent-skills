import {
  Brain,
  Filter,
  Search,
  Tag,
} from "lucide-react";
import { useMemo, useState } from "react";

import { MemoryVaultRecord } from "@/components/MemoryVaultRecord";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import { formatLatency } from "@/lib/utils";
import { qidSafe, recordsFrom, type VaultType } from "@/lib/vaultRecords";
import type { EvidenceCard, LaneActivity, RetrievalLane, SessionInfo, TranscriptEvent } from "@/types";

interface MemoryVaultProps {
  cards: EvidenceCard[];
  transcript: TranscriptEvent[];
  lanes: LaneActivity[];
  session: SessionInfo;
  currentThread: string;
  busy: boolean;
  onSearch: (query: string, lane: RetrievalLane) => void;
}

function TypeFilterButton({
  type,
  active,
  onClick,
}: {
  type: VaultType;
  active: boolean;
  onClick: (type: VaultType) => void;
}) {
  const qid = `live-evidence:vault:type:${type}`;
  useRegisterAction({
    element_id: qid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_TYPE_FILTER",
    label: `Filter Vault by ${type}`,
    description: "Filter the current-session evidence records by record type",
    params: { type },
  });

  return (
    <button
      data-qid={qid}
      data-qs-action="LIVE_EVIDENCE_VAULT_TYPE_FILTER"
      title={`Filter Vault by ${type}`}
      type="button"
      className={`rounded-md px-3 py-1.5 text-xs capitalize transition ${
        active ? "bg-white text-slate-950" : "text-slate-400 hover:bg-white/[0.07] hover:text-slate-100"
      }`}
      onClick={() => onClick(type)}
    >
      {type}
    </button>
  );
}

function TagFilterButton({
  tag,
  active,
  onClick,
}: {
  tag: string;
  active: boolean;
  onClick: (tag: string) => void;
}) {
  const qid = `live-evidence:vault:tag:${qidSafe(tag)}`;
  useRegisterAction({
    element_id: qid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_TAG_FILTER",
    label: `Filter Vault by ${tag}`,
    description: "Filter the current-session evidence records by tag",
    params: { tag },
  });

  return (
    <button
      data-qid={qid}
      data-qs-action="LIVE_EVIDENCE_VAULT_TAG_FILTER"
      title={`Filter Vault by ${tag}`}
      type="button"
      className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] transition ${
        active
          ? "border-cyan-300/60 bg-cyan-300/15 text-cyan-100"
          : "border-white/10 bg-white/[0.035] text-slate-400 hover:border-white/20 hover:text-slate-100"
      }`}
      onClick={() => onClick(tag)}
    >
      #{tag}
    </button>
  );
}

export function MemoryVault({ cards, transcript, lanes, session, currentThread, busy, onSearch }: MemoryVaultProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState<VaultType>("all");
  const [selectedTag, setSelectedTag] = useState("all");
  const [selectedProject, setSelectedProject] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useRegisterAction({
    element_id: "live-evidence:vault:search",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_SEARCH_EDIT",
    label: "Edit Vault search",
    description: "Search the current-session evidence records by keyword",
  });
  useRegisterAction({
    element_id: "live-evidence:vault:project",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_PROJECT_FILTER",
    label: "Filter Vault by project",
    description: "Filter current-session records by project or thread",
  });
  useRegisterAction({
    element_id: "live-evidence:vault:date-from",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_DATE_FROM",
    label: "Set Vault start date",
    description: "Filter current-session records from this date",
  });
  useRegisterAction({
    element_id: "live-evidence:vault:date-to",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_DATE_TO",
    label: "Set Vault end date",
    description: "Filter current-session records through this date",
  });
  useRegisterAction({
    element_id: "live-evidence:vault:memory-search",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_VAULT_MEMORY_SEARCH",
    label: "Run Memory search",
    description: "Run the visible query through the bounded Memory retrieval lane",
  });

  const records = useMemo(() => recordsFrom(cards, session, currentThread), [cards, currentThread, session]);
  const tags = useMemo(() => Array.from(new Set(records.flatMap((record) => record.tags))).sort(), [records]);
  const projects = useMemo(() => Array.from(new Set(records.map((record) => record.project))).sort(), [records]);

  const filteredRecords = useMemo(() => {
    const lowerQuery = searchQuery.trim().toLowerCase();
    return records.filter((record) => {
      const matchesSearch =
        lowerQuery.length === 0 ||
        record.title.toLowerCase().includes(lowerQuery) ||
        record.content.toLowerCase().includes(lowerQuery) ||
        record.sourceText.toLowerCase().includes(lowerQuery);
      const matchesType = selectedType === "all" || record.type === selectedType;
      const matchesTag = selectedTag === "all" || record.tags.includes(selectedTag);
      const matchesProject = selectedProject === "all" || record.project === selectedProject;
      const matchesDateFrom = !dateFrom || record.createdDate >= dateFrom;
      const matchesDateTo = !dateTo || record.createdDate <= dateTo;
      return matchesSearch && matchesType && matchesTag && matchesProject && matchesDateFrom && matchesDateTo;
    });
  }, [dateFrom, dateTo, records, searchQuery, selectedProject, selectedTag, selectedType]);

  const memoryLane = lanes.find((lane) => lane.lane === "memory");
  const canRunMemorySearch = searchQuery.trim().length >= 2 && !busy;

  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem] lg:pr-96" aria-label="Memory Vault">
      <div className="min-w-0">
        <div className="mb-4 space-y-3">
          <div>
            <h2 className="text-xl font-semibold text-white">Memory Vault</h2>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              Historical semantic archive endpoint is not connected; this view is limited to real current-session evidence records.
            </p>
          </div>

          <div className="grid gap-2 md:grid-cols-[minmax(14rem,1fr)_auto]">
            <div className="relative min-w-0">
              <Search aria-hidden="true" className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
              <input
                data-qid="live-evidence:vault:search"
                data-qs-action="LIVE_EVIDENCE_VAULT_SEARCH_EDIT"
                title="Search current-session evidence records"
                type="search"
                className="h-10 w-full rounded-lg border border-white/10 bg-black/20 pl-9 pr-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus-visible:border-cyan-300/45 focus-visible:ring-2 focus-visible:ring-cyan-300/20"
                placeholder="Search evidence, sources, or transcript-derived claims"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <button
              data-qid="live-evidence:vault:memory-search"
              data-qs-action="LIVE_EVIDENCE_VAULT_MEMORY_SEARCH"
              title="Run this query through Memory retrieval"
              type="button"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-cyan-300/20 bg-cyan-300/10 px-3 text-xs font-medium text-cyan-100 transition hover:bg-cyan-300/15 disabled:cursor-not-allowed disabled:opacity-45"
              disabled={!canRunMemorySearch}
              onClick={() => onSearch(searchQuery.trim(), "memory")}
            >
              <Brain aria-hidden="true" className="size-3.5" />
              Memory search
            </button>
          </div>

          <div className="grid gap-2 xl:grid-cols-[auto_minmax(11rem,14rem)_auto_auto]">
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/20 p-1">
              {(["all", "code", "memory", "fact"] as VaultType[]).map((type) => (
                <TypeFilterButton key={type} type={type} active={selectedType === type} onClick={setSelectedType} />
              ))}
            </div>

            <select
              data-qid="live-evidence:vault:project"
              data-qs-action="LIVE_EVIDENCE_VAULT_PROJECT_FILTER"
              title="Filter by project or thread"
              className="h-10 rounded-lg border border-white/10 bg-black/20 px-3 text-xs text-slate-200 outline-none focus-visible:border-cyan-300/45 focus-visible:ring-2 focus-visible:ring-cyan-300/20"
              value={selectedProject}
              onChange={(event) => setSelectedProject(event.target.value)}
            >
              <option value="all">All projects</option>
              {projects.map((project) => (
                <option key={project} value={project}>
                  {project}
                </option>
              ))}
            </select>

            <input
              data-qid="live-evidence:vault:date-from"
              data-qs-action="LIVE_EVIDENCE_VAULT_DATE_FROM"
              title="Filter from date"
              type="date"
              className="h-10 rounded-lg border border-white/10 bg-black/20 px-3 text-xs text-slate-200 outline-none focus-visible:border-cyan-300/45 focus-visible:ring-2 focus-visible:ring-cyan-300/20"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
            <input
              data-qid="live-evidence:vault:date-to"
              data-qs-action="LIVE_EVIDENCE_VAULT_DATE_TO"
              title="Filter through date"
              type="date"
              className="h-10 rounded-lg border border-white/10 bg-black/20 px-3 text-xs text-slate-200 outline-none focus-visible:border-cyan-300/45 focus-visible:ring-2 focus-visible:ring-cyan-300/20"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            <span className="inline-flex shrink-0 items-center gap-1 text-slate-500">
              <Tag aria-hidden="true" className="size-3" />
              Tags
            </span>
            <TagFilterButton tag="all" active={selectedTag === "all"} onClick={setSelectedTag} />
            {tags.map((tag) => (
              <TagFilterButton key={tag} tag={tag} active={selectedTag === tag} onClick={setSelectedTag} />
            ))}
          </div>
        </div>

        {filteredRecords.length === 0 ? (
          <div className="grid min-h-[24rem] place-items-center rounded-lg border border-white/10 bg-[#0b1214] px-6 text-center">
            <div>
              <Filter aria-hidden="true" className="mx-auto size-6 text-slate-500" />
              <p className="mt-3 text-sm font-medium text-slate-200">No current-session records match these filters.</p>
              <p className="mt-1 text-xs text-slate-500">Live audio must create evidence cards before the Vault can show operational content.</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filteredRecords.map((record) => (
              <MemoryVaultRecord key={record.id} record={record} />
            ))}
          </div>
        )}
      </div>

      <aside className="space-y-3" aria-label="Vault contract and live lane state">
        <div className="rounded-lg border border-white/10 bg-[#0b1214] p-4">
          <div className="text-[10px] font-semibold uppercase text-amber-200">Archive Contract</div>
          <p className="mt-2 text-xs leading-5 text-slate-400">
            `GET /api/memories/search` is not implemented. Semantic + keyword historical search remains fail-closed until that bounded endpoint exists.
          </p>
        </div>

        <div className="rounded-lg border border-white/10 bg-[#0b1214] p-4">
          <div className="text-[10px] font-semibold uppercase text-cyan-200">Live Lanes</div>
          <div className="mt-3 space-y-2">
            {lanes.map((lane) => (
              <div key={lane.lane} className="rounded-md border border-white/[0.07] bg-black/15 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium capitalize text-slate-200">{lane.lane}</span>
                  <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-400">{lane.state}</span>
                </div>
                <p className="mt-1 text-[11px] leading-4 text-slate-500">{lane.detail}</p>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-600">
                  <span>{lane.result_count} results</span>
                  <span>{formatLatency(lane.latency_ms)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-[#0b1214] p-4">
          <div className="text-[10px] font-semibold uppercase text-emerald-200">Session Intake</div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <dt className="text-slate-500">Transcript</dt>
              <dd className="mt-0.5 font-mono text-slate-200">{transcript.length}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Records</dt>
              <dd className="mt-0.5 font-mono text-slate-200">{records.length}</dd>
            </div>
          </dl>
        </div>
      </aside>
    </section>
  );
}
