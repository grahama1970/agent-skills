# Surf

The CLI for AI agents to control Chrome. Zero config, agent-agnostic, battle-tested.

```bash
surf go "https://example.com"
surf read
surf click e5
surf snap
```

## Why Surf

Browser automation for AI agents is harder than it looks. Most tools require complex setup, tie you to specific AI providers, or break on real-world pages.

Surf takes a different approach:

**Agent-Agnostic** - Pure CLI commands over Unix socket. Works with Claude Code, GPT, Gemini, Cursor, custom agents, shell scripts - anything that can run commands.

**Zero Config** - Install the extension, run commands. No MCP servers to configure, no relay processes, no subscriptions.

**Battle-Tested** - Built by reverse-engineering production browser extensions and methodically working through agent-hostile pages like Discord settings. Falls back gracefully when CDP fails.

**Smart Defaults** - Screenshots auto-resize to 1200px (saves tokens). Actions auto-capture screenshots (saves round-trips). Errors on restricted pages warn instead of fail.

**AI Without API Keys** - Query ChatGPT, Gemini, and Perplexity using your browser's logged-in session. No API keys, no rate limits, no cost.

**Network Capture** - Automatically logs all network requests while active. Filter, search, and replay API calls without manually setting up request interception.

## Comparison

| Feature | Surf | Manus | Claude Extension | DevTools MCP | dev-browser |
|---------|------|-------|------------------|--------------|-------------|
| Agent-agnostic | Yes | No (Manus only) | No (Claude only) | Partial | No (Claude skill) |
| Zero config | Yes | No (subscription) | No (subscription) | No (MCP setup) | No (relay server) |
| Local-only | Yes | No (cloud) | Partial | Yes | Partial |
| CLI interface | Yes | No | No | No | No |
| Free | Yes | No | No | Yes | Yes |
| AI via browser cookies | Yes | No | No | No | No |

## Installation

### Quick Start

```bash
# 1. Install globally
npm install -g surf-cli

# 2. Load extension in Chrome
#    - Open chrome://extensions
#    - Enable "Developer mode"
#    - Click "Load unpacked"
#    - Paste the path from: surf extension-path

# 3. Install native host (copy extension ID from chrome://extensions)
surf install <extension-id>

# 4. Restart Chrome and test
surf tab.list
```

### Multi-Browser Support

```bash
surf install <extension-id>                    # Chrome (default)
surf install <extension-id> --browser brave    # Brave
surf install <extension-id> --browser all      # All supported browsers
```

Supported: `chrome`, `chromium`, `brave`, `edge`, `arc`

### Uninstall

```bash
surf uninstall                  # Chrome only
surf uninstall --all            # All browsers + wrapper files
```

### Development Setup

```bash
git clone https://github.com/nicobailon/surf-cli.git
cd surf-cli
npm install
npm run build
# Then load dist/ as unpacked extension
```

## Usage

```bash
surf <command> [args] [options]
surf --help                    # Basic help
surf --help-full               # All 50+ commands
surf <command> --help          # Command details
surf --find <query>            # Search commands
```

### Navigation

```bash
surf go "https://example.com"
surf back
surf forward
surf tab.reload --hard
```

### Reading Pages

```bash
surf read                           # Accessibility tree + visible text content
surf read --no-text                 # Accessibility tree only (no text)
surf read --depth 3                 # Limit tree depth (smaller output)
surf read --compact                 # Remove empty structural elements
surf read --depth 3 --compact       # Both (60% smaller output)
surf page.text                      # Raw text content only
surf page.state                     # Modals, loading state, scroll position
```

Element refs (`e1`, `e2`, `e3`...) are stable identifiers from the accessibility tree - semantic, predictable, and resilient to DOM changes.

### Semantic Locators

Find and interact with elements by role, text, or label - no refs or selectors needed:

```bash
# By ARIA role
surf locate.role button --name "Submit"           # Find button
surf locate.role button --name "Submit" --action click  # Find and click
surf locate.role textbox --action fill --value "hello"  # Find and fill
surf locate.role link --all                       # List all links

# By text content  
surf locate.text "Sign In" --action click         # Click element with text
surf locate.text "Accept" --exact                 # Exact match only

# By form label
surf locate.label "Email" --action fill --value "test@example.com"
```

### Iframe Support

Work with content inside iframes:

```bash
surf frame.list                     # List all frames
surf frame.switch --index 0         # Switch to first iframe
surf frame.switch --name "payment"  # Switch by frame name
surf frame.switch --selector "#checkout-frame"  # Switch by CSS selector

# Now all commands target the iframe
surf read                           # Read iframe content
surf click e5                       # Click in iframe
surf locate.role button --action click

surf frame.main                     # Return to main page
```

### Interaction

