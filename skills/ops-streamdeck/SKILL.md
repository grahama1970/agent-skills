---
name: ops-streamdeck
description: >
  Stream Deck control skill for agents. Provides ability to restart streamdeck
  daemons, execute button tasks, query status, and manage Stream Deck
  hardware through a persistent daemon interface. Works with the streamdeck
  Python package for CLI operations and agent-driven automation.
allowed-tools: Bash, Read
triggers:
  - restart streamdeck
  - streamdeck button
  - execute streamdeck task
  - streamdeck status
  - streamdeck daemon
  - start streamdeck
  - stop streamdeck
  - streamdeck health check
  - fix streamdeck buttons
  - streamdeck broken
metadata:
  short-description: Stream Deck daemon control and automation

provides:
  - ops-streamdeck
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - developer-tooling
  - observability-operations
---

# Stream Deck Skill

Agent-accessible interface for Stream Deck control. Provides persistent daemon
management, button task execution, and status querying capabilities.

## Architecture

The streamdeck project has two components:

1. **CLI Tool** (`streamdeck` command) - Manual operations by users
2. **Daemon** (this skill) - Persistent service for agent automation

```
┌─────────────────────────────────────────────────────────────────────┐
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
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start the Daemon

```bash
# Start the streamdeck daemon in the background
./run.sh daemon start

# Or start in foreground for debugging
./run.sh daemon start --foreground
```

### 2. Use Agent Commands

```bash
# Restart the daemon
./run.sh restart

# Execute a button task
./run.sh button <button_id> [args...]

# Query daemon status
./run.sh status

# List available buttons
./run.sh list-buttons

# Get daemon logs
./run.sh logs
```

## Commands

### Daemon Management

| Command                     | Description                                |
| --------------------------- | ------------------------------------------ |
| `daemon start`              | Start the streamdeck daemon (background)   |
| `daemon start --foreground` | Start daemon in foreground (for debugging) |
| `daemon stop`               | Stop the streamdeck daemon                 |
| `daemon restart`            | Restart the streamdeck daemon              |
| `daemon status`             | Check if daemon is running                 |
| `daemon logs`               | View daemon logs                           |

### Button Operations

| Command              | Description                     |
| -------------------- | ------------------------------- |
| `button <id>`        | Execute button press event      |
| `button <id> --hold` | Execute button long-press event |
| `list-buttons`       | List all available button IDs   |
| `button-info <id>`   | Get information about a button  |

### Status Queries

| Command            | Description               |
| ------------------ | ------------------------- |
| `status`           | Get overall daemon status |
| `status --json`    | Get status in JSON format |
| `status --buttons` | Get button states         |

### Safety Audits

| Command                | Description                                                                 |
| ---------------------- | --------------------------------------------------------------------------- |
| `audit-display-safety` | Non-mutating audit for meeting/display button routes and KDE scale hazards  |
| `audit-date-widget`    | Non-mutating audit for home date/day widget placement and renderer binding  |
| `dynamic-stage-check`  | Non-mutating compile/stage check for voice/chat dynamic page requests       |
| `dynamic-deploy-check` | Live deploy check for semantic dynamic page requests with config readback   |

### Dynamic Pages

| Command               | Description                                                                 |
| --------------------- | --------------------------------------------------------------------------- |
| `dynamic-stage-check` | Compiles a semantic `streamdeck.dynamic_page_request.v1` request through the live streamdeck CLI and verifies staged artifacts without hardware effects |
| `dynamic-deploy-check` | Compiles and deploys a semantic `streamdeck.dynamic_page_request.v1` request to the dynamic page slot, then verifies persisted Stream Deck config readback |

### Configuration

| Command                      | Description                |
| ---------------------------- | -------------------------- |
| `config`                     | Show current configuration |
| `config --set <key> <value>` | Set configuration value    |
| `config --get <key>`         | Get configuration value    |

### Prompts Management

| Command                                  | Description                                                    |
| ---------------------------------------- | -------------------------------------------------------------- |
| `prompts list`                           | List available prompts                                         |
| `prompts copy <name>`                    | Copy prompt content to clipboard                               |
| `prompts set-button <name> <btn>`        | Configure a button for a prompt                                |
| `prompts set-button ... --switch-page N` | Configure button to switch page after press (1=Home, 2=Page 1) |

### Health Check & Auto-Fix

| Command        | Description                                    |
| -------------- | ---------------------------------------------- |
| `health-check` | Verify all services running and icons correct  |
| `fix`          | Auto-repair broken button configurations       |

```bash
# Check if buttons are configured correctly
./run.sh health-check

