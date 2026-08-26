import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.15em]",
  {
    variants: {
      variant: {
        default: "border-[var(--accent)]/25 bg-[var(--accent)]/10 text-[var(--accent)]",
        muted: "border-white/10 bg-white/[0.045] text-[var(--muted-foreground)]",
        warning: "border-amber-300/20 bg-amber-300/[0.08] text-amber-200",
        danger: "border-rose-300/20 bg-rose-300/[0.08] text-rose-200",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
