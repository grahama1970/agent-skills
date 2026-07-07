import { motion, useReducedMotion } from "motion/react";
import { cn } from "./lib/utils";
import { Icons } from "./battle-icons";

export function RunnerHud({ state, verb, selected }: { state: string; verb?: string; selected?: boolean }) {
  const reduceMotion = useReducedMotion();
  const Icon = iconForState(state);
  const tone = toneForState(state);
  const animate = !reduceMotion && (state === "blocked" || state === "retry" || state === "research");

  return (
    <div className="relative">
      <motion.div
        initial={false}
        animate={animate ? { y: [0, -2, 0], scale: selected ? [1, 1.04, 1] : [1, 1.02, 1] } : undefined}
        transition={animate ? { duration: state === "blocked" ? 1.3 : 1.8, repeat: Infinity } : undefined}
        className={cn(
          "grid h-11 w-11 place-items-center rounded-full border bg-battle-panel2 shadow-acrylic",
          selected && "ring-2 ring-battle-green/35",
          tone
        )}
        title={`Runner: ${state}${verb ? ` · ${verb}` : ""}`}
      >
        <Icon className="h-5 w-5" />
      </motion.div>
    </div>
  );
}

function iconForState(state: string) {
  switch (state) {
    case "research":
      return Icons.Search;
    case "stderr":
      return Icons.Terminal;
    case "self_heal":
      return Icons.Wrench;
    case "mutate":
      return Icons.Dna;
    case "retry":
      return Icons.RefreshCw;
    case "detected":
      return Icons.Radar;
    case "blocked":
    case "blocked_handoff":
      return Icons.ShieldX;
    case "killed":
      return Icons.Skull;
    case "promoted":
      return Icons.ShieldCheck;
    case "fastest_crash":
      return Icons.Rocket;
    default:
      return Icons.Bug;
  }
}

function toneForState(state: string) {
  switch (state) {
    case "blocked":
    case "blocked_handoff":
      return "border-battle-blue/80 text-battle-blue shadow-blueGlow";
    case "killed":
      return "border-battle-red/80 text-battle-red shadow-redGlow";
    case "promoted":
    case "fastest_crash":
      return "border-battle-green/80 text-battle-green shadow-greenGlow";
    case "research":
      return "border-battle-cyan/50 text-battle-cyan shadow-blueGlow";
    case "retry":
    case "useful":
      return "border-battle-yellow/70 text-battle-yellow shadow-yellowGlow";
    default:
      return "border-battle-red/55 text-battle-red shadow-redGlow";
  }
}
