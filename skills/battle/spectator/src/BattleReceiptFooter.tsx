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
}: Props) {
  useRegisterAction("battle:control:playhead", { action: "BATTLE_REPLAY_PLAYHEAD_TOGGLE", label: "Toggle Battle Playhead", description: "Play or pause receipt-backed Battle replay", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:sound-arm", { action: "BATTLE_SOUND_ARM", label: "Arm Battle Sound", description: "Arm sound for receipt-backed events with explicit cues", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:speed", { action: "BATTLE_SPEED_SET", label: "Set Battle Replay Speed", description: "Set receipt-backed replay speed", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:control:focus", { action: "BATTLE_FILTER_SET", label: "Set Battle Focus", description: "Filter receipt-backed Battle lanes", tags: ["battle", "receipt-backed"] });

  return (
    <footer className="flex min-h-[56px] items-center justify-between gap-3 rounded-2xl border border-white/10 bg-battle-panel/80 px-3 py-2 shadow-acrylic backdrop-blur-xl" data-qid="battle:receipt-footer">
      <div className="flex min-w-0 items-center gap-3">
        <Button data-qid="battle:control:playhead" data-qs-action="BATTLE_REPLAY_PLAYHEAD_TOGGLE" title={playing ? "Pause receipt replay playhead" : "Play receipt replay playhead"} variant={playing ? "green" : "outline"} size="icon" className="min-h-11 min-w-11" onClick={() => setPlaying((value) => !value)}>
          {playing ? <Icons.Pause className="h-4 w-4" /> : <Icons.Play className="h-4 w-4" />}
        </Button>
        <Button data-qid="battle:control:highlight-next" data-qs-action="BATTLE_HIGHLIGHT_NEXT" title="Jump playhead to next receipt-backed highlight" variant="outline" size="sm" className="min-h-11" onClick={onJumpToNextHighlight}>Next highlight</Button>
        <Button data-qid="battle:control:highlight-reel" data-qs-action="BATTLE_HIGHLIGHT_REEL_TOGGLE" title={highlightReel ? "Disable highlight-reel transport" : "Play highlight reel (jump between proven terminal beats)"} variant={highlightReel ? "green" : "outline"} size="sm" className="min-h-11" onClick={() => onHighlightReelChange(!highlightReel)}>{highlightReel ? "Highlights on" : "Highlights"}</Button>
        <span className="battle-label mr-2 hidden sm:inline">Spectator mode</span>
        <Button data-qid="battle:control:sound-arm" data-qs-action="BATTLE_SOUND_ARM" title="Arm sound for receipt-backed events with explicit cues" variant="outline" size="sm" className="min-h-11" onClick={arm}>
          <Icons.Eye className="h-4 w-4" /> Spectator mode <span className={enabled ? "text-battle-green" : "text-slate-500"}>{enabled ? "LIVE" : "click to arm"}</span>
        </Button>
        <span className="battle-label mr-2 hidden sm:inline">Speed</span>
        <ToggleGroup className="min-h-11" data-qid="battle:control:speed" data-qs-action="BATTLE_SPEED_SET" title="Set receipt-backed replay speed" type="single" value={speed} onValueChange={(value) => value && setSpeed(value)}>
          {["1x", "2x", "4x", "8x"].map((item) => (
            <ToggleGroupItem key={item} data-qid={`battle:control:speed:${item}`} data-qs-action="BATTLE_SPEED_SET" title={`Set replay speed to ${item}`} value={item} className="h-11 min-h-11 min-w-11 px-3">{item}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <div className="flex min-w-0 flex-1 items-center justify-center gap-2">
        <span className="battle-label mr-2">Focus</span>
        {([
          ["all", "All Lanes"],
          ["red", "Red Team"],
          ["blue", "Blue Team"],
          ["useful", "Useful"],
          ["receipt", "Receipts"],
        ] as const).map(([id, label]) => (
          <Button key={id} data-qid={`battle:toolbar:filter:${id}`} data-qs-action="BATTLE_FILTER_SET" title={`Focus ${label}`} variant={filter === id ? "green" : "outline"} size="sm" className="min-h-11" onClick={() => setFilter(id)}>{label}</Button>
        ))}
      </div>

      <div className="flex shrink-0 items-center gap-2">{receiptStreamButton}</div>
    </footer>
  );
}