```bash
surf click e5                       # Click by element ref
surf click --selector ".btn"        # Click by CSS selector
surf click 100 200                  # Click by coordinates
surf type "hello" --submit          # Type and press Enter
surf type "email@example.com" --ref e12  # Type into specific element
surf key Escape                     # Press key
surf scroll.bottom                  # Scroll to bottom
```

### Forms

Select options in dropdown menus:

```bash
surf select e5 "US"                         # Select by value
surf select "#country" "US"                 # Select by CSS selector
surf select e5 "opt1" "opt2"                # Multi-select
surf select e5 --by label "United States"   # Select by visible text
surf select e5 --by index 0                 # Select first option
```

### Element Inspection

Get computed styles from elements:

```bash
surf element.styles e5              # Get styles by ref
surf element.styles ".header"       # Get styles by CSS selector (can return multiple)
```

Returns font, color, background, border, padding, and bounding box for design debugging.

### Screenshots

Screenshots auto-save to `/tmp` by default (optimized for AI agents):

```bash
surf screenshot                             # Auto-saves to /tmp/surf-snap-*.png
surf screenshot --output /tmp/shot.png      # Save to specific path
surf screenshot --full --output /tmp/hd.png # Full resolution (skip resize)
surf screenshot --annotate                  # With element labels
surf screenshot --fullpage                  # Entire page
surf screenshot --no-save                   # Return base64 + ID only (no file)
surf snap                                   # Alias for screenshot
```

To disable auto-save globally, set `autoSaveScreenshots: false` in `surf.json`.

Actions like `click`, `type`, and `scroll` automatically capture a screenshot after execution - no extra command needed.

### Tabs

```bash
surf tab.list
surf tab.new "https://example.com"
surf tab.switch 123
surf tab.close 123
surf tab.name "dashboard"           # Name current tab
surf tab.switch "dashboard"         # Switch by name
surf tab.group --name "Work" --color blue
```

### Window Isolation

Keep using your browser while the agent works in a separate window:

```bash
# Create isolated window for agent
surf window.new "https://example.com"
# Returns: Window 123456 (tab 789)

# All subsequent commands target that window
surf click e5 --window-id 123456
surf read --window-id 123456
surf tab.new "https://other.com" --window-id 123456

# Or manage windows directly
surf window.list                    # List all windows
surf window.list --tabs             # Include tab details
surf window.focus 123456            # Bring window to front
surf window.close 123456            # Close window
```

### Device Emulation

Test responsive designs and mobile layouts:

```bash
surf emulate.device --list                    # Show available devices
surf emulate.device "iPhone 14"               # Emulate iPhone 14
surf emulate.device "Pixel 7"                 # Emulate Pixel 7
surf emulate.device reset                     # Return to desktop

# Custom viewport
surf emulate.viewport --width 375 --height 812
surf emulate.viewport --width 1920 --height 1080 --scale 2

# Touch emulation
surf emulate.touch                            # Enable touch
surf emulate.touch --enabled false            # Disable touch
```

Available devices: iPhone 12-14 (Pro/Max), iPhone SE, iPad (Pro/Mini), Pixel 5-7 (Pro), Galaxy S21-S23, Galaxy Tab S7, Nest Hub (Max).

### Performance Tracing

Capture performance metrics and traces:

```bash
surf perf.metrics                   # Current performance metrics
surf perf.start                     # Start tracing
surf perf.stop                      # Stop and get trace data
```

### AI Queries (No API Keys)

Query AI models using your browser's logged-in session:

```bash
# ChatGPT
surf chatgpt "explain this code"
surf chatgpt "summarize" --with-page     # Include page context
surf chatgpt "analyze" --model gpt-4o    # Specify model
surf chatgpt "review" --file code.ts     # Attach file

# Gemini
surf gemini "explain quantum computing"
surf gemini "summarize" --with-page                           # Include page context
surf gemini "analyze" --file data.csv                         # Attach file
surf gemini "a robot surfing" --generate-image /tmp/robot.png # Generate image
surf gemini "add sunglasses" --edit-image photo.jpg --output out.jpg
surf gemini "summarize" --youtube "https://youtube.com/..."   # YouTube analysis
surf gemini "hello" --model gemini-2.5-flash                  # Model selection

# Perplexity
surf perplexity "what is quantum computing"
surf perplexity "explain this page" --with-page               # Include page context
surf perplexity "deep dive" --mode research                   # Research mode (Pro)
surf perplexity "latest news" --model sonar                   # Model selection (Pro)
```

Requires being logged into chatgpt.com, gemini.google.com, or perplexity.ai in Chrome.

### Waiting

```bash
surf wait 2                         # Wait 2 seconds
surf wait.element ".loaded"         # Wait for element
surf wait.network                   # Wait for network idle
surf wait.url "/dashboard"          # Wait for URL pattern
```

