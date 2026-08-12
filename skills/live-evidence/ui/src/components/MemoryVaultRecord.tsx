import { Brain, Calendar, Clipboard, Code, ExternalLink, MessageSquare } from "lucide-react";
import { useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { MemoryRecord } from "@/lib/vaultRecords";

function RecordSourceAction({ record }: { record: MemoryRecord }) {
  const [copied, setCopied] = useState(false);
  const qid = `live-evidence:vault:source:${record.id}`;

  useRegisterAction({
    element_id: qid,
    app: "live-evidence",
    action: record.sourceHref ? "LIVE_EVIDENCE_VAULT_OPEN_SOURCE" : "LIVE_EVIDENCE_VAULT_COPY_SOURCE",
    label: record.sourceHref ? "Open evidence source" : "Copy source locator",
    description: record.sourceHref
      ? "Open the external source attached to this evidence record"
      : "Copy the source locator because no browser-openable source URL is available",
    params: { record_id: record.id },
  });

  if (record.sourceHref) {
    return (
      <a
        data-qid={qid}
        data-qs-action="LIVE_EVIDENCE_VAULT_OPEN_SOURCE"
        title="Open evidence source"
        href={record.sourceHref}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-mono text-cyan-200 transition hover:bg-cyan-300/10"
      >
        <span>Open</span>
        <ExternalLink aria-hidden="true" className="size-3" />
      </a>
    );
  }

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(record.sourceText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      data-qid={qid}
      data-qs-action="LIVE_EVIDENCE_VAULT_COPY_SOURCE"
      title="Copy source locator"
      type="button"
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-mono text-slate-400 transition hover:bg-white/[0.07] hover:text-slate-100"
      onClick={copySource}
    >
      <Clipboard aria-hidden="true" className="size-3" />
      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

export function MemoryVaultRecord({ record }: { record: MemoryRecord }) {
  const icon =
    record.type === "code" ? (
      <Code aria-hidden="true" className="size-3.5 text-cyan-300" />
    ) : record.type === "memory" ? (
      <Brain aria-hidden="true" className="size-3.5 text-violet-300" />
    ) : (
      <MessageSquare aria-hidden="true" className="size-3.5 text-emerald-300" />
    );

  return (
    <article className="flex min-h-[13rem] flex-col justify-between rounded-lg border border-white/[0.085] bg-[#0b1214] p-4 transition hover:border-white/20">
      <div>
        <div className="flex items-center justify-between gap-3 text-[11px] text-slate-400">
          <span className="inline-flex items-center gap-1.5 font-medium capitalize">
            {icon}
            {record.type}
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] text-slate-500">
            <Calendar aria-hidden="true" className="size-3" />
            {record.createdAt}
          </span>
        </div>
        <h3 className="mt-3 text-sm font-semibold leading-5 text-white">{record.title}</h3>
        <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-300">{record.content}</p>
      </div>

      <div className="mt-4 border-t border-white/[0.07] pt-3">
        <div className="mb-2 truncate font-mono text-[10px] text-slate-500" title={record.sourceText}>
          {record.sourceText}
        </div>
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 gap-1 overflow-hidden">
            {record.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="truncate font-mono text-[10px] text-slate-500">
                #{tag}
              </span>
            ))}
          </div>
          <RecordSourceAction record={record} />
        </div>
      </div>
    </article>
  );
}
