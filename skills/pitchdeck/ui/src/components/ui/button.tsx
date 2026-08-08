/**
 * shadcn Button, adapted to this app's NON-NEGOTIABLE interaction contract.
 *
 * Every interactive element must carry data-qid, data-qs-action and title at
 * write time (best-practices-react), so those three are REQUIRED props here
 * rather than optional pass-through: a Button that cannot be selected by a test
 * manifest or driven by an agent is not shippable, and making them required
 * moves that from a review comment to a compile error.
 *
 * useRegisterAction stays in the CALLER's component body — hooks must run at the
 * top level of a component, and registering from inside this primitive would
 * fire it wherever a Button happens to render, including inside .map().
 */
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '../../lib/utils'

const buttonVariants = cva(
  // focus-visible, never focus: a mouse click must not paint a focus ring
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ' +
    'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ' +
    'focus-visible:ring-[var(--ring)] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90',
        secondary: 'bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:opacity-90',
        outline: 'border border-[var(--border)] bg-transparent hover:bg-[var(--accent)]',
        ghost: 'hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)]',
        destructive: 'bg-[var(--destructive)] text-[var(--primary-foreground)] hover:opacity-90',
        link: 'text-[var(--primary)] underline-offset-4 hover:underline',
      },
      size: {
        sm: 'h-8 rounded-md px-3 text-xs',
        default: 'h-9 px-4 py-2',
        lg: 'h-10 rounded-md px-6',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  /** Stable selector for test manifests and CDP automation: component:element:qualifier */
  'data-qid': string
  /** QuerySpec action id an agent resolves intent to: COMPONENT_ACTION */
  'data-qs-action': string
  /** Human-readable label (MIL-STD-1472H, screen readers, tooltips) */
  title: string
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  },
)
Button.displayName = 'Button'

export { Button, buttonVariants }