### Other

```bash
surf js "return document.title"     # Execute JavaScript
surf search "login"                 # Find text in page
surf cookie.list                    # List cookies
surf zoom 1.5                       # Set zoom to 150%
surf console                        # Read console messages
surf network                        # Read network requests
```

### Network Capture

Surf automatically captures all network requests while active. No explicit start needed.

```bash
# Overview (token-efficient for LLMs)
surf network                          # Recent requests, compact table
surf network --urls                   # Just URLs (minimal output)
surf network --format curl            # As curl commands

# Filtering
surf network --origin api.github.com  # Filter by origin/domain
surf network --method POST            # Only POST requests
surf network --type json              # Only JSON responses
surf network --status 4xx,5xx         # Only errors
surf network --since 5m               # Last 5 minutes
surf network --exclude-static         # Skip images/fonts/css/js

# Drill down
surf network.get r_001                # Full request/response details
surf network.body r_001               # Response body (for piping to jq)
surf network.curl r_001               # Generate curl command
surf network.origins                  # List captured domains

# Management
surf network.clear                    # Clear captured data
surf network.stats                    # Capture statistics
```

Storage location: `/tmp/surf/` (override with `--network-path` or `SURF_NETWORK_PATH` env).
Auto-cleanup: 24 hours TTL, 200MB max.

## Global Options

```bash
--tab-id <id>      # Target specific tab
--window-id <id>   # Target specific window (isolate agent from your browsing)
--json             # Output raw JSON
--soft-fail        # Warn instead of error (exit 0) on restricted pages
--no-screenshot    # Skip auto-screenshot after actions
--full             # Full resolution screenshots (skip resize)
--network-path <path>  # Custom path for network logs (default: /tmp/surf, or SURF_NETWORK_PATH env)
```

## Socket API

For programmatic integration, send JSON to `/tmp/surf.sock`:

```bash
echo '{"type":"tool_request","method":"execute_tool","params":{"tool":"tab.list","args":{}},"id":"1"}' | nc -U /tmp/surf.sock
```

## Command Groups

| Group | Commands |
|-------|----------|
| `window.*` | `new`, `list`, `focus`, `close`, `resize` |
| `tab.*` | `list`, `new`, `switch`, `close`, `name`, `unname`, `named`, `group`, `ungroup`, `groups`, `reload` |
| `scroll.*` | `top`, `bottom`, `to`, `info` |
| `page.*` | `read`, `text`, `state` |
| `locate.*` | `role`, `text`, `label` |
| `element.*` | `styles` |
| `frame.*` | `list`, `switch`, `main`, `js` |
| `wait.*` | `element`, `network`, `url`, `dom`, `load` |
| `cookie.*` | `list`, `get`, `set`, `clear` |
| `bookmark.*` | `add`, `remove`, `list` |
| `history.*` | `list`, `search` |
| `dialog.*` | `accept`, `dismiss`, `info` |
| `emulate.*` | `network`, `cpu`, `geo`, `device`, `viewport`, `touch` |
| `perf.*` | `start`, `stop`, `metrics` |
| `network.*` | `get`, `body`, `curl`, `origins`, `clear`, `stats`, `export`, `path` |

## Aliases

| Alias | Command |
|-------|---------|
| `snap` | `screenshot` |
| `read` | `page.read` |
| `find` | `search` |
| `go` | `navigate` |

## How It Works

```
CLI (surf) → Unix Socket → Native Host → Chrome Extension → CDP/Scripting API
```

Surf uses Chrome DevTools Protocol for most operations, with automatic fallback to `chrome.scripting` API when CDP is unavailable (restricted pages, certain contexts). Screenshots fall back to `captureVisibleTab` when CDP capture fails.

## Limitations

- Cannot automate `chrome://` pages or the Chrome Web Store (Chrome restriction)
- First CDP operation on a new tab takes ~100-500ms (debugger attachment)
- Some operations on restricted pages return warnings instead of results

## Linux Support (Experimental)

Surf should work on Linux with Chromium. Not yet tested in production.

```bash
# Install dependencies
sudo apt install chromium-browser nodejs npm imagemagick

# For headless server: add Xvfb + VNC
sudo apt install xvfb tigervnc-standalone-server

# Install Surf and native host
npm install -g surf-cli
surf install <extension-id> --browser chromium
```

**Notes:**
- Use Chromium (no official Chrome for Linux ARM64)
- Screenshot resize uses ImageMagick instead of macOS `sips`
- Headless servers need Xvfb + VNC for initial login setup

## Development

```bash
npm run dev       # Watch mode
npm run build     # Production build
```

After changes:
- **Extension** (`src/`): Reload at `chrome://extensions`
- **Host** (`native/`): Restart `node native/host.cjs`

## License

MIT
