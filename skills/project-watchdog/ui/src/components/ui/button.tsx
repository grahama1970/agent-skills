import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  tone?: 'primary' | 'ghost' | 'danger';
}

const tones = {
  primary: 'border-cyan-300/40 bg-cyan-300/15 text-cyan-100 hover:bg-cyan-300/25',
  ghost: 'border-white/10 bg-white/[0.04] text-slate-100 hover:bg-white/[0.08]',
  danger: 'border-rose-300/40 bg-rose-300/15 text-rose-100 hover:bg-rose-300/25',
};

export function Button({ children, className, tone = 'ghost', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-xl border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40',
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
