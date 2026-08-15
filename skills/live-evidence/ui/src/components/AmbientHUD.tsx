import { Brain, Check, Clipboard, Radio, Terminal, X } from "lucide-react";
import { useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import { compactPath } from "@/lib/utils";
import type { EvidenceCard, SessionStatus } from "@/types";

interface AmbientHUDProps {
  cards: EvidenceCard[];
  connected: boolean;
  status: SessionStatus;
  onDismiss: (cardId: string) => void;
}

function cardKind(card: EvidenceCard): "code" | "memory" {
  return card.lanes.some((lane) => lane === "code" || lane === "ripgrep") ? "code" : "memory";
}

function sourceLabel(card: EvidenceCard): string {
  const source = card.sources[0];
  if (!source) return "Source pending";
  const locator = source.path ?? source.url ?? source.label;
  const suffix = source.line_start ? `:${source.line_start}` : "";
  return `${source.repository ?? source.lane} / ${compactPath(locator)}${suffix}`;
}

function HudInsightCard({ card, onDismiss }: { card: EvidenceCard; onDismiss: (cardId: string) => void }) {
  const [copied, setCopied] = useState(false);
  const kind = cardKind(card);
  const dismissQid = `live-evidence:hud:dismiss:${card.card_id}`;
  const copyQid = `live-evidence:hud:copy:${card.card_id}`;
  const question = card.question || card.query;
  const answer = card.answer || card.talking_point;
  const evidence = card.evidence || card.proof;

  useRegisterAction({
    element_id: dismissQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_HUD_DISMISS",
    label: "Dismiss HUD insight",
    description: "Clear one insight from the ambient HUD without removing it from the Vault",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: copyQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_HUD_COPY",
    label: "Copy HUD insight",
    description: "Copy the currently surfaced evidence snippet",
    params: { card_id: card.card_id },
  });

  const copyInsight = async () => {
    try {
      await navigator.clipboard.writeText(`Question: ${question}\n\nAnswer: ${answer}\n\nEvidence: ${evidence}\n\n${card.qualifier}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className="group relative overflow-hidden rounded-xl border border-white/10 bg-slate-950/85 p-3 shadow-2xl shadow-black/35 backdrop-blur-xl transition hover:border-white/20">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {kind === "code" ? (
            <Terminal aria-hidden="true" className="size-3.5 shrink-0 text-cyan-300" />
          ) : (
            <Brain aria-hidden="true" className="size-3.5 shrink-0 text-violet-300" />
          )}
          <h2 className="truncate text-xs font-semibold text-slate-100">{card.thread}</h2>
        </div>
        <button
          data-qid={dismissQid}
          data-qs-action="LIVE_EVIDENCE_HUD_DISMISS"
          title="Dismiss this HUD insight"
          type="button"
          className="grid size-6 shrink-0 place-items-center rounded-md text-slate-500 opacity-100 transition hover:bg-white/10 hover:text-slate-200 sm:opacity-0 sm:group-hover:opacity-100"
          onClick={() => onDismiss(card.card_id)}
          aria-label="Dismiss HUD insight"
        >
          <X aria-hidden="true" className="size-3.5" />
        </button>
      </div>

      <div className="mt-2 space-y-2">
        <div>
          <div className="mb-0.5 text-[9px] font-semibold uppercase text-cyan-200/80">Question</div>
          <p className="line-clamp-2 text-[11px] leading-4 text-slate-300">{question}</p>
        </div>
        <div>
          <div className="mb-0.5 text-[9px] font-semibold uppercase text-emerald-200/80">Answer</div>
          <p className="line-clamp-3 text-xs leading-5 text-slate-100">{answer}</p>
        </div>
        <div>
          <div className="mb-0.5 text-[9px] font-semibold uppercase text-amber-200/80">Evidence</div>
          <p className="line-clamp-2 text-[11px] leading-4 text-slate-400">{evidence}</p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2 text-[10px]">
        <span className="min-w-0 truncate font-mono text-slate-400" title={sourceLabel(card)}>
          {sourceLabel(card)}
        </span>
        <button
          data-qid={copyQid}
          data-qs-action="LIVE_EVIDENCE_HUD_COPY"
          title="Copy this HUD insight"
          type="button"
          className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 font-mono text-slate-400 transition hover:bg-white/10 hover:text-slate-100"
          onClick={copyInsight}
        >
          {copied ? (
            <>
              <Check aria-hidden="true" className="size-3 text-emerald-300" />
              <span className="text-emerald-300">Copied</span>
            </>
          ) : (
            <>
              <Clipboard aria-hidden="true" className="size-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
    </article>
  );
}

export function AmbientHUD({ cards, connected, status, onDismiss }: AmbientHUDProps) {
  const listening = connected && status === "listening";

  return (
    <aside
      className="fixed right-4 top-4 z-50 w-[min(20rem,calc(100vw-2rem))] space-y-3 font-sans text-xs select-none sm:right-6 sm:top-6"
      aria-label="Ambient evidence HUD"
    >
      <div className="flex items-center justify-between rounded-full border border-white/10 bg-slate-950/82 px-3 py-1.5 text-slate-300 shadow-lg shadow-black/30 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            {listening ? <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-300 opacity-75" /> : null}
            <span className={`relative inline-flex size-2 rounded-full ${listening ? "bg-emerald-400" : "bg-amber-300"}`} />
          </span>
          <span className="font-semibold uppercase text-[10px] text-slate-400">
            {listening ? "Listening" : status}
          </span>
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
          <Radio aria-hidden="true" className="size-3" />
          Cmd+\ transcript
        </div>
      </div>

      <div className="space-y-2">
        {cards.map((card) => (
          <HudInsightCard key={card.card_id} card={card} onDismiss={onDismiss} />
        ))}
      </div>
    </aside>
  );
}