# Auto-fix broken buttons (stops service, edits config, restarts)
./run.sh fix
```

## CRITICAL: Config File Behavior

The Stream Deck UI (`streamdeck.service`) saves its in-memory state to `~/.streamdeck_ui.json` every ~30 seconds.

**NEVER edit the config while the service is running!** Your changes will be overwritten.

### Correct Procedure for Config Changes

```bash
# 1. STOP the service first
systemctl --user stop streamdeck.service

# 2. Edit the config file
vim ~/.streamdeck_ui.json

# 3. START the service (loads your changes into memory)
systemctl --user start streamdeck.service
```

### Why Socket Updates Are Temporary

The `icon_updater.py` sends updates via Unix socket to change button icons in real-time.
These updates modify the **in-memory state** only. When the service saves its state
(every ~30 seconds), it writes the in-memory values back to the config file.

This means:
- Socket updates appear immediately on the Stream Deck
- But if the config file had different values, those get overwritten
- The next time the service restarts, it loads from the config file

**Use `./run.sh fix` to safely update button configurations.**

## Workstation Display Safety

Display topology and KDE Global Scale are global workstation state, not normal
button state. A Stream Deck meeting button must not route through commands that
can change monitor topology, mirror outputs, or write KDE scale settings unless
the human has explicitly authorized a recovery operation.

For meeting/display button work:

- Treat `xrandr --output`, `kscreen-doctor output.*`, `nvidia-settings --assign`,
  `nvidia-settings --load-config-only`, `kwriteconfig`, `kdeglobals`,
  `ScreenScaleFactors`, `forceFontDPI`, and KDE Global Scale writes as hazardous.
- Do not treat a blank command as a working disabled state. If a disabled button
  must become usable, wire it to a non-mutating script first and prove the command
  survived the Stream Deck daemon save interval.
- Do not run a physical button or command path as proof until a static
  `audit-display-safety` readback has passed.
- If display recovery is needed, use the separate workstation rollback plan and
  do not fold recovery commands into Stream Deck meeting automation.

## Dynamic Page Safety

Voice commands and SPARTA Explorer chat must enter the Stream Deck through the
semantic request boundary, not by emitting raw button commands. The safe request
shape is `streamdeck.dynamic_page_request.v1`; it names source, request id,
intent text, context refs, confidence, lifetime, and optional catalog recipe id.

The compiler selects a catalog recipe and emits a staged
`streamdeck.dynamic_page_manifest.v1` artifact. Button commands in that artifact
must be dispatcher bindings such as:

```text
streamdeck-cli action invoke --binding <binding-id>
```

The request boundary rejects raw executable fields such as `buttons`, `command`,
`keys`, or `write`, and rejects workstation primitives such as `xrandr`,
`kscreen`, `nvidia-settings`, KDE scale terms, process kill commands, and shell
composition tokens.

Use this non-mutating proof command after dynamic-page or voice/SPARTA page
changes:

```bash
./run.sh dynamic-stage-check
```

It calls `/home/graham/workspace/streamdeck/.venv/bin/streamdeck-cli page
stage-request`, writes artifacts under `/tmp/ops-streamdeck-dynamic-stage-check`
unless `STREAMDECK_DYNAMIC_STAGE_OUTPUT` is set, and requires
`external_effects=false`, `recipe_id=sparta_review_controls`, two dispatcher
bindings, and an inspectable staged manifest. This does not prove physical
button rendering, action-dispatch semantics, or deployment to hardware.

Use this live proof command when the requested behavior is deployment to the
Stream Deck dynamic page slot:

```bash
./run.sh dynamic-deploy-check
```

It calls `/home/graham/workspace/streamdeck/.venv/bin/streamdeck-cli page
deploy-request`, writes stage/deploy receipts under
`/tmp/ops-streamdeck-dynamic-deploy-check` unless
`STREAMDECK_DYNAMIC_DEPLOY_OUTPUT` is set, and requires persisted
`~/.streamdeck_ui.json` readback showing dispatcher bindings at buttons 0/1,
empty unused buttons 2-30, and a clean back button at 31. It does not prove that
pressing those buttons executes the target action dispatcher correctly.

## Configuration

The daemon reads configuration from:

1. **Environment Variables:**
   - `STREAMDECK_DAEMON_PORT` - Port for daemon API (default: 48970)
   - `STREAMDECK_DAEMON_HOST` - Host for daemon API (default: 127.0.0.1)
   - `STREAMDECK_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)

