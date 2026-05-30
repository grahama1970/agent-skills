# Surf Native Host

Native messaging host that bridges CLI commands to the Chrome extension via Unix socket.

## Architecture

```
CLI (surf) → Unix Socket (/tmp/surf.sock) → Native Host → Chrome Extension → CDP
```

## Files

| File | Purpose |
|------|---------|
| `host.cjs` | Main native host with socket server and tool handling |
| `cli.cjs` | CLI tool for browser automation |
| `chatgpt-client.cjs` | ChatGPT browser automation client |
| `protocol.cjs` | Chrome native messaging protocol helpers |
| `host-wrapper.py` | Python wrapper for native host execution |
| `host.sh` | Shell script to start the host |

## Setup

1. Install the native host manifest:
```bash
npm run install:native <extension-id>
```

Or manually:
```bash
mkdir -p ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts
cat > ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.pi_chrome.json << EOF
{
  "name": "com.anthropic.pi_chrome",
  "description": "Surf CLI Native Host",
  "path": "$PWD/host-wrapper.py",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://YOUR_EXTENSION_ID/"]
}
EOF
```

2. Start the native host:
```bash
node host.cjs
```

The host creates a Unix socket at `/tmp/surf.sock`.

## CLI Reference

See the main [README](../README.md) for full CLI documentation.

### Quick Reference

```bash
surf go "https://example.com"       # Navigate
surf read                           # Get accessibility tree
surf click e5                       # Click element
surf type "hello" --submit          # Type and submit
surf snap                           # Screenshot to /tmp
surf chatgpt "explain this"         # Query ChatGPT
```

### Global Options

```bash
--tab-id <id>     # Target specific tab
--json            # Output raw JSON
--soft-fail       # Warn instead of error on restricted pages
--no-screenshot   # Skip auto-screenshot after actions
--full            # Full resolution screenshots
```

## Protocol

### Tool Request

```json
{
  "type": "tool_request",
  "method": "execute_tool",
  "params": {
    "tool": "TOOL_NAME",
    "args": { ... },
    "tabId": 123
  },
  "id": "unique-request-id"
}
```

### Tool Response (Success)

```json
{
  "type": "tool_response",
  "id": "unique-request-id",
  "result": {
    "content": [
      { "type": "text", "text": "Result message" }
    ]
  }
}
```

### Tool Response (With Image)

```json
{
  "type": "tool_response",
  "id": "unique-request-id",
  "result": {
    "content": [
      { "type": "text", "text": "Screenshot captured" },
      { "type": "image", "data": "base64...", "mimeType": "image/png" }
    ]
  }
}
```

### Tool Response (Error)

```json
{
  "type": "tool_response",
  "id": "unique-request-id",
  "error": {
    "content": [{ "type": "text", "text": "Error message" }]
  }
}
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Socket not found | Ensure `node host.cjs` is running |
| No response | Check extension is loaded in Chrome |
| "Content script not loaded" | Navigate to a page first |
| "Cannot control this page" | Page is restricted (chrome://, extensions) - use `--soft-fail` |
| Slow first operation | Normal - CDP debugger attachment takes ~100-500ms |
