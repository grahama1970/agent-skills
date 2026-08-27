import React from "react";

import { useAutoScroll } from "../hooks/useAutoScroll";
import { useCardSpeech } from "../hooks/useCardSpeech";
import { useCardNavigation } from "../hooks/useCardNavigation";

interface ScanCardProps {
  step: number;
  title: string;
  talkingPoint: string;
  isActive?: boolean;
  onClick?: () => void;
}

export const ScanCard: React.FC<ScanCardProps> = ({
  step,
  title,
  talkingPoint,
  isActive = false,
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`cursor-pointer rounded-r-md border-l-4 p-3 transition-all ${
        isActive
          ? "border-amber-400 bg-slate-800 shadow-lg shadow-amber-400/10"
          : "border-sky-400 bg-slate-900 hover:bg-slate-800/80"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-black tracking-wider text-sky-400">
          0{step}
        </span>
        <h3 className="text-sm font-bold text-slate-100">{title}</h3>
      </div>
      <p className="mt-1 line-clamp-2 text-xs font-medium text-slate-300">
        • {talkingPoint}
      </p>
    </div>
  );
};

interface CardData {
  title: string;
  body: string;
}

export const TalkingPointsStack = ({
  points,
  activeIdx,
}: {
  points: CardData[];
  activeIdx: number;
}) => (
  <div className="flex w-full flex-col gap-2">
    {points.map((pt, idx) => (
      <ScanCard
        key={idx}
        step={idx + 1}
        title={pt.title}
        talkingPoint={pt.body}
        isActive={activeIdx === idx}
      />
    ))}
  </div>
);

/**
 * Reviewer v2 (2026-08-27): keyboard-navigable stack (j/k, arrows, 1-9),
 * contained auto-scroll inside a max-height viewport, ACTIVE badge.
 */
export const ScannableCardStack = ({ cards }: { cards: CardData[] }) => {
  const { activeIndex, setActiveIndex } = useCardNavigation({
    itemCount: cards.length,
  });

  const itemRefs = useAutoScroll<HTMLDivElement>(activeIndex, {
    behavior: "smooth",
    block: "nearest",
    containToParent: true,
  });

  return (
    <div className="flex max-h-[420px] w-full flex-col gap-2.5 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-slate-700">
      {cards.map((card, idx) => {
        const isActive = activeIndex === idx;
        return (
          <div
            key={idx}
            ref={(el) => {
              itemRefs.current[idx] = el;
            }}
            onClick={() => setActiveIndex(idx)}
            className={`scannable-card cursor-pointer rounded-r-md border-l-4 p-3 transition-all duration-150 ${isActive ? "active border-amber-400 bg-slate-800 ring-1 ring-amber-400/20 shadow-md" : "border-sky-500/50 bg-slate-900/90 opacity-70 hover:bg-slate-800/60"}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black text-sky-400">
                0{idx + 1}
              </span>
              {isActive && (
                <span className="text-[9px] font-bold uppercase tracking-widest text-amber-400">
                  ACTIVE
                </span>
              )}
            </div>
            <h3 className="card-title text-sm font-extrabold text-slate-100">{card.title}</h3>
            <p className="card-bullet mt-1 line-clamp-2 text-xs font-medium text-slate-300">
              • {card.body}
            </p>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Reviewer v3: stack with synchronized Web Speech earcons. Mounted ONLY when
 * the session policy grants voice_output (rehearsal purpose) - in a live
 * meeting the browser TTS would leak into the call mic, so the policy layer,
 * not the UI, owns that decision.
 */
export const ScannableCardStackWithAudio = ({ cards }: { cards: CardData[] }) => {
  const { activeIndex, setActiveIndex } = useCardNavigation({
    itemCount: cards.length,
  });

  const itemRefs = useAutoScroll<HTMLDivElement>(activeIndex, {
    behavior: "smooth",
    block: "nearest",
    containToParent: true,
  });

  const activeCard = cards[activeIndex];
  useCardSpeech(activeCard, {
    enabled: true,
    speechRate: 1.35,
    readBody: false,
  });

  return (
    <div className="flex max-h-[400px] w-full flex-col gap-2.5 overflow-y-auto pr-1 scrollbar-thin">
      {cards.map((card, idx) => {
        const isActive = activeIndex === idx;
        return (
          <div
            key={idx}
            ref={(el) => {
              itemRefs.current[idx] = el;
            }}
            onClick={() => setActiveIndex(idx)}
            className={`cursor-pointer rounded-r-md border-l-4 p-3 transition-all duration-150 ${
              isActive
                ? "border-amber-400 bg-slate-800 ring-1 ring-amber-400/20 shadow-md"
                : "border-sky-500/50 bg-slate-900/90 opacity-60 hover:bg-slate-800/60"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black text-sky-400">0{idx + 1}</span>
              {isActive && (
                <div className="flex items-center gap-1 text-[9px] font-bold text-amber-400">
                  <span className="h-1.5 w-1.5 animate-ping rounded-full bg-amber-400" />
                  TTS SPEAKING
                </div>
              )}
            </div>
            <h3 className="card-title text-sm font-extrabold text-slate-100">{card.title}</h3>
            <p className="card-bullet mt-1 line-clamp-2 text-xs font-medium text-slate-300">
              • {card.body}
            </p>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Reviewer round 4: 2x2 matrix deck - fixed spatial coordinates, 1-4 hotkeys,
 * focus dimming. Verbatim structure; cards fed from parsed answer points.
 */
export const CardDeckMatrix = ({ cards }: { cards: CardData[] }) => {
  const [activeId, setActiveId] = React.useState<number>(1);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
      if (["1", "2", "3", "4"].includes(e.key)) {
        const id = parseInt(e.key, 10);
        if (id <= cards.length) setActiveId(id);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cards.length]);

  return (
    <div className="mx-auto w-full max-w-2xl rounded-xl bg-slate-950 p-4">
      <div className="mb-3 flex items-center justify-between px-1">
        <span className="text-[11px] font-black uppercase tracking-widest text-slate-400">
          CARD DECK MATRIX · <span className="text-amber-400">[1-4] SELECT</span>
        </span>
        <span className="rounded border border-sky-800 bg-sky-950/80 px-2 py-0.5 text-[10px] font-bold text-sky-400">
          ACTIVE: CARD 0{activeId}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3.5">
        {cards.slice(0, 4).map((card, idx) => {
          const id = idx + 1;
          const isActive = id === activeId;
          const label = card.title.replace(/^\d+\.\s*/, "").split(" ")[0].toUpperCase();
          const headline = card.title.replace(/^\d+\.\s*/, "");
          return (
            <div
              key={id}
              onClick={() => setActiveId(id)}
              className={`relative flex h-36 cursor-pointer flex-col justify-between rounded-lg border-2 p-4 transition-all duration-150 ${
                isActive
                  ? "z-10 scale-[1.02] border-amber-400 bg-slate-900 shadow-lg shadow-amber-400/10"
                  : "border-slate-800 bg-slate-900/40 opacity-40 hover:border-slate-700 hover:opacity-75"
              }`}
            >
              <div className="flex items-start justify-between">
                <span className={`text-[10px] font-black tracking-wider ${isActive ? "text-amber-400" : "text-slate-500"}`}>
                  {label}
                </span>
                <span className={`rounded px-1.5 py-0.5 text-xs font-black ${isActive ? "bg-amber-400 text-slate-950" : "bg-slate-800 text-slate-400"}`}>
                  {id}
                </span>
              </div>
              <div className="my-auto">
                <h3 className={`text-base font-extrabold leading-tight ${isActive ? "text-white" : "text-slate-300"}`}>
                  {headline}
                </h3>
                <p className={`mt-1 line-clamp-2 text-xs font-medium ${isActive ? "text-slate-200" : "text-slate-500"}`}>
                  • {card.body}
                </p>
              </div>
              {isActive && <div className="absolute bottom-0 left-0 right-0 h-1 rounded-b-sm bg-amber-400" />}
            </div>
          );
        })}
      </div>
    </div>
  );
};
