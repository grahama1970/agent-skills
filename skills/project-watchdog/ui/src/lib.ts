import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function compactPath(path: string | null) {
  if (!path) return 'not recorded';
  return path.replace(/^\/home\/graham\//, '~/');
}

export function issueLabel(repo: string | null, issue: number | null) {
  if (!repo || issue == null) return 'watchdog tick';
  return `${repo}#${issue}`;
}
