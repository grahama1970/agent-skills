import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded font-mono text-sm tracking-wide transition-colors disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-accent text-ground hover:bg-[#ffc472]',
        outline:
          'border border-line bg-transparent text-ink hover:border-accent',
      },
      size: {
        default: 'px-6 py-3',
        sm: 'px-4 py-2',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonLinkProps
  extends React.AnchorHTMLAttributes<HTMLAnchorElement>,
    VariantProps<typeof buttonVariants> {
  /** Stable selector, component:element:qualifier */
  'data-qid': string;
  /** QuerySpec action ID, COMPONENT_ACTION */
  'data-qs-action': string;
  /** Human-readable label (a11y + tooltip) */
  title: string;
}

export function ButtonLink({
  className,
  variant,
  size,
  ...props
}: ButtonLinkProps) {
  return (
    <a className={cn(buttonVariants({ variant, size, className }))} {...props} />
  );
}
