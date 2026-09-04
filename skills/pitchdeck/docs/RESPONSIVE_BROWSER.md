# Responsive browser reading

## Design classification

- Surface: existing React presentation, not a new authoring or publication workflow.
- User job: read/record a deck beside VS Code without shrinking text to fit a widescreen slide.
- Primary object/action: the current slide, its argument, and previous/next navigation.
- Secondary material: editing, source, chat and notes; tools must not consume the entire narrow reading pane.
- Source of truth: the emitted deck payload; no rewriting, summarizing, dropping qualifiers or browser-side geometry persistence.
- Applicable skills: best-practices-design, best-practices-react, pitchdeck, surf, agentic-evals.

## Behavior

Present mode and the presenter's current slide reflow when their **available pane** is below 1100 CSS pixels. Desktop reading remains a scaled 1920×1080 canvas. This is automatic; there is no aspect-ratio setting to manage.

- Semantic layouts wrap columns/cards and native flows, with normal document height and vertical scrolling.
- Canonical freeform elements flow in payload order, with readable text, contained images and retained qualifier elements. No absolute frame is written back.
- Canonical DIAGRAM elements now reach the browser. Narrow diagrams show nodes and explicit directed/labeled relationships; node order is not substituted for graph edges. This is a semantic reading projection, not a claim of graphical scene parity with PowerPoint.
- Complex Mermaid/math visuals retain internal geometry with local scrolling when needed, rather than shrinking labels indefinitely.
- Header controls wrap. Chat/notes and source tools overlay on narrow windows; a collapsed chat drawer is inert to keyboard focus.
- Slide navigation, overview selection and reduced-motion rules remain active. A new slide resets the reading scroll position. Focus a narrow slide to scroll with vertical arrow/Page/Home/End/Space keys; Left/Right navigate slides.

**Design/Source editing and thumbnails intentionally remain fixed-coordinate previews.** Reflow is a reading projection, not a second mutable layout. PPTX/PDF sizing, claim rules, publication gates and source documents are unchanged. Other canonical primitive projection limitations (icons, groups, rich text, figures, shapes) are not addressed here.

## Acceptance gate

Must prove: real Chrome content at desktop, 960px and phone widths; complete emitted text/qualifier and diagram-label retention; loaded images; no page/slide horizontal overflow; readable narrow type; button/keyboard/overview navigation; and fixed Design coordinates with unchanged payload bytes. Reject if a whole-slide scale masquerades as responsive reading.

Run Vite, then the retained live gate:

```bash
cd skills/pitchdeck/ui && pnpm dev --host 127.0.0.1 --port 3006
# another terminal, repo root:
skills/agentic-evals/run.sh run skills/pitchdeck/fixtures/responsive_browser.json \
  --output /tmp/pitchdeck-responsive-agentic-evals.json
```

The gate uses Surf's existing Chrome session, a dedicated disposable unfocused window with a visible selected tab (to avoid background animation/timer throttling), the workstation's approved canonical document at `/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json`, and the current SPARTA semantic bundle at `examples/sparta-explorer`, and the default live `ui/public/deck.data.json` deck. It re-emits the canonical payload through `emit-document-ui` and the semantic payload through `emit-ui`; these are real operational prerequisites, not mocked inputs. Missing prerequisites fail instead of returning a simulated PASS. The script accepts `--url`, `--document`, and `--out` overrides. It never calls an edit API.

Receipts record source hashes, actual viewports, complete expected/rendered strings, font floors, navigation checks and Surf screenshots. The adversarial case injects a whole-slide scale into its own tab and requires the same live oracle to reject it. These checks do not certify arbitrary deck layouts, graphical equivalence with exported slides, visual approval, or an actual VS Code recording session.
