# Changelog

## [2.2.0] - 2025-01-19

### Added
- **Element styles inspection** - New `element.styles` command to get computed CSS styles from elements. Returns font, color, background, border, padding, and bounding box. Accepts refs or CSS selectors.
- **Dropdown select command** - New `select` command to select options in `<select>` dropdowns. Supports single/multi-select, matching by value (default), label, or index.

## [2.1.0] - 2025-01-17

### Added
- **Frame context for iframe support** - `frame.switch` now properly affects subsequent commands (`page.read`, `locate.*`, `click`, `search`, etc.). Switch to an iframe and all content script operations target that frame.
- **Semantic locators** - `locate.role`, `locate.text`, `locate.label` commands to find elements by ARIA role, text content, or label. Supports `--action click|fill|hover|text` to act on found elements.
- **Device emulation** - `emulate.device` with 19 device presets (iPhone, iPad, Pixel, Galaxy, Nest Hub). Includes `emulate.viewport`, `emulate.touch` for custom configurations.
- **Performance tracing** - `perf.start`, `perf.stop`, `perf.metrics` for capturing Chrome performance traces.
- **Page read optimization** - `--depth` and `--compact` flags for `page.read` to reduce output size for LLM efficiency.
- **Window isolation for multi-agent workflows** - New `window.*` commands (`new`, `list`, `focus`, `close`, `resize`) and `--window-id` global option. Agents can work in separate browser windows without interfering with user browsing.
- **Helpful hints in CLI output** - Commands now show actionable hints (e.g., `window.new` shows how to use `--window-id`)
- **Auto-tab creation** - When targeting a window with only restricted tabs (chrome://, extensions), Surf auto-creates a usable tab
- **Linux support (experimental)** - Added ImageMagick fallback for screenshot resizing, supports both IM6 (`convert`) and IM7 (`magick`). Install script already handles Linux native messaging paths.
- **`surf --help-topic windows`** - New help topic explaining window isolation workflow
- **Screenshot auto-save control** - New `--no-save` flag and `autoSaveScreenshots` config option to disable auto-saving screenshots to `/tmp`. When disabled, returns base64 + ID instead of file path, saving context for agents that don't need the file.
- **Extension disconnect detection** - CLI detects when extension disconnects and exits cleanly with a helpful message
- **Testing infrastructure** - Added vitest with coverage, Chrome API mocks, and network formatter tests
- **Biome linter** - Strict linting for test code with rules for test best practices (no focused/skipped tests, no console, no any, etc.)
- **Perplexity AI integration** - Query Perplexity using browser session via `surf perplexity "query"`. Supports `--with-page` for context, `--mode` for search modes, and `--model` for model selection (Pro features).
- **`surf read` now includes visible text by default** - Reduces agent round-trips by returning both accessibility tree and page text content in one call. Use `--no-text` to get only interactive elements.

### Changed
- `surf read` behavior changed: now includes `--- Page Text ---` section by default
- Added `--no-text` flag to `surf read` to exclude text content (previous default behavior)
- `tab.list` now respects `--window-id` to show only tabs in that window
- `tab.new` now respects `--window-id` to create tabs in a specific window

### Fixed
- Fixed `locate.role`, `locate.text`, `locate.label`, `emulate.device`, `frame.js` not accepting positional arguments (missing from PRIMARY_ARG_MAP)
- Fixed `emulate.device --list` requiring a tab when it shouldn't (added to COMMANDS_WITHOUT_TAB)
- Fixed `surf screenshot` without `--output` returning an unusable in-memory ID instead of saving to file. Now auto-saves to `/tmp/surf-snap-*.png` like the `snap` alias, ensuring agents always get a usable file path. The `screenshotId` is still returned for use with `upload_image` workflow.
- Fixed MCP server `screenshot` tool not accepting `output` parameter (was only accepting `savePath`)
- Fixed frame context not being used by most content script operations (now `frame.switch` properly affects `page.read`, `locate.*`, `click`, `type`, `search`, etc.)
- Fixed frame context memory leak on tab close
- Fixed frame context not clearing on page navigation
- Fixed device emulation matching preferring shorter names ("iPhone 14" over "iPhone 14 Pro" when user typed "iphone14pro")
- Fixed `--depth` not being parsed as integer for `page.read`
- Fixed device presets out of sync between CLI and extension (now 19 devices in both)
- Fixed `performLocateAction` helper not respecting frame context for `--action` operations
- Fixed internal message `id` leaking into JSON output for window commands
- Fixed `windowId` not being forwarded from CLI through native host to extension
- Fixed `tab.new` not creating tabs in the specified window when using `--window-id`
- Fixed `tab.list` not filtering by window when using `--window-id`
- Fixed `tab.list` showing no output when no tabs exist (now shows helpful message)
- Fixed `--window-id` and `--tab-id` not being parsed as integers (caused Chrome API errors with helpful validation)
- Fixed ImageMagick 7 compatibility (`magick identify` fallback for systems without standalone `identify`)
- Fixed text content not being included when screenshots were also present in page read responses

### Removed
- Removed `session.*` commands - sessions couldn't actually provide profile isolation via native messaging (use `window.new --incognito` for cookie isolation instead)
- Removed non-functional base64 image output from CLI (was not being interpreted by agents)
