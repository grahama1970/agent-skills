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
            className={`cursor-pointer rounded-r-md border-l-4 p-3 transition-all duration-150 ${
              isActive
                ? "border-amber-400 bg-slate-800 ring-1 ring-amber-400/20 shadow-md"
                : "border-sky-500/50 bg-slate-900/90 opacity-70 hover:bg-slate-800/60"
            }`}
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
            <h3 className="text-sm font-extrabold text-slate-100">{card.title}</h3>
            <p className="mt-1 line-clamp-2 text-xs font-medium text-slate-300">
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
            <h3 className="text-sm font-extrabold text-slate-100">{card.title}</h3>
            <p className="mt-1 line-clamp-2 text-xs font-medium text-slate-300">
              • {card.body}
            </p>
          </div>
        );
      })}
    </div>
  );
};
