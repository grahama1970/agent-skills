---
name: ops-embry-agent
description: Manage the Embry Agent D-Bus daemon (embry-agent.service) for system-level Pi access
version: "1.0"
provides:
  - embry-agent-daemon-management
composes: []
triggers:
  - "start the agent daemon"
  - "stop the agent daemon"
  - "restart embry agent"
  - "agent daemon status"
  - "check if the agent is running"
  - "install embry agent service"
  - "view agent daemon logs"
  - "is pi-dbus running"
---

# ops-embry-agent

Manage the Embry Agent D-Bus daemon (`embry-agent.service`).

The daemon runs Pi in RPC mode behind a D-Bus session bus interface (`org.embry.Agent`),
allowing any UX surface (KDE launcher, Tauri, voice, Stream Deck) to invoke the agent
without spawning subprocesses.

## Commands

| Command | Description |
|---------|-------------|
| `status` | Show daemon status and D-Bus name registration |
| `start` | Start the daemon |
| `stop` | Stop the daemon |
| `restart` | Restart the daemon |
| `logs [N]` | Show last N lines of logs (default 50) |
| `install` | Install the systemd user service |
| `uninstall` | Remove the systemd user service |
| `ping` | Health check — calls org.embry.Agent.Ping via D-Bus |

## Examples

```bash
# Check if running
/ops-embry-agent status

# Start and verify
/ops-embry-agent start
/ops-embry-agent ping

# View recent logs
/ops-embry-agent logs 100
```
