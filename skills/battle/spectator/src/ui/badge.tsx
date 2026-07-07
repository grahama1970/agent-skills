import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-bold uppercase tracking-[.08em] transition-colors",
  {
    variants: {
      variant: {
        default: "border-white/10 bg-white/[.04] text-slate-300",
        red: "border-battle-red/35 bg-battle-red/12 text-battle-red",
        blue: "border-battle-blue/35 bg-battle-blue/12 text-battle-blue",
        green: "border-battle-green/35 bg-battle-green/12 text-battle-green",
        yellow: "border-battle-yellow/35 bg-battle-yellow/12 text-battle-yellow",
        purple: "border-battle-purple/35 bg-battle-purple/12 text-battle-purple"
      }
    },
    defaultVariants: { variant: "default" }
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}
function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
export { Badge, badgeVariants };
