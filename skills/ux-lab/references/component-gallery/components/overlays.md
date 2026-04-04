# Overlays Components

## Modal
Overlay dialog with backdrop. Traps focus and dismisses on Escape.
**Props:** open, title, children, actions, size (sm/md/lg/full)
**NVIS:** `bg-[var(--nvis-bg-surface)]` with `bg-black/60` backdrop

## Tooltip
Hover-triggered info popup with arrow.
**Props:** content, placement (top, bottom, left, right), delay
**NVIS:** `bg-[var(--nvis-bg-elevated)] text-[var(--nvis-text-label)]` shadow-lg

## ContextMenu
Positioned action list (see also actions.md).
**Props:** items, position (x, y), onClose
**NVIS:** `bg-[var(--nvis-bg-surface)]` with divider support

## Dropdown
Click-triggered content overlay anchored to trigger element.
**Props:** trigger, children, placement, offset
**NVIS:** `bg-[var(--nvis-bg-surface)] border border-[var(--nvis-bg-elevated)] shadow-xl`

## Popover
Rich content overlay with optional arrow and close button.
**Props:** trigger, content, placement, closeable
**NVIS:** Same surface tokens as Dropdown with `max-w-sm`
