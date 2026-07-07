import { Button } from "./ui/button";
import { Icons } from "./battle-icons";
import { useRegisterAction } from "./hooks/useRegisterAction";

export type BattleFilter = "all" | "red" | "blue" | "useful" | "handoff" | "receipt";

type Props = {
  mode: string;
  setMode: (value: string) => void;
  filter: BattleFilter;
  setFilter: (value: BattleFilter) => void;
  query: string;
  setQuery: (value: string) => void;
};

const filters: Array<{ id: BattleFilter; label: string; icon: React.ReactNode }> = [
  { id: "all", label: "All", icon: <Icons.Activity className="h-4 w-4" /> },
  { id: "red", label: "Red", icon: <Icons.Bug className="h-4 w-4" /> },
  { id: "blue", label: "Blue", icon: <Icons.Shield className="h-4 w-4" /> },
  { id: "useful", label: "Useful", icon: <Icons.Lightbulb className="h-4 w-4" /> },
  { id: "handoff", label: "Handoffs", icon: <Icons.GitBranch className="h-4 w-4" /> },
  { id: "receipt", label: "Receipts", icon: <Icons.FileJson className="h-4 w-4" /> }
];

export function BattleToolbar({ mode, setMode, filter, setFilter, query, setQuery }: Props) {
  useRegisterAction("battle:toolbar:search", { action: "BATTLE_SEARCH", label: "Search Battle", description: "Search receipt-backed Battle lanes and events.", tags: ["battle"] });
  useRegisterAction("battle:toolbar:filter", { action: "BATTLE_FILTER_SET", label: "Set Battle Filter", description: "Filter visible Battle lanes and events.", tags: ["battle"] });
  useRegisterAction("battle:toolbar:mode", { action: "BATTLE_MODE_SET", label: "Set Battle View Mode", description: "Set the Battle spectator focus mode.", tags: ["battle"] });

  return (
    <section className="flex min-h-[54px] items-center justify-between gap-3 rounded-2xl border border-white/10 bg-battle-panel/70 px-3 py-2 shadow-acrylic backdrop-blur-xl">
      <label className="relative w-[300px] shrink-0">
        <Icons.Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
        <input data-qid="battle:toolbar:search" data-qs-action="BATTLE_SEARCH" title="Search payload, agent, or receipt" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search payload, agent, receipt..." className="h-11 w-full rounded-xl border border-white/10 bg-black/20 pl-9 pr-3 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-battle-cyan/40" />
      </label>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {filters.map((item) => (
          <Button key={item.id} data-qid={`battle:toolbar:filter:${item.id}`} data-qs-action="BATTLE_FILTER_SET" title={`Show ${item.label} Battle events`} variant={filter === item.id ? "green" : "outline"} size="sm" className="min-h-11" onClick={() => setFilter(item.id)}>
            {item.icon} {item.label}
          </Button>
        ))}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {["spectator", "judge", "ops"].map((item) => (
          <Button key={item} data-qid={`battle:toolbar:mode:${item}`} data-qs-action="BATTLE_MODE_SET" title={`Switch to ${item} view`} variant={mode === item ? "green" : "outline"} size="sm" className="min-h-11 min-w-11 uppercase" onClick={() => setMode(item)}>
            {item.slice(0, 1)}
          </Button>
        ))}
      </div>
    </section>
  );
}
