# Stream Deck Skill

Agent-accessible interface for Stream Deck control. Provides persistent daemon
management, button task execution, and status querying capabilities.

## Overview

This skill adds a **persistent daemon component** to the streamdeck project, enabling:

- **Agent automation** - Execute button tasks programmatically
- **Restart capability** - Restart streamdeck daemon on demand
- **Status queries** - Query daemon state and button status
- **Background operation** - Daemon runs continuously, independent of CLI

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT / AUTOMATION                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Stream Deck Skill (this skill)               │     │
│  │  • Restart daemon                              │     │
│  │  • Execute button tasks                        │◄──►│
│  │  • Query status                                 │     │
│  └────────────────────────────────────────────────────────┘     │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Stream Deck Daemon (persistent service)        │     │
│  │  • Manages Stream Deck hardware               │     │
│  │  • Executes button press events                 │     │
│  │  • Provides status API                         │     │
│  └────────────────────────────────────────────────────────┘     │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Stream Deck CLI (manual operations)        │     │
│  │  • User-invoked commands                     │     │
│  │  • Video chat, lights, monitoring, etc.      │     │
│  └────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install the Skill

```bash
# The skill auto-installs via uvx from git
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/streamdeck
./run.sh --help
```

### 2. Start the Daemon

```bash
# Start in background
./run.sh daemon start

# Or start in foreground for debugging
./run.sh daemon start --foreground
```

### 3. Use Agent Commands

```bash
# Restart daemon
./run.sh restart

# Execute a button task
./run.sh button 0

# Query daemon status
./run.sh status
```

## Key Features

### Daemon Management
- **Start/Stop/Restart** - Full lifecycle control
- **Background/Foreground** - Flexible operation modes
- **Status Checking** - Verify daemon health
- **Log Viewing** - Debug and monitor activity

### Button Operations
- **Execute Press** - Trigger button press events
- **Long Press Support** - Hold events for advanced actions
- **Button Listing** - Discover available buttons
- **Button Info** - Get button configuration

### Status Queries
- **Overall Status** - Daemon health and state
- **Button States** - Current state of all buttons
- **JSON Output** - Machine-readable format for agents

### Configuration
- **File-based Config** - `~/.streamdeck/daemon.json`
- **Environment Variables** - Override defaults
- **Button Mappings** - Map button IDs to commands
- **Dynamic Updates** - Change config without restart

## Integration with Stream Deck CLI

The daemon works **alongside** the existing streamdeck CLI:

| Interface | Purpose | Example |
|-----------|---------|----------|
| CLI | Manual operations by humans | `streamdeck videochat start` |
| Daemon | Automated operations by agents | `./run.sh button 0` |

Both interfaces share:
- Same configuration files
- Same codebase
- Same button definitions

This ensures consistent behavior whether using CLI or daemon.

## Configuration

### Environment Variables

```bash
export STREAMDECK_DAEMON_PORT=48970
export STREAMDECK_DAEMON_HOST=127.0.0.1
export STREAMDECK_LOG_LEVEL=INFO
```

### Config File Structure

```json
{
  "daemon": {
    "port": 48970,
    "host": "127.0.0.1",
    "log_level": "INFO"
  },
  "buttons": {
    "0": {
      "name": "Video Chat Start",
      "command": "streamdeck videochat start"
    },
    "1": {
      "name": "Video Chat Stop",
      "command": "streamdeck videochat stop"
    }
  }
}
```

## API Endpoints

The daemon exposes a simple HTTP API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /status` | GET | Get daemon status |
| `GET /buttons` | GET | List all buttons |
| `GET /buttons/{id}` | GET | Get button info |
| `POST /buttons/{id}` | POST | Execute button press |
| `POST /buttons/{id}/hold` | POST | Execute button long-press |
| `POST /restart` | POST | Restart daemon |
| `POST /stop` | POST | Stop daemon |

### Example API Usage

```bash
# Get status
curl http://127.0.0.1:48970/status

# Execute button
curl -X POST http://127.0.0.1:48970/buttons/0

# Get button info
curl http://127.0.0.1:48970/buttons/0
```

## Usage Examples

### Agent Workflow

```python
import requests

# Start daemon
requests.post("http://127.0.0.1:48970/start")

# Execute button
requests.post("http://127.0.0.1:48970/buttons/0")

# Check status
response = requests.get("http://127.0.0.1:48970/status")
print(response.json())
```

### Shell Workflow

```bash
# Start daemon
./run.sh daemon start

# Execute button
./run.sh button 0

# Get status
./run.sh status

# Restart
./run.sh restart
```

## Troubleshooting

### Daemon Won't Start

```bash
# Check if port is already in use
lsof -i :48970

# Check logs for errors
./run.sh logs

# Try starting in foreground to see errors
./run.sh daemon start --foreground
```

### Permission Issues

The daemon requires access to:
- Stream Deck hardware (USB device access)
- Configuration directory (`~/.streamdeck/`)
- Network port (48970) for API

On Linux, ensure user has proper permissions:
```bash
# Add user to dialout group (for serial port access)
sudo usermod -a -G dialout $USER

# Ensure ~/.streamdeck is writable
chmod 755 ~/.streamdeck
```

## Development

### Running Tests

```bash
# Run daemon tests
./sanity.sh

# Run with verbose output
./sanity.sh --verbose
```

### Adding New Features

To add new button commands:

1. Add button configuration to `~/.streamdeck/daemon.json`
2. Implement command handler in daemon code
3. Test with: `./run.sh button <id>`

## Dependencies

- Python 3.8+
- Stream Deck Python SDK (`streamdeck`)
- FastAPI (for daemon API)
- Uvicorn (for daemon server)
- Pydantic (for API models)

Install dependencies:
```bash
# Via uvx (recommended)
uvx --from "git+https://github.com/grahama1970/streamdeck.git" streamdeck-daemon

# Or manually
pip install streamdeck fastapi uvicorn pydantic
```

## License

MIT License - See LICENSE file for details.

## Related Skills

- **time-tracker** - Time tracking with Toggl integration
- **icon-library** - Icon pack management
- **code-review** - Code review and patch generation
- **memory** - Memory-first problem solving

These skills can work together to provide comprehensive Stream Deck automation.
