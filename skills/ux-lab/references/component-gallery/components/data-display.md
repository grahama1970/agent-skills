# Data Display Components

## DataTable
Tabular data with sortable columns and row selection.
**Props:** columns (key, label, sortable), rows, onSort, onSelect
**NVIS:** Header: `bg-[var(--nvis-bg-elevated)]` Rows: `bg-[var(--nvis-bg-dark)]` alternate

## Card
Contained content surface with optional header and footer.
**Props:** title, children, actions, elevation
**NVIS:** `bg-[var(--nvis-bg-surface)] border border-[var(--nvis-bg-elevated)] rounded-lg`

## ListView
Vertical item collection with optional icons and actions.
**Props:** items (label, icon, description, action), onItemClick
**NVIS:** Hover: `bg-[var(--nvis-bg-elevated)]` with accent left border on active

## TreeView
Hierarchical expandable list with indent guides.
**Props:** nodes (label, children, expanded, icon), onToggle
**NVIS:** Indent guides at `opacity-45` of `--nvis-text-dim`

## Chart
Data visualization wrapper (delegates to /create-figure).
**Props:** type (bar, line, pie, scatter), data, options
**NVIS:** Uses `--nvis-accent` as primary series color

## Avatar
User/entity image circle with fallback initials.
**Props:** src, name, size (sm/md/lg)
**NVIS:** Fallback: `bg-[var(--nvis-accent)] text-[var(--nvis-bg-dark)]`
