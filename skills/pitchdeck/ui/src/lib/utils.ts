/**
 * Class-name merge used by every shadcn primitive.
 *
 * clsx resolves conditionals; tailwind-merge then drops earlier classes that a
 * later one overrides, so a caller's `className` genuinely wins instead of
 * fighting the variant in specificity order.
 */
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
