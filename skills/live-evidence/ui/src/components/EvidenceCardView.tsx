import { Check, Clipboard, Pin, PinOff, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import { compactPath } from "@/lib/utils";
import type { EvidenceCard } from "@/types";

interface EvidenceCardViewProps {
  card: EvidenceCard;
  busy: boolean;
  onPin: (cardId: string) => void;
  onDismiss: (cardId: string) => void;
}

export function EvidenceCardView({ card, busy, onPin, onDismiss }: EvidenceCardViewProps) {
  const [copied, setCopied] = useState(false);
  const pinQid = `live-evidence:card:pin:${card.card_id}`;
  const dismissQid = `live-evidence:card:dismiss:${card.card_id}`;
  const copyQid = `live-evidence:card:copy:${card.card_id}`;

  useRegisterAction({
    element_id: pinQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CARD_PIN",
    label: card.pinned ? "Unpin evidence card" : "Pin evidence card",
    description: "Keep or release this evidence card in the active interview view",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: dismissQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CARD_DISMISS",
    label: "Dismiss evidence card",
    description: "Remove this evidence card from the active interview view",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: copyQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CARD_COPY",
    label: "Copy evidence card",
    description: "Copy the talking point, proof, qualifier, and sources to the clipboard",
    params: { card_id: card.card_id },
  });

  const copyCard = async () => {
    const sources = card.sources
      .map((source) => `${source.label} — ${source.path ?? source.url ?? "source"}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(
        `${card.talking_point}\n\nProof: ${card.proof}\n\nQualifier: ${card.qualifier}\n\n${sources}`,
      );
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Card className="relative flex min-h-0 flex-1 flex-col overflow-hidden border-[var(--accent)]/15">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[radial-gradient(ellipse_at_top,rgba(62,211,194,0.10),transparent_68%)]" />
      <CardHeader className="relative flex-row items-start justify-between gap-4 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={card.status === "supported" ? "default" : "warning"}>
              {card.status === "supported" ? "Now" : "Insufficient"}
            </Badge>
            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              {card.thread}
            </span>
          </div>
          <p className="mt-3 max-w-2xl text-xs leading-5 text-[var(--muted-foreground)]">
            Asked: “{card.query}”
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            data-qid={pinQid}
            data-qs-action="LIVE_EVIDENCE_CARD_PIN"
            title={card.pinned ? "Unpin this evidence card" : "Pin this evidence card"}
            variant="ghost"
            size="icon"
            disabled={busy}
            onClick={() => onPin(card.card_id)}
            aria-label={card.pinned ? "Unpin evidence card" : "Pin evidence card"}
          >
            {card.pinned ? <PinOff aria-hidden="true" className="size-4" /> : <Pin aria-hidden="true" className="size-4" />}
          </Button>
          <Button
            data-qid={copyQid}
            data-qs-action="LIVE_EVIDENCE_CARD_COPY"
            title="Copy this evidence card"
            variant="ghost"
            size="icon"
            onClick={copyCard}
            aria-label="Copy evidence card"
          >
            {copied ? <Check aria-hidden="true" className="size-4 text-emerald-300" /> : <Clipboard aria-hidden="true" className="size-4" />}
          </Button>
          <Button
            data-qid={dismissQid}
            data-qs-action="LIVE_EVIDENCE_CARD_DISMISS"
            title="Dismiss this evidence card"
            variant="ghost"
            size="icon"
            disabled={busy}
            onClick={() => onDismiss(card.card_id)}
            aria-label="Dismiss evidence card"
          >
            <X aria-hidden="true" className="size-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="relative flex min-h-0 flex-1 flex-col px-5 pb-5 lg:px-7 lg:pb-7">
        <section aria-labelledby={`talking-point-${card.card_id}`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
            Say / remember
          </p>
          <h2
            id={`talking-point-${card.card_id}`}
            className="mt-3 text-[clamp(1.35rem,2.3vw,2.25rem)] font-semibold leading-[1.16] tracking-[-0.035em] text-[var(--foreground)]"
          >
            {card.talking_point}
          </h2>
        </section>

        <div className="mt-6 grid gap-3 lg:grid-cols-[1.25fr_0.75fr]">
          <section className="rounded-2xl border border-white/[0.08] bg-black/15 p-4" aria-label="Supporting proof">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Best evidence
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--foreground)]/90">{card.proof}</p>
          </section>
          <section className="rounded-2xl border border-amber-300/[0.12] bg-amber-200/[0.035] p-4" aria-label="Required qualification">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-200">
              <ShieldAlert aria-hidden="true" className="size-3.5" />
              Keep bounded
            </div>
            <p className="mt-2 text-xs leading-5 text-amber-50/78">{card.qualifier}</p>
          </section>
        </div>

        <div className="mt-auto pt-5">
          <Separator />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {card.sources.slice(0, 3).map((source) => (
                <div
                  key={source.source_id}
                  className="answer-provenance max-w-[20rem] rounded-lg border border-white/[0.07] bg-white/[0.035] px-2.5 py-1.5 text-[10px] text-[var(--muted-foreground)]"
                  title={source.path ?? source.url ?? source.label}
                >
                  <span className="font-semibold text-[var(--foreground)]/85">{source.repository ?? source.lane}</span>
                  <span className="mx-1.5 text-white/20">/</span>
                  <span>{compactPath(source.path ?? source.url)}</span>
                  {source.line_start ? <span>:{source.line_start}</span> : null}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
              <span className="size-1.5 rounded-full bg-[var(--accent)]" />
              {Math.round(card.confidence * 100)}% evidence confidence
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
