# Pi Agent Extensions

Extensions for [Pi Agent](https://github.com/mariozechner/pi-mono) that provide enhanced capabilities for coding agents.

**Compatible with:** pi-mono v0.25.x

## Components

### Hooks

| Hook | Description |
|------|-------------|
| `communicator.ts` | Real-time inter-agent messaging via WebSocket (push) + HTTP (pull) |
| `rewind.ts` | Git-based file restoration with automatic checkpoints |

### Tools

| Tool | Description |
|------|-------------|
| `emit/` | Custom tool for sending messages between agents |

### Services

| Service | Description |
|---------|-------------|
| `switchboard.ts` | HTTP + WebSocket daemon for message routing |
| `switchboard.sh` | Management script (start/stop/restart/status) |

## Quick Install

```bash
# Run the install script
./extensions/pi/install.sh

# Install switchboard dependencies
cd ~/.pi/agent/services/switchboard && npm install

# Start the Switchboard
~/.pi/agent/services/switchboard/switchboard.sh start
```

## Architecture: True Push/Pull Communication

```
┌─────────────────┐                    ┌─────────────────┐
│   Agent A       │                    │   Switchboard   │
│  (pi-mono)      │                    │    (daemon)     │
│                 │   WebSocket        │                 │
│  ┌───────────┐  │◄──────────────────►│  HTTP + WS      │
│  │Communicator│ │   (PUSH)           │  Server         │
│  │   Hook    │  │                    │                 │
│  └───────────┘  │                    └────────┬────────┘
│                 │                             │
│  ┌───────────┐  │   HTTP POST                 │ WebSocket
│  │emit_message│─┼────────────────────────────►│ (PUSH)
│  │   Tool    │  │   (PULL)                    │
│  └───────────┘  │                             ▼
└─────────────────┘                    ┌─────────────────┐
                                       │    Agent B      │
                                       │   (pi-mono)     │
                                       │                 │
                                       │  Messages       │
                                       │  delivered      │
                                       │  INSTANTLY      │
                                       └─────────────────┘
```

**Key Improvement:** Unlike file-based polling, messages are pushed to connected agents **immediately** via WebSocket.

## Inter-Agent Communication Flow

### Example: Two Project Agents Collaborating

```
Project Agent A (pi-mono)              Project Agent B (memory)
        │                                      │
        │  "Fix the auth bug please"           │
        ├─────────────────────────────────────►│
        │      (emit_message tool)             │
        │                                      │
        │                              [Agent B receives via WebSocket]
        │                              [Agent B fixes the bug]
        │                                      │
        │  "Fixed! I updated login.ts:42"      │
        │◄─────────────────────────────────────┤
        │      (pushed via WebSocket)          │
        │                                      │
[Agent A sees response immediately]            │
        │                                      │
        │  "Thanks! Verified it works."        │
        ├─────────────────────────────────────►│
        │                                      │
```

## Features

### Switchboard Service

- **HTTP API** for sending messages (pull)
- **WebSocket API** for receiving messages (push)
- **Message persistence** to disk
- **Priority-based sorting** (urgent first)
- **Agent registration** and connection tracking
- **Heartbeat** for dead connection detection

### Communicator Hook

- **Auto-connects** to Switchboard on session start
- **WebSocket push** for instant message delivery
- **Auto-reconnection** with exponential backoff
- **HTTP fallback** if WebSocket unavailable
- **Message queuing** for messages received while busy

### Message Types & Priorities

| Type | Use Case |
|------|----------|
| `task` | Actionable work request |
| `question` | Needs response |
| `response` | Answer to question |
| `info` | FYI notification |
| `alert` | Important notification |

| Priority | Behavior |
|----------|----------|
| `urgent` | Pushed immediately, sorted first |
| `high` | Pushed immediately |
| `normal` | Standard delivery |
| `low` | Auto-acknowledged if type=info |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SWITCHBOARD_URL` | `http://127.0.0.1:7890` | HTTP endpoint |
| `SWITCHBOARD_WS` | `ws://127.0.0.1:7890` | WebSocket endpoint |
| `SWITCHBOARD_PORT` | `7890` | Port for Switchboard |
| `PI_AGENT_NAME` | `<project-dir>` | Agent identifier |
| `PI_REWIND_SILENT` | `false` | Suppress rewind notifications |

### Auto-Start Switchboard on Login

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# Start Switchboard if not running
if ! pgrep -f "pi-switchboard" > /dev/null; then
    ~/.pi/agent/services/switchboard/switchboard.sh start &>/dev/null
fi
```

## API Reference

### HTTP Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check (includes connected count) |
| `POST` | `/emit` | Send a message |
| `POST` | `/register` | Register an agent |
| `GET` | `/agents` | List connected agents |
| `GET` | `/inbox/:agent` | Get messages for agent |
| `DELETE` | `/inbox/:agent/:id` | Acknowledge message |
| `DELETE` | `/inbox/:agent` | Clear inbox |

### WebSocket Protocol

**Connect:** `ws://127.0.0.1:7890?agent=<name>`

**Receive Events:**
```json
{"type": "connected", "agent": "name", "pendingMessages": 0}
{"type": "message", "data": {...message...}}
{"type": "ack", "id": "msg_xxx"}  // Another agent acked your message
{"type": "emitted", "id": "msg_xxx"}  // Your message was sent
```

**Send Events:**
```json
{"type": "emit", "to": "agent", "message": "text", "priority": "high"}
{"type": "ack", "id": "msg_xxx"}
{"type": "ping"}
```

## Usage Examples

### Send a Task (in Pi agent)

```
emit_message(action="emit", to="memory", message="Please recall solutions for login bugs", type="question", priority="high")
```

### Check Connected Agents

```
emit_message(action="list")
```

### Send via curl

```bash
curl -X POST http://127.0.0.1:7890/emit \
  -H "Content-Type: application/json" \
  -d '{
    "from": "project-a",
    "to": "project-b",
    "type": "task",
    "priority": "high",
    "message": "Please review my changes"
  }'
```

## Rewind Hook

Git-based file restoration with automatic checkpoints.

- Creates checkpoint at each `turn_start`
- Saves as git refs under `refs/pi-checkpoints/<session>/`
- Offers restore options on `/branch` command
- Max 100 checkpoints per session

## Troubleshooting

### Switchboard Not Starting

```bash
# Check if port is in use
lsof -i :7890

# Check logs
~/.pi/agent/services/switchboard/switchboard.sh logs

# Verify dependencies
cd ~/.pi/agent/services/switchboard && npm install
```

### Messages Not Delivered

```bash
# Check agent connections
curl http://127.0.0.1:7890/agents

# Verify WebSocket
curl http://127.0.0.1:7890/health
# Look for "connectedAgents" > 0
```

### Hook Not Loading

Ensure hooks are in the correct location:
```bash
ls ~/.pi/agent/hooks/
# Should show: communicator.ts, rewind.ts, etc.
```

## License

MIT
