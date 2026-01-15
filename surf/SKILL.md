---
name: surf
description: >
  Control Chrome browser via CLI - navigate, click, type, screenshot, read pages.
  Use when user says "open browser", "click on", "fill form", "take screenshot",
  "navigate to", "automate browser", or needs any browser automation task.
allowed-tools: Bash, Read
triggers:
  - open browser
  - click on
  - fill form
  - take screenshot
  - navigate to
  - automate browser
  - browser automation
  - read webpage
metadata:
  short-description: Browser automation CLI for AI agents
---

# Surf - Browser Automation

Control Chrome via CLI commands. Zero config, agent-agnostic.

**Self-contained skill** - auto-installs via `npx` from GitHub (no global npm install needed).

## Simplest Usage

```bash
# Via wrapper (recommended - auto-installs from GitHub)
.agents/skills/surf/run.sh go "https://example.com"

# Or via npx with GitHub repo explicitly
npx github:nicobailon/surf-cli go "https://example.com"

# Common commands
./run.sh go "https://example.com"    # Navigate to URL
./run.sh read                        # Get page content with element refs
./run.sh click e5                    # Click element by ref
./run.sh snap                        # Take screenshot
```

## Common Patterns

### Navigate and read a page
```bash
surf go "https://example.com"
surf read                        # Returns accessibility tree with e1, e2, e3... refs
```

### Click and type
```bash
surf click e5                    # Click element by ref from `surf read`
surf type "hello@example.com"    # Type text
surf type "search query" --submit  # Type and press Enter
surf type "text" --ref e12       # Type into specific element
```

### Screenshots
```bash
surf snap                        # Quick screenshot to /tmp
surf screenshot --output /tmp/page.png  # Save to specific path
surf screenshot --annotate       # With element labels
surf screenshot --fullpage       # Entire scrollable page
```

### Wait for page states
```bash
surf wait 2                      # Wait 2 seconds
surf wait.element ".loaded"      # Wait for element to appear
surf wait.network                # Wait for network idle
surf wait.url "/dashboard"       # Wait for URL to contain pattern
```

### Tab management
```bash
surf tab.list                    # List all tabs
surf tab.new "https://example.com"  # Open new tab
surf tab.switch 123              # Switch to tab by ID
surf tab.close 123               # Close tab
```

### JavaScript execution
```bash
surf js "return document.title"  # Execute JS and return result
surf js "document.querySelector('.btn').click()"
```

### AI queries (no API keys needed)
```bash
surf chatgpt "explain this code"           # Query using browser session
surf chatgpt "summarize" --with-page       # Include current page context
surf chatgpt "analyze" --model gpt-4o      # Specify model
```

Requires being logged into chatgpt.com in Chrome.

## Element References

`surf read` returns an accessibility tree with stable element refs:

```
[e1] button "Submit"
[e2] textbox "Email"
[e3] link "Sign up"
```

Use these refs with `surf click e1`, `surf type "text" --ref e2`, etc.

## Command Reference

| Category | Commands |
|----------|----------|
| Navigation | `go`, `back`, `forward`, `tab.reload` |
| Reading | `read`, `page.text`, `page.state` |
| Interaction | `click`, `type`, `key`, `scroll.*` |
| Screenshots | `screenshot`, `snap` |
| Tabs | `tab.list`, `tab.new`, `tab.switch`, `tab.close`, `tab.name` |
| Waiting | `wait`, `wait.element`, `wait.network`, `wait.url` |
| Other | `js`, `search`, `cookie.*`, `console`, `network` |

## Global Options

```bash
--tab-id <id>      # Target specific tab
--json             # Output raw JSON
--soft-fail        # Warn instead of error on restricted pages
--no-screenshot    # Skip auto-screenshot after actions
--full             # Full resolution screenshots
```

## Prerequisites

1. Install: `npm install -g surf-cli`
2. Load extension in Chrome (chrome://extensions > Load unpacked)
3. Install native host: `surf install <extension-id>`
4. Restart Chrome

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Socket not found | Run `node native/host.cjs` or ensure Chrome has extension |
| No response | Check extension loaded at chrome://extensions |
| "Cannot control this page" | Page is restricted - use `--soft-fail` |
| Slow first operation | Normal - debugger attachment takes ~100-500ms |
