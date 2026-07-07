import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-battle-blue/18 text-battle-cyan border border-battle-blue/30 hover:bg-battle-blue/28",
        destructive: "bg-battle-red/15 text-battle-red border border-battle-red/30 hover:bg-battle-red/25",
        outline: "border border-white/10 bg-white/[.03] hover:bg-white/[.07] text-slate-200",
        ghost: "hover:bg-white/[.06] text-slate-300",
        green: "bg-battle-green/12 text-battle-green border border-battle-green/30 hover:bg-battle-green/20",
        yellow: "bg-battle-yellow/10 text-battle-yellow border border-battle-yellow/30 hover:bg-battle-yellow/18"
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10"
      }
    },
    defaultVariants: {
      variant: "default",
      size: "default"
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...(!asChild ? { type: "button" } : {})} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
