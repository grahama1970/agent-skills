import { Icons } from "./battle-icons";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { cn } from "./lib/utils";

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
};

export function BattleMockupFooter({ playing, setPlaying, speed, setSpeed, filter, setFilter, enabled, arm }: Props) {
  useRegisterAction("battle:footer:spectator-arm", { action: "BATTLE_SOUND_ARM", label: "Arm Battle Spectator Sound", description: "Arm local sound cues for Battle spectator mode.", tags: ["battle", "design"] });
  useRegisterAction("battle:footer:speed", { action: "BATTLE_SPEED_SET", label: "Set Battle Replay Speed", description: "Set Battle design-view replay speed.", tags: ["battle", "design"] });
  useRegisterAction("battle:footer:focus", { action: "BATTLE_FILTER_SET", label: "Set Battle Lane Focus", description: "Filter visible Battle lanes in design view.", tags: ["battle", "design"] });
  useRegisterAction("battle:footer:playhead", { action: "BATTLE_REPLAY_PLAYHEAD_TOGGLE", label: "Toggle Battle Playhead", description: "Play or pause the Battle timeline playhead.", tags: ["battle", "design"] });

  return (
    <footer className="footer flex h-[64px] items-center justify-between gap-3 rounded-xl border border-[rgba(90,173,255,.07)] bg-[rgba(4,10,18,.45)] px-3 text-[11.5px] text-[#4a5e75]">
      <button
        type="button"
        data-qid="battle:footer:spectator-arm"
        data-qs-action="BATTLE_SOUND_ARM"
        title="Arm sound for Battle spectator mode"
        className="liveBadge inline-flex min-h-11 items-center gap-1.5 font-extrabold text-battle-green focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
        onClick={arm}
      >
        <Icons.Eye className="h-3.5 w-3.5" /> Spectator Mode · <span className="h-1.5 w-1.5 rounded-full bg-battle-green shadow-greenGlow" /> {enabled ? "LIVE" : "ARM"}
      </button>
      <div className="footerControls flex flex-1 flex-wrap items-center justify-center gap-2.5">
        <div className="playback flex items-center gap-1">
          <span className="mr-1.5 text-[10px] font-bold text-[#5a6e85]">SPEED</span>
          {["1x", "2x", "4x", "8x"].map((item) => (
            <button
              key={item}
              type="button"
              data-qid={`battle:footer:speed:${item}`}
              data-qs-action="BATTLE_SPEED_SET"
              title={`Set replay speed to ${item}`}
              className={cn(
                "footChip min-h-11 rounded-[7px] border px-2.5 text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40",
                speed === item ? "border-[rgba(60,240,122,.35)] bg-[rgba(60,240,122,.09)] text-[#a0ffc0]" : "border-[rgba(90,173,255,.1)] bg-[rgba(4,10,18,.55)] text-[#8a9eb8]",
              )}
              onClick={() => setSpeed(item)}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="focusChips flex items-center gap-1">
          <span className="mr-1.5 text-[10px] font-bold text-[#5a6e85]">FOCUS</span>
          {(
            [
              ["all", "All Lanes"],
              ["red", "Red Team"],
              ["blue", "Blue Team"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              data-qid={`battle:footer:focus:${id}`}
              data-qs-action="BATTLE_FILTER_SET"
              title={`Focus Battle lanes: ${label}`}
              className={cn(
                "footChip min-h-11 rounded-[7px] border px-2.5 text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40",
                filter === id ? "border-[rgba(60,240,122,.35)] bg-[rgba(60,240,122,.09)] text-[#a0ffc0]" : "border-[rgba(90,173,255,.1)] bg-[rgba(4,10,18,.55)] text-[#8a9eb8]",
              )}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="playback flex items-center gap-1">
          <span className="mr-1.5 text-[10px] font-bold text-[#5a6e85]">VIEW</span>
          {["☰", "▥", "▦"].map((glyph, index) => (
            <span key={glyph} className={cn("footChip grid h-[30px] min-w-[30px] place-items-center rounded-[7px] border px-2 text-[11px] font-semibold", index === 2 ? "border-[rgba(60,240,122,.35)] bg-[rgba(60,240,122,.09)] text-[#a0ffc0]" : "border-[rgba(90,173,255,.1)] bg-[rgba(4,10,18,.55)] text-[#8a9eb8]")}>{glyph}</span>
          ))}
        </div>
      </div>
      <button
        type="button"
        data-qid="battle:footer:playhead"
        data-qs-action="BATTLE_REPLAY_PLAYHEAD_TOGGLE"
        title={playing ? "Pause Battle playhead" : "Play Battle playhead"}
        className="fit min-h-11 min-w-11 rounded-lg border border-[rgba(90,173,255,.12)] bg-[rgba(4,10,18,.55)] px-3 py-1.5 text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
        onClick={() => setPlaying((value) => !value)}
      >
        {playing ? <Icons.Pause className="h-4 w-4" /> : "⛶"}
      </button>
    </footer>
  );
}
