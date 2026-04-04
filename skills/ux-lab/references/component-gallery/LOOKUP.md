# Component Vocabulary Lookup

When an agent or human describes a UI element, map to the canonical OpenPencil component.

## Term Disambiguation

| User Says | Canonical Component | Notes |
|-----------|-------------------|-------|
| button, btn, CTA | ActionButton | Primary, secondary, ghost, danger variants |
| toggle, switch | ToggleSwitch | Boolean on/off control |
| checkbox, check | Checkbox | Multi-select boolean |
| radio, option | RadioGroup | Single-select from list |
| dropdown, select, picker | Select | Single-value dropdown |
| combobox, autocomplete | ComboBox | Filterable dropdown |
| text field, input, text box | TextInput | Single-line text entry |
| textarea, multi-line | TextArea | Multi-line text entry |
| search, search bar | SearchInput | TextInput with search icon + clear |
| tab, tabs, tab bar | TabBar | Horizontal navigation tabs |
| sidebar, drawer, panel | SidePanel | Collapsible side navigation |
| breadcrumb, path | Breadcrumb | Hierarchical location indicator |
| nav, navbar, header | TopBar | Horizontal navigation bar |
| card, tile | Card | Contained content surface |
| table, grid, data grid | DataTable | Tabular data display |
| list, item list | ListView | Vertical item collection |
| tree, tree view | TreeView | Hierarchical expandable list |
| modal, dialog, popup | Modal | Overlay dialog with backdrop |
| toast, notification, snackbar | Toast | Temporary status message |
| tooltip, hint | Tooltip | Hover-triggered info |
| badge, chip, tag | Badge | Small label/counter |
| progress, loader, spinner | ProgressIndicator | Loading/progress state |
| alert, banner | Alert | Persistent status message |
| divider, separator, hr | Divider | Visual section separator |
| spacer, gap | Spacer | Layout spacing element |
| avatar, profile pic | Avatar | User/entity image circle |
| icon, glyph | Icon | Lucide icon reference |
| chart, graph, viz | Chart | Data visualization (via /create-figure) |
| form, fieldset | FormGroup | Grouped input container |
| accordion, collapsible | Accordion | Expandable content sections |
| menu, context menu, right-click | ContextMenu | Action list overlay |
| toolbar, action bar | Toolbar | Horizontal action buttons |
| stepper, wizard | Stepper | Multi-step flow indicator |
| slider, range | Slider | Numeric range control |
| color picker | ColorPicker | HSV color selector |
| date picker, calendar | DatePicker | Date selection control |
| file upload, dropzone | FileUpload | File input with drag-drop |
| skeleton, placeholder | SkeletonLoader | Content loading placeholder |
| empty state, no data | EmptyState | Zero-content placeholder |
| error page, 404 | ErrorState | Error display with action |
| dashboard | DashboardLayout | Grid of cards and charts |
| settings, preferences | SettingsLayout | Form-based configuration |
| kanban, board | KanbanBoard | Column-based card layout |

## NVIS Token Mapping

All components use NVIS MIL-STD-3009 design tokens for dark-mode compliance:

| Token | CSS Variable | Usage |
|-------|-------------|-------|
| Background | `--nvis-bg-primary` | Component surfaces |
| Background Alt | `--nvis-bg-secondary` | Elevated surfaces, cards |
| Text | `--nvis-text-primary` | Primary labels |
| Text Muted | `--nvis-text-secondary` | Secondary/hint text |
| Accent | `--nvis-accent` | Active states, selections |
| Border | `--nvis-border` | Component borders |
| Success | `--nvis-success` | Positive feedback |
| Warning | `--nvis-warning` | Caution indicators |
| Error | `--nvis-error` | Error states |

## Platform Translations

| Figma | OpenPencil | Tailwind/React | KDE/QML |
|-------|-----------|----------------|---------|
| Frame | Frame | div/section | Item |
| Rectangle | Rectangle | div | Rectangle |
| Text | Text | span/p | Text |
| Auto Layout | Yoga Flex | flex | RowLayout/ColumnLayout |
| Component | Component | React Component | QML Component |
| Instance | Instance | JSX usage | Loader |
| Fill | fill | bg-* | color |
| Stroke | stroke | border-* | border |
| Effects | effects | shadow-* | DropShadow |