2. **Config File:** `~/.streamdeck/daemon.json`

### Example Config

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
    },
    "2": {
      "name": "Lights Toggle",
      "command": "streamdeck lights toggle"
    },
    "3": {
      "name": "Time Tracker Toggle",
      "command": "streamdeck time-tracker toggle"
    }
  }
}
```

## Integration with Stream Deck CLI

The daemon works alongside the existing streamdeck CLI:

- **CLI** - Used for manual operations by humans
- **Daemon** - Used for automated operations by agents
- Both\*\* share the same configuration and codebase

This dual approach ensures:

- ✅ Human users can continue using familiar CLI commands
- ✅ Agents have reliable daemon for automation
- ✅ No breaking changes to existing functionality
- ✅ Consistent behavior across both interfaces

## API Endpoints

The daemon exposes a simple HTTP API:

| Endpoint                  | Method | Description               |
| ------------------------- | ------ | ------------------------- |
| `GET /status`             | GET    | Get daemon status         |
| `GET /buttons`            | GET    | List all buttons          |
| `GET /buttons/{id}`       | GET    | Get button info           |
| `POST /buttons/{id}`      | POST   | Execute button press      |
| `POST /buttons/{id}/hold` | POST   | Execute button long-press |
| `POST /restart`           | POST   | Restart daemon            |
| `POST /stop`              | POST   | Stop daemon               |

### Example API Usage

```bash
# Get status
curl http://127.0.0.1:48970/status

# Execute button
curl -X POST http://127.0.0.1:48970/buttons/0

# Get button info
curl http://127.0.0.1:48970/buttons/0
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

### Button Not Executing

```bash
# Check button configuration
./run.sh button-info <id>

# Verify daemon is running
./run.sh status

# Check logs for errors
./run.sh logs
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

### Agentic Evaluation

`ops-streamdeck` composes with `agentic-evals` and carries a committed
multi-trial fixture at `fixtures/agentic_eval.json`.

Use this fixture after changing the skill contract, `run.sh`, service-control
logic, button execution behavior, health checks, Stream Deck config safety
rules, or any meeting/display button path:

```bash
../agentic-evals/run.sh run fixtures/agentic_eval.json
```

The eval exercises a live local status path, a fail-closed malformed button
request, nested button-state readback, `audit-states`, `audit-display-safety`,
`dynamic-stage-check`, `dynamic-deploy-check`, and `audit-date-widget`. The
display audit non-mutatingly checks live config/templates/scripts for hazardous
display and KDE scale routes. The dynamic stage check non-mutatingly compiles a
semantic voice/SPARTA request to staged artifacts. The dynamic deploy check
pushes the compiled page to the live dynamic page slot and verifies persisted
config readback. It does not prove physical button rendering, USB hardware
availability, light behavior, daemon API correctness, actual meeting button
execution, action-dispatch semantics, or voice/STT/SPARTA transport integration.

### Adding New Features

To add new button commands:

1. Add button configuration to `~/.streamdeck/daemon.json`
2. Implement command handler in daemon code
3. Test with: `./run.sh button <id>`

## Data Storage

- **Config:** `~/.streamdeck/daemon.json` - Button configurations and daemon settings
- **Logs:** `~/.streamdeck/daemon.log` - Daemon activity logs
- **State:** `~/.streamdeck/daemon.state` - Current button states (runtime only)

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
