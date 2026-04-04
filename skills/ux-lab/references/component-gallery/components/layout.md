# Layout Components

## Grid
Responsive grid container using CSS Grid or Yoga Flex.
**Props:** columns, gap, minChildWidth, children
**NVIS:** No visual tokens — structural only

## Panel
Bordered content section with optional header.
**Props:** title, collapsible, children, padding
**NVIS:** `bg-[var(--nvis-bg-surface)] border border-[var(--nvis-bg-elevated)] rounded-lg`

## Divider
Visual section separator, horizontal or vertical.
**Props:** orientation, label (optional centered text)
**NVIS:** `border-[var(--nvis-bg-elevated)]`

## Spacer
Layout spacing element for flex containers.
**Props:** size (xs/sm/md/lg/xl) or px value
**NVIS:** No visual tokens — structural only

## DashboardLayout
Grid of cards and charts with responsive breakpoints.
**Props:** widgets (component, span, order), columns
**NVIS:** Uses Panel and Card tokens for widget containers

## SettingsLayout
Form-based configuration layout with labeled sections.
**Props:** sections (title, fields), onSave
**NVIS:** Section headers use `text-[var(--nvis-text-label)]` uppercase
