import { cn } from "@/lib/utils";

export function Separator({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("h-px w-full bg-white/[0.075]", className)} />;
}
