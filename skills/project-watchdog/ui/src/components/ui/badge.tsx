import type { ReactNode } from 'react';
import { cn } from '../../lib';
import type { GateStatus } from '../../types';

const variants: Record<GateStatus, string> = {
  PASS: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200',
  FAIL: 'border-rose-400/50 bg-rose-400/10 text-rose-200',
  BLOCKED: 'border-amber-400/50 bg-amber-400/10 text-amber-200',
  NEEDS_ATTENTION: 'border-orange-400/50 bg-orange-400/10 text-orange-200',
  DRY_RUN: 'border-sky-400/50 bg-sky-400/10 text-sky-200',
  SKIPPED: 'border-slate-400/40 bg-slate-400/10 text-slate-200',
  UNKNOWN: 'border-violet-400/40 bg-violet-400/10 text-violet-200',
};

export function GateBadge({ status, className }: { status: GateStatus; className?: string }) {
  return (
    <span
      className={cn('rounded-full border px-2.5 py-1 text-xs font-semibold tracking-[0.18em]', variants[status], className)}
    >
      {status}
    </span>
  );
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('rounded-full border border-white/10 bg-white/[0.06] px-2 py-1 text-xs text-slate-300', className)}>
      {children}
    </span>
  );
}
