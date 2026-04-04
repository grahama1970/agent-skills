# Actions Components

## ActionButton
Primary interactive control. Variants: primary, secondary, ghost, danger, icon-only.

**Props:** label, variant, size (sm/md/lg), icon, disabled, loading
**Tailwind:** `bg-teal-600 hover:bg-teal-500 text-white px-4 py-2 rounded-lg font-medium`
**NVIS:** `bg-[var(--nvis-accent)] text-[var(--nvis-bg-dark)]`

### Variants
- **Primary**: Teal background, dark text — primary actions (Save, Submit, Confirm)
- **Secondary**: Border only, teal text — secondary actions (Cancel, Back)
- **Ghost**: No border, teal text on hover — tertiary actions (More, Details)
- **Danger**: Red background — destructive actions (Delete, Remove)
- **Icon-only**: Square, icon centered — toolbar buttons

## ToggleSwitch
Boolean on/off control with animated transition.
**Props:** checked, label, disabled
**NVIS:** Track: `bg-[var(--nvis-bg-elevated)]` Off / `bg-[var(--nvis-accent)]` On

## ContextMenu
Right-click action list. Appears at cursor position, dismisses on click-away.
**Props:** items (label, icon, action, divider, disabled)
**NVIS:** `bg-[var(--nvis-bg-surface)] border border-[var(--nvis-bg-elevated)] shadow-xl`

## Toolbar
Horizontal strip of icon buttons with optional separators.
**Props:** items, orientation (horizontal/vertical)
**NVIS:** `bg-[var(--nvis-bg-elevated)] border-b border-[var(--nvis-bg-surface)]`
