# Inputs Components

## TextInput
Single-line text entry with optional label and validation.
**Props:** value, placeholder, label, error, disabled, icon
**NVIS:** `bg-[var(--nvis-bg-surface)] border border-[var(--nvis-bg-elevated)]` Focus: `border-[var(--nvis-accent)]`

## TextArea
Multi-line text entry with auto-resize option.
**Props:** value, placeholder, rows, maxLength
**NVIS:** Same as TextInput with `min-h-[80px]`

## SearchInput
TextInput variant with search icon and clear button.
**Props:** value, placeholder, onSearch, onClear
**NVIS:** Includes Lucide `Search` icon at `--nvis-text-dim`

## Select
Single-value dropdown with option list.
**Props:** value, options (label, value), placeholder
**NVIS:** Dropdown: `bg-[var(--nvis-bg-surface)] shadow-xl`

## ComboBox
Filterable dropdown with type-ahead search.
**Props:** value, options, filterFn, placeholder
**NVIS:** Combines TextInput focus ring with Select dropdown

## Checkbox
Boolean multi-select control.
**Props:** checked, label, indeterminate, disabled
**NVIS:** Checked: `bg-[var(--nvis-accent)]` with dark checkmark

## Slider
Numeric range control with track and thumb.
**Props:** value, min, max, step, label
**NVIS:** Track: `bg-[var(--nvis-bg-elevated)]` Fill: `bg-[var(--nvis-accent)]`
