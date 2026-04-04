# Navigation Components

## TabBar
Horizontal navigation tabs with active indicator.
**Props:** tabs (label, icon, id), activeId, onChange
**NVIS:** Active: `border-b-2 border-[var(--nvis-accent)] text-[var(--nvis-text-strong)]`

## Breadcrumb
Hierarchical location path with clickable segments.
**Props:** items (label, href), separator
**NVIS:** `text-[var(--nvis-text-secondary)]` with accent on hover

## SidePanel
Collapsible side navigation with icon + label items.
**Props:** items (label, icon, href, active), collapsed, width
**NVIS:** `bg-[var(--nvis-bg-elevated)]` with active item accent highlight

## TopBar
Horizontal navigation bar with logo, nav items, and actions.
**Props:** logo, items, actions
**NVIS:** `bg-[var(--nvis-bg-dark)] border-b border-[var(--nvis-bg-surface)]`

## Pagination
Page navigation with prev/next and page numbers.
**Props:** currentPage, totalPages, onPageChange
**NVIS:** Active page uses `bg-[var(--nvis-accent)]`
