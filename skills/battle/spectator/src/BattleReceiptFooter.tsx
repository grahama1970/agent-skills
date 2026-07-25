import type { ReactNode } from "react";
import { Icons } from "./battle-icons";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { Button } from "./ui/button";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

type BattleFilter = "all" | "red" | "blue" | "useful" | "receipt";

type Props = {
  playing: boolean;
  setPlaying: (value: boolean | ((prev: boolean) => boolean)) => void;
  speed: string;
  setSpeed: (value: string) => void;
  filter: BattleFilter;
  setFilter: (value: BattleFilter) => void;
  enabled: boolean;
  arm: () => void;
  highlightReel: boolean;
  onHighlightReelChange: (enabled: boolean) => void;
  onJumpToNextHighlight: () => void;
  receiptStreamButton?: ReactNode;
  adaptiveReceipt?: boolean;
};

export function BattleReceiptFooter({
  playing,
  setPlaying,
  speed,
  setSpeed,
  filter,
  setFilter,
  enabled,
  arm,
  highlightReel,
  onHighlightReelChange,
  onJumpToNextHighlight,
  receiptStreamButton,
  adaptiveReceipt = false,
}: Props) {
  useRegisterAction("battle:control:playhead", { action: "BATTLE_REPLAY_PLAYHEAD_TOGGLE", label: "Toggle Battle Playhead", description: "Play or pause receipt-backed Battle replay", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:sound-arm", { action: "BATTLE_SOUND_ARM", label: "Arm Battle Sound", description: "Arm sound for receipt-backed events with explicit cues", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:speed", { action: "BATTLE_SPEED_SET", label: "Set Battle Replay Speed", description: "Set receipt-backed replay speed", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:focus", { action: "BATTLE_FILTER_SET", label: "Set Battle Focus", description: "Filter receipt-backed Battle lanes", tags: ["battle", "receipt-backed"] });
  const focusOptions: ReadonlyArray<readonly [BattleFilter, string]> = adaptiveReceipt
    ? [
        ["all", "All"],
        ["useful", "Useful"],
        ["receipt", "Receipts"],
      ]
    : [
        ["all", "All"],
        ["red", "Red"],
        ["blue", "Blue"],
        ["useful", "Useful"],
        ["receipt", "Receipts"],
      ];

  return (
    <footer
      className="battle-receipt-footer grid items-center gap-x-3 border-t border-white/10 bg-[#0d1117] px-4"
      data-qid="battle:receipt-footer"
    >
      <div className="battle-receipt-footer-transport flex min-w-0 items-center gap-1.5">
        <Button data-qid="battle:control:playhead" data-qs-action="BATTLE_REPLAY_PLAYHEAD_TOGGLE" title={playing ? "Pause receipt replay playhead" : "Play receipt replay playhead"} variant={playing ? "green" : "outline"} size="icon" className="h-11 min-h-11 w-11 min-w-11" onClick={() => setPlaying((value) => !value)}>
          {playing ? <Icons.Pause className="h-3.5 w-3.5" /> : <Icons.Play className="h-3.5 w-3.5" />}
        </Button>
        <Button data-qid="battle:control:highlight-next" data-qs-action="BATTLE_HIGHLIGHT_NEXT" title="Jump playhead to next receipt-backed highlight" variant="outline" size="sm" className="h-11 min-h-11 px-3 text-xs" onClick={onJumpToNextHighlight}>Next</Button>
        <Button data-qid="battle:control:highlight-reel" data-qs-action="BATTLE_HIGHLIGHT_REEL_TOGGLE" title={highlightReel ? "Disable highlight-reel transport" : "Play highlight reel (jump between proven terminal beats)"} variant={highlightReel ? "green" : "outline"} size="sm" className="h-11 min-h-11 px-3 text-xs" onClick={() => onHighlightReelChange(!highlightReel)}>Highlights</Button>
        <Button data-qid="battle:control:sound-arm" data-qs-action="BATTLE_SOUND_ARM" title={enabled ? "Spectator mode live" : "Arm sound for receipt-backed events with explicit cues"} variant={enabled ? "green" : "outline"} size="sm" className="h-11 min-h-11 gap-1.5 px-3 text-xs" onClick={arm}>
          <Icons.Eye className="h-3.5 w-3.5" /> {enabled ? "Live" : "Arm"}
        </Button>
        <ToggleGroup className="h-11" data-qid="battle:control:speed" data-qs-action="BATTLE_SPEED_SET" title="Set receipt-backed replay speed" type="single" value={speed} onValueChange={(value) => value && setSpeed(value)}>
          {["1x", "2x", "4x", "8x"].map((item) => (
            <ToggleGroupItem key={item} data-qid={`battle:control:speed:${item}`} data-qs-action="BATTLE_SPEED_SET" title={`Set replay speed to ${item}`} value={item} className="h-11 min-h-11 min-w-11 px-3 text-xs">{item}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <div className="battle-receipt-footer-focus flex min-w-0 items-center justify-center">
        <div className="segmented-control" role="group" aria-label="Focus filter">
          {focusOptions.map(([id, label]) => (
            <button
              key={id}
              type="button"
              data-qid={`battle:toolbar:filter:${id}`}
              data-qs-action="BATTLE_FILTER_SET"
              title={`Focus ${label}`}
              className={`seg-btn seg-${id}${filter === id ? " is-active" : ""}`}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="battle-receipt-footer-proof flex shrink-0 items-center gap-2">{receiptStreamButton}</div>
    </footer>
  );
}
