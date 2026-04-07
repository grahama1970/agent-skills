# Chart Design Principles for Architecture Diagrams

Target canvas: ~1200x800px (typical browser viewport minus left pane and inspector).

## BAD Examples (what we keep doing wrong)

### 1. Hardcoded spacing ignoring node count
```
row_h = 140   # ← fixed 140px per row
10 rows × 140 = 1400px tall → diagram scrolls off screen
```
**Why it's bad:** The spacing doesn't adapt to how many nodes exist. 5-node diagrams waste space; 12-node diagrams overflow.

### 2. Box too wide for canvas
```
box_w = 420, col_w = 520
3 columns: 420 + 520 + 520 = 1460px → overflows 1200px canvas
```
**Why it's bad:** Columns calculated without knowing how many columns exist or the canvas width.

### 3. Giant gaps between rows
```
row_h = 105, box_h = 50
Gap between boxes: 105 - 50 = 55px of dead space
```
**Why it's bad:** More gap than content. Arrows have room but the diagram looks like a todo list, not an architecture.

### 4. Font size not proportional to box
```
box_h = 50, fontSize = 16
Two lines of text at 16px × 1.2 lineHeight = 38.4px → barely fits
```
**Why it's bad:** Text overflows or gets clipped. Font should be chosen AFTER box size is known.

### 5. Not accounting for branch columns
```
Main flow: col 0 (280px wide)
CLARIFY: col 1 (280px wide, offset 340px)
NO_MATCH: col 2 (280px wide, offset 680px)
Total: 280 + 340 + 340 = 960px — but only if centered properly
```
**Why it's bad:** The main flow column is left-aligned, wasting the right half. Branch columns push content off-screen.

## GOOD Design Rules

### Rule 1: Compute from canvas, not from constants
```python
TARGET_W = 1100  # usable canvas width (minus 50px margin each side)
TARGET_H = 750   # usable canvas height (minus toolbar + bottom bar)

max_row = max(comp.get("row", 0) for comp in components)
max_col = max(comp.get("col", 0) for comp in components)

# Derive spacing from canvas and node count
row_h = TARGET_H / (max_row + 1)
col_w = TARGET_W / (max_col + 1) if max_col > 0 else TARGET_W
```

### Rule 2: Box fills 70-80% of its grid cell
```python
box_w = int(col_w * 0.7)   # 70% of column width
box_h = int(row_h * 0.55)  # 55% of row height (leaves room for arrows)
```

### Rule 3: Font scales with box
```python
# Title text: 60% of box height for single line
fontSize = max(10, min(16, int(box_h * 0.3)))
```

### Rule 4: Center the diagram in canvas
```python
# Offset so col 0 isn't at x=0
margin_x = (TARGET_W - (max_col + 1) * col_w) / 2 + 50
margin_y = 50  # below toolbar
```

### Rule 5: Arrow gap is proportional, not fixed
```python
arrow_gap = max(4, int(row_h * 0.05))  # 5% of row height, min 4px
```

## Quick Reference: Canvas-Aware Layout

For a 12-node pipeline with 10 rows × 3 columns on 1200×800 canvas:
- `row_h = 750 / 10 = 75px`
- `col_w = 1100 / 3 = 367px`
- `box_w = 367 * 0.7 = 257px`
- `box_h = 75 * 0.55 = 41px`
- `fontSize = max(10, min(16, 41 * 0.3)) = 12px`
- `arrow_gap = max(4, 75 * 0.05) = 4px`
- Total height: 10 × 75 + 50 margin = 800px ← fits viewport

For a 5-node simple pipeline with 5 rows × 1 column:
- `row_h = 750 / 5 = 150px`
- `col_w = 1100`
- `box_w = 1100 * 0.4 = 440px` (cap at 40% for single column)
- `box_h = 150 * 0.55 = 82px`
- `fontSize = max(10, min(16, 82 * 0.3)) = 16px`
- Total height: 5 × 150 + 50 = 800px ← fits viewport
