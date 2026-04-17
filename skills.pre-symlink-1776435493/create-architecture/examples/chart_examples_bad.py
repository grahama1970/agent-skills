"""Bad chart design examples (anti-patterns) for batch-learning into /memory.

Contains BAD example dicts used by learn_chart_examples.py to teach
/create-architecture what NOT to do: hardcoded pixels, overlapping boxes,
misused colors, and broken connection routing.
"""
BAD = [
    {
        "problem": "BAD chart-design: Hardcoded pixel constants ignoring node count. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
row_h = 140  # fixed constant
spacing = 60  # fixed constant
10 nodes \u00d7 (140 + 60) = 2000px tall \u2192 diagram scrolls off screen

FIX: Compute row_h from canvas height and node count:
row_h = CANVAS_H / n_rows  # adapts to content

RULE VIOLATED: Rule 1 \u2014 compute from canvas, not from constants.
5-node diagrams waste space. 12-node diagrams overflow.
The SAME hardcoded values can't work for both.""",
        "tags": ["bad-example", "hardcoded-spacing", "overflow"],
    },
    {
        "problem": "BAD chart-design: Orphaned branch nodes disconnected from decision point. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Decision node at row 4, col 0.
CLARIFY branch at row 4, col 1 \u2014 but visually it floats far away.
NO_MATCH branch at row 4, col 2 \u2014 even further.
No visual connection to the decision that spawned them.

The branches look like independent components, not outcomes of a decision.
Reader can't tell which decision leads to which branch.

FIX: Branches must fork at the SAME ROW as the decision node.
Use columns to separate outcomes, not distance.
Draw direct arrows from decision \u2192 each branch.
Color-code branches (green=pass, red=fail) for instant comprehension.

RULE VIOLATED: Decision outcomes must be visually adjacent to their decision point.""",
        "tags": ["bad-example", "orphaned-branches", "disconnected"],
    },
    {
        "problem": "BAD chart-design: All nodes in single column with branches tacked on as distant satellites. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Main flow: 10 nodes stacked in col 0, rows 0-9.
CLARIFY: col 1, row 4 \u2014 connected by a long diagonal arrow.
NO_MATCH: col 2, row 4 \u2014 connected by an even longer diagonal arrow.
Both branches are orphaned far to the right.

This is NOT a decision tree \u2014 it's a linear list with Post-it notes stuck on the side.
The viewer's eye follows the main column and never notices the branches.

FIX: Convert to proper decision tree layout:
- Main flow in CENTER column (col 1, not col 0)
- Branches fork LEFT and RIGHT at each decision point
- Branch outcomes at the SAME ROW as the decision node
- Multiple decision points create a 'railroad with sidings' pattern

RULE VIOLATED: Never put all logic in one column with branches as afterthoughts.""",
        "tags": ["bad-example", "single-column", "linear-with-branches"],
    },
    {
        "problem": "BAD chart-design: Box too wide for canvas, overflowing viewport. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
box_w = 420, col_w = 520
3 columns: 420 + 520 + 520 = 1460px \u2192 overflows 1300px canvas
User must scroll horizontally to see the full diagram.

FIX: Compute box_w from canvas and column count:
col_w = CANVAS_W / n_cols  # 1300/3 = 433px
box_w = col_w * 0.7        # 433*0.7 = 303px
Total: 3 \u00d7 433 = 1299px \u2190 fits canvas

RULE VIOLATED: Rule 2 \u2014 box fills 70-80% of its grid cell.
Columns calculated without knowing how many columns exist.""",
        "tags": ["bad-example", "overflow", "too-wide"],
    },
    {
        "problem": "BAD chart-design: Giant gaps between rows, diagram looks like a todo list. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
row_h = 105, box_h = 50
Gap between boxes: 105 - 50 = 55px of dead space
More gap than content. Arrows have room but the diagram looks sparse.

5 nodes in 700px canvas should use row_h = 140px, box_h = 77px.
Not row_h = 105px with box_h = 50px.

FIX: box_h = row_h * 0.55 (55% of row height)
Gap = row_h * 0.45 \u2014 proportional, not fixed.

RULE VIOLATED: Rule 2 \u2014 box fills 70-80% of its grid cell width, 55% of height.
The visual weight should be in the BOXES, not the gaps.""",
        "tags": ["bad-example", "giant-gaps", "sparse"],
    },
    {
        "problem": "BAD chart-design: Font size not proportional to box, text overflows or is unreadable. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
box_h = 50, fontSize = 16
Two lines of text at 16px \u00d7 1.2 lineHeight = 38.4px \u2192 barely fits
Add padding (12px) \u2192 50.4px > 50px \u2192 text clips or overflows.

Even worse: subtitle (tech + latency) tries to render below label.
Two lines at 16px in a 50px box = guaranteed overflow.

FIX: Font scales with box:
fontSize = max(10, min(14, int(box_h * 0.3)))
For box_h=50: fontSize = max(10, min(14, 15)) = 14px
For box_h=38: fontSize = max(10, min(14, 11)) = 11px

SUBTITLE RULE: Only show subtitle if box_h >= fontSize * 1.2 * 2 + 12

RULE VIOLATED: Rule 3 \u2014 font scales with box. Font chosen AFTER box size is known.""",
        "tags": ["bad-example", "text-overflow", "font-size"],
    },
    {
        "problem": "BAD chart-design: Spaghetti arrows crossing over nodes. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Node A (row 0, col 0) connects to Node D (row 3, col 2).
Arrow drawn as straight diagonal \u2014 crosses over nodes B and C in between.
Multiple such cross-connections create an unreadable web.

FIX:
1. Use elbow (orthogonal) arrows, not diagonal
2. Route through empty grid cells only
3. For cross-column connections, use L-shaped routing with midpoint:
   - Go down to midpoint_y between source and target
   - Go across to target column at midpoint_y
   - Go down to target
4. If no empty cell exists, restructure the grid to create routing channels

RULE VIOLATED: Arrows should never cross over node boxes.
Use orthogonal routing with elbow arrows. Excalidraw: elbowed=true.""",
        "tags": ["bad-example", "spaghetti-arrows", "crossing"],
    },
    {
        "problem": "BAD chart-design: No decision diamond \u2014 using rectangles for decisions. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
'Validate' node is a rectangle (same as all other nodes).
It has two outgoing arrows but looks identical to processing nodes.
Reader can't distinguish 'do something' from 'decide something'.

FIX: Decision nodes use the \u25c7 prefix in their label:
  label: '\u25c7 Valid?' not 'Validate'
  color: amber (always \u2014 decisions are uncertain/pending)

The \u25c7 prefix triggers the layout engine to:
  1. Render as diamond shape (or diamond-styled rectangle)
  2. Apply amber color
  3. Expect exactly 2+ outgoing connections (branches)
  4. Place branch outcomes at the same row, different columns

RULE VIOLATED: Decision points must be visually distinct from processing steps.
Use \u25c7 prefix, amber color, and question-form labels.""",
        "tags": ["bad-example", "no-diamond", "missing-decision-shape"],
    },
    {
        "problem": "BAD chart-design: Diagram not centered, crammed into left third of canvas. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Single-column pipeline starts at x=40 (left margin).
box_w = 300px. Canvas is 1300px wide.
Right 960px of canvas is empty white space.
Diagram looks like it's hiding in the corner.

FIX: Center the grid in the canvas:
x_offset = MARGIN + (usable_w - n_cols * col_w) / 2
For single column: x_center = (1300 - 300) / 2 = 500px

Multi-column: center the entire grid, not individual columns.

RULE VIOLATED: Rule 4 \u2014 center the diagram in canvas.
The first column should not start at x=0 or x=MARGIN.""",
        "tags": ["bad-example", "not-centered", "left-aligned"],
    },
    {
        "problem": "BAD chart-design: Using random colors with no semantic meaning. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Node 1: purple (it's a database)
Node 2: green (it's an API endpoint)
Node 3: red (it's a cache \u2014 not an error!)
Node 4: blue (it's the error handler \u2014 should be red!)
Colors assigned randomly based on visual preference, not meaning.

FIX: Colors encode component TYPE or LATENCY, never aesthetics:
  purple = UI/presentation
  blue = data processing/search
  green = fast/deterministic/success
  amber = LLM/AI/decision
  red = error/failure/blocking
  dim = archived/background

Apply consistently. A database is green (fast). An error handler is red.
A decision point is amber. UI is purple. Always.

RULE VIOLATED: Color encodes type, not importance or aesthetics.
Consistent color = instant comprehension. Random color = visual noise.""",
        "tags": ["bad-example", "random-colors", "no-semantics"],
    },
    {
        "problem": "BAD chart-design: Branches going UPWARD, violating top-to-bottom flow. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
Main flow goes top-to-bottom (rows 0\u21929).
Error branch at row 7 has an arrow going UP to row 2 (retry).
The upward arrow crosses 5 rows of nodes.

This creates confusion: is the flow going up or down?
The eye naturally follows top\u2192bottom and gets confused by upward arrows.

FIX: Upward arrows should be RARE and visually distinct:
1. Route them along the RIGHT EDGE of the diagram (outside the main flow)
2. Use dashed or dim (#64748b) style to distinguish from main flow
3. Label them explicitly: 'retry', 'loop back'
4. Better yet: show the retry target at a LOWER row in a different column
   instead of creating an upward arrow

RULE VIOLATED: Main flow is ALWAYS top-to-bottom.
Loop-backs route around the outside, never through the center.""",
        "tags": ["bad-example", "upward-arrows", "flow-violation"],
    },
    {
        "problem": "BAD chart-design: Too many nodes for canvas, everything unreadable at 8px font. ANTI-PATTERN.",
        "solution": """WHAT WENT WRONG:
20 nodes in a single diagram. 15 rows.
row_h = 700/15 = 46px. box_h = 46*0.55 = 25px. font_size = max(10, 46*0.15) = 10px.
At 10px font in a 25px box, labels are truncated. Subtitles don't fit at all.
Everything is a smear of tiny colored rectangles.

FIX: Split into sub-diagrams:
- If n_rows > 12: consider splitting into 2 diagrams
- If box_h < 35px: definitely split
- Group related nodes into 'phases' and create one diagram per phase
- Link diagrams with labeled entry/exit points

Alternative: Use a 2-column layout instead of single column:
- Nodes A-J in col 0, nodes K-T in col 1
- Reduces rows from 20 to 10, doubling available height

RULE VIOLATED: Minimum readable box_h is ~35px at 10px font.
If computed box_h drops below this, the diagram needs restructuring.""",
        "tags": ["bad-example", "too-many-nodes", "unreadable"],
    },
]
