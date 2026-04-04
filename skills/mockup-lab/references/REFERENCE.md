## Spec File Format

The `--spec` file is a markdown document that tells Stitch what to build. Copy and fill
in the template at `docs/spec-template.md` (in this skill directory):

```markdown

## Views File Format (for `explore`)

The `--views` argument takes a JSON file — an array of `{ name, prompt }` objects:

```json
[
  { "name": "dashboard", "prompt": "Show the main dashboard view with..." },
  { "name": "settings", "prompt": "Show the settings page with..." }
]
```

- `name`: filename-safe identifier (becomes `<name>.png` in output)
- `prompt`: what to show in this view — be specific about content, layout, data

Each view gets its own Stitch `edit()` call. Results go to `<output>/<name>.png`
with a `manifest.json` index. Budget: 1 credit per view.

## Manifest Format (from `explore`)

```json
[
  { "view": "dashboard", "screenId": "abc123", "imagePath": "/path/to/dashboard.png" },
  { "view": "mixer", "screenId": "def456", "imagePath": "/path/to/mixer.png" },
  { "view": "settings", "error": "RATE_LIMITED — retry later" }
]
```

The agent should check `manifest.json` for errors and retry failed views.

## Human-in-the-Loop Handoff

The human reviews designs in the **Stitch browser** (live URL from `generate`).
The agent collects structured decisions via `/interview`:

```
1. Agent: ./run.sh iterate ... → new screen generated
2. Agent: "Review at https://stitch.withgoogle.com/projects/123"
3. Human: reviews in browser, sees the mockup
4. Agent: /interview "Which direction?" with options based on what Stitch generated
5. Human: picks option or provides free-text feedback
6. Agent: ./run.sh iterate --feedback "<human's feedback>"
7. Repeat until human approves
```

The agent does NOT ask "does this look good?" as a yes/no. It offers specific
choices based on what the mockup shows (layout A vs B, with/without sidebar, etc).

## Design System Files (Source of Truth)

Three files define the Embry OS design system. All must agree. If they diverge, `EmbryStyle.ts` wins.

| File | Location | Purpose |
|------|----------|---------|
| `EmbryStyle.ts` | `packages/ux-lab/src/components/sparta/common/EmbryStyle.ts` | Runtime tokens for React components (import this) |
| `design-tokens.json` | `packages/ux-lab/design-tokens.json` | Machine-readable tokens for `/review-design` and tooling |
| `DESIGN.md` | `packages/ux-lab/DESIGN.md` | Human-readable design system for Stitch + agents |

### Passing DESIGN.md to Stitch

Stitch supports a `DESIGN.md` that defines the project's design system.
Pass a summary of the key tokens via `iterate` (keep under ~2000 chars):

```bash
./run.sh iterate --project <id> --screen <id> \
  --feedback "Apply NVIS design: bg #141414, text #e2e8f0, accent #7c3aed, \
  green #00ff88, red #ff4444, amber #ffaa00, blue #4a9eff. \
  Fonts: Space Grotesk headlines, Inter body, JetBrains Mono code."
```

The full DESIGN.md goes into the Stitch project settings via the web UI at
`https://stitch.withgoogle.com/projects/<id>` → Design Theme.

## Convergence Loop

The `converge` command is **one-shot**: it generates the initial screen and returns
the project/screen IDs + Stitch URL. The review→interview→iterate loop must be
driven by the calling agent (or orchestrator like `/orchestrate`).

**Full loop (agent-driven):**

```
1. Agent writes spec.md (use docs/spec-template.md)
2. ./run.sh converge --spec spec.md → projectId, screenId, stitchUrl
3. Human reviews at stitchUrl
4. Agent: /interview → collect structured feedback
5. ./run.sh iterate --project <id> --screen <id> --feedback "<feedback>"
6. Human reviews again → repeat 4-5 until approved
7. ./run.sh explore --views views.json → generate all views
8. ./run.sh pull → download approved HTML + screenshots
```

Human reviews in Stitch browser (live URL). Decisions collected via `/interview`.
The agent never generates HTML mockups directly — Stitch does all design work.

## Pipeline Position

```
spec.md + DESIGN.md → /mockup-lab (Stitch) → approved mockup + views
                                                     ↓
                                           build React component
                                                     ↓
                                           /ux-lab (React + Vite)
                                                     ↓
                                           /review-design (compare to mockup)
                                                     ↓
                                           production component
```

| Phase | Tool | Output |
|-------|------|--------|
| Design system | DESIGN.md + EmbryStyle.ts | NVIS tokens for Stitch |
| Design exploration | /mockup-lab (Stitch) | HTML mockup (design target) |
| View inventory | /mockup-lab explore | Screenshots of every view |
| Implementation | /ux-lab (React + Vite) | Working component |
| Visual verification | /review-design | Audit comparing impl to mockup |

## Stitch SDK Reference

```typescript
// Generate from prompt
const screen = await project.generate(prompt);
const html = await screen.getHtml();      // download URL
const image = await screen.getImage();    // download URL

// Edit existing screen
const edited = await screen.edit("Make the sidebar wider");

// Generate variants (1-5)
const variants = await screen.variants("Try layouts", {
  variantCount: 3,
  creativeRange: "EXPLORE",  // REFINE | EXPLORE | REIMAGINE
  aspects: ["LAYOUT", "COLOR_SCHEME", "IMAGES", "TEXT_FONT", "TEXT_CONTENT"],
});

// Error handling
// Codes: AUTH_FAILED, NOT_FOUND, PERMISSION_DENIED,
//        RATE_LIMITED, NETWORK_ERROR, VALIDATION_ERROR
```

## Stitch Limitations (observed)

- **`project.generate()` is broken** (as of SDK 2026-03): expects
  `raw.outputComponents[0].design.screens[0]` but API returns `designSystem`.
  Workaround: `stitch_cli.mjs` bypasses the SDK method and calls
  `generate_screen_from_text` tool directly. Do NOT use `project.generate()`.
- **Screen visibility race**: newly created screens may not appear in
  `project.screens()` for 1-2s. The CLI retries automatically (3 attempts, 2s apart).
- `screen.edit()` generates **one screen per call** — batching multiple views in
  one prompt produces only 1 result. Use `explore` to iterate through views.
- Feedback prompts over ~3000 chars may fail silently (empty response).
  Summarize long DESIGN.md content.
- ~150 designs/day on paid tier. The `explore` command uses 1 credit per view in your `--views` file.
