# Canonical deck ZIP handoff

One authoritative `deck.document.json` travels with its resources. Intake does
not replace a working deck or change its contents. It is not publication approval.

## Producer contract

Put these files at the ZIP root, without an enclosing folder:

```text
deck.document.json       # pitchdeck.deck_document.v1
assets/                  # every assets[].local_path, with exact relative names
sources/                 # required sources[].path snapshots
NARRATIVE.md              # include root source files too, if referenced
debugger.json             # optional pitchdeck.debugger_map.v1
slide-map.json            # optional project-owned companion
README.md                # provenance and remaining limitations
theme.json               # optional reusable ThemeTokens object
fonts/                   # optional archived font resources
docs/                    # optional supporting documentation
```

- Preserve authored elements, coordinates, notes, builds, transitions, bindings,
  claim state and qualifiers in the canonical document. Intake copies bytes; it
  never recompiles a legacy manifest over the submitted document.
- Bundle every declared asset path and every required source path. Paths must be
  relative to the ZIP root, without traversal, backslashes, drive prefixes or
  environment-variable syntax.
  No external URLs are fetched or environment variables expanded.
- Include **all resolved `deck.theme_tokens` fields**. `deck.theme` names the
  preset; its name alone is not a portable snapshot. A separate `theme.json`,
  if supplied, contains the same plain token object and must agree with it.
  The canonical snapshot controls this deck; the library theme can evolve later.
- Supplied fonts/textures are retained, not installed or automatically substituted
  into the renderer. Rendering still uses pitchdeck's existing font/texture
  loading paths. A font family name is not proof of font availability.
- Debugger slide/concept IDs must exist in the document. Files remain relative to
  the separately configured code workspace. Ranges are checked structurally,
  not against that workspace's source bytes. Intake never starts a debugger.
  `slide-map.json` is preserved with JSON-syntax validation only.
- Prefer omitting `deck.authoring.json`. If supplied, its canonical SHA-256 must
  match. It is retained only as review material, **not converted or merged**;
  hash agreement does not establish agreement of its expanded contents. Edit the
  canonical input, not two competing copies.

ZIP limits: 2048 members, 64 MiB per file, 256 MiB total expanded size. Links,
case-colliding names, file/directory collisions and a supplied
`intake-receipt.json` are refused. Different image files with the same basename
are refused because the existing browser emitter flattens asset paths.

## Receiver commands

Check first; this creates no destination directory:

```bash
skills/pitchdeck/run.sh ingest-package \
  --package /path/to/handoff.zip \
  --output-dir /mnt/storage12tb/skills/pitchdeck/sources/oai-handoff-NEW
```

Use the same command with `--execute` to import. Existing destinations are
refused, including on repeated imports. A successful import writes
`intake-receipt.json` last, after independently hashing each file on disk.
Interrupted imports without that receipt are not accepted deliveries.

Then use the established browser emitter against the imported source:

```bash
skills/pitchdeck/run.sh emit-document-ui \
  --document /path/to/import/deck.document.json \
  --asset-base /path/to/import \
  --output-dir /path/to/new-preview
```

Keep the imported source bundle. The browser emitter does not automatically copy
all project-owned sidecars into its preview directory; bind or copy the matching
maps explicitly before enabling code navigation. Do not point a running deck at
new data until its preview and workspace binding have been checked.

## Retained evaluation

```bash
PITCHDECK_INTAKE_PACKAGE=/path/to/producer-handoff.zip \
  skills/agentic-evals/run.sh run skills/pitchdeck/fixtures/package_intake.json \
  --output /mnt/storage12tb/skills/pitchdeck/outputs/package-intake/evals.json
```

The live case reads imported files and the existing emitter's actual output.
Adversarial cases inject missing assets, traversal, theme disagreement, stale
mapping IDs, unknown animation targets, environment paths, duplicate JSON keys,
symlinks and asset filename collisions. These checks do not establish visual
fidelity, media sanitization, semantic claim safety, native playback or workspace
execution. No browser windows are opened.
