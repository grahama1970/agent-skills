# Feedback Components

## Toast
Temporary status message that auto-dismisses.
**Props:** message, variant (success, warning, error, info), duration
**NVIS:** Uses `--nvis-status-*` colors per variant, `bg-[var(--nvis-bg-surface)]` base

## Alert
Persistent status message with optional action.
**Props:** title, message, variant, action, dismissible
**NVIS:** Left border accent using `--nvis-status-*` per variant

## ProgressIndicator
Loading/progress state display. Variants: bar, spinner, skeleton.
**Props:** value (0-100 or indeterminate), variant, label
**NVIS:** Fill: `bg-[var(--nvis-accent)]` Track: `bg-[var(--nvis-bg-elevated)]`

## Badge
Small label or counter attached to elements.
**Props:** label, variant (default, success, warning, error), size
**NVIS:** Default: `bg-[var(--nvis-accent)] text-[var(--nvis-bg-dark)]` rounded-full

## SkeletonLoader
Content loading placeholder with pulse animation.
**Props:** width, height, variant (text, circle, rect)
**NVIS:** `bg-[var(--nvis-bg-elevated)] animate-pulse rounded`

## EmptyState
Zero-content placeholder with illustration and action.
**Props:** icon, title, description, action
**NVIS:** `text-[var(--nvis-text-dim)]` centered layout
