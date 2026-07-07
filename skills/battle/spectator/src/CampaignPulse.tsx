import type { ReactNode } from "react";
import { battleEvents, lanes, receiptBackedFixture } from "./lib/battle-data";
import { Icons } from "./battle-icons";

export function CampaignPulse() {
  const scoreboard = receiptBackedFixture.scoreboard;
  const usefulSignals = lanes.reduce((count, lane) => count + lane.events.filter((event) => event.kind === "useful" && event.proven).length, 0);
  const blueBlocks = battleEvents.filter((event) => event.event_type === "blue.blocked_red").length;
  return (
    <section className="grid min-h-[54px] grid-cols-7 gap-0 rounded-2xl border border-white/10 bg-battle-panel/70 px-2 py-2 shadow-acrylic backdrop-blur-xl divide-x divide-white/10">
      <PulseItem icon={<Icons.Activity className="h-4 w-4" />} label="Active lineages" value={String(lanes.length)} tone="text-battle-green" />
      <PulseItem icon={<Icons.Dna className="h-4 w-4" />} label="Red workers" value={String(scoreboard?.red_materialized_count ?? lanes.length)} tone="text-battle-purple" />
      <PulseItem icon={<Icons.Lightbulb className="h-4 w-4" />} label="Useful signals" value={String(usefulSignals)} tone="text-battle-yellow" />
      <PulseItem icon={<Icons.GitBranch className="h-4 w-4" />} label="Judged pairs" value={String(scoreboard?.judged_pair_count ?? 0)} tone="text-battle-cyan" />
      <PulseItem icon={<Icons.Shield className="h-4 w-4" />} label="Blue blocks" value={String(blueBlocks || scoreboard?.blue_success_count || 0)} tone="text-battle-blue" />
      <PulseItem icon={<Icons.Skull className="h-4 w-4" />} label="Dead ends" value="0" tone="text-slate-400" />
      <PulseItem icon={<Icons.Rocket className="h-4 w-4" />} label="Fastest crash" value="—" tone="text-slate-500" />
    </section>
  );
}

function PulseItem({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string; tone: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3 px-3">
      <span className={tone}>{icon}</span>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-black uppercase tracking-[.12em] text-slate-500">{label}</div>
        <div className={`text-2xl font-black leading-none ${tone}`}>{value}</div>
      </div>
    </div>
  );
}
