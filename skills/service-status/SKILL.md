---
name: service-status
description: Check health of Embry OS service daemons via Unix sockets
internal: true
triggers:
  - "service status"
  - "daemon health"
  - "are services running"
allowed-tools:
  - Bash

provides:
  - service-status
composes: [task-monitor]
disciplines:
  - observability-operations
---

# Service Status

Check health of all 7 Embry OS daemons via their Unix sockets.

## Usage

Run `bash .pi/skills/service-status/run.sh` or use the instructions below.

## Daemons

| Daemon | Socket |
|--------|--------|
| state-daemon | /run/user/1000/embry/state.sock |
| voice-daemon | /run/user/1000/embry/voice.sock |
| sparta-daemon | /run/user/1000/embry/sparta.sock |
| memory-daemon | /run/user/1000/embry/memory.sock |
| inference-daemon | /run/user/1000/embry/inference.sock |
| datalake-daemon | /run/user/1000/embry/datalake.sock |
| discord-daemon | /run/user/1000/embry/discord.sock |

## Steps

1. For each daemon, run:
   ```bash
   curl -s --unix-socket /run/user/1000/embry/<name>.sock http://localhost/health
   ```
2. Parse the JSON response for `status` field
3. Report a summary table of all daemon statuses
4. Flag any daemons that are down or returning errors

## Common Mistakes

### WRONG: Using TCP localhost instead of Unix sockets
```bash
curl http://localhost:8601/health  # wrong! daemons use Unix sockets
```

### RIGHT: Use Unix socket paths
```bash
curl -s --unix-socket /run/user/1000/embry/memory.sock http://localhost/health
```

### WRONG: Checking only one daemon and assuming all are healthy
```bash
curl -s --unix-socket /run/user/1000/embry/state.sock http://localhost/health
# Only checked state-daemon, other 6 could be down
```

### RIGHT: Check all 7 daemons and report a summary
```bash
bash .pi/skills/service-status/run.sh  # checks all daemons
```

### WRONG: Not parsing the JSON response for status field
```bash
curl -s --unix-socket /run/user/1000/embry/memory.sock http://localhost/health
# Returns JSON but you just see if curl succeeded
```

### RIGHT: Parse status field from JSON response
```bash
status=$(curl -s --unix-socket /run/user/1000/embry/memory.sock http://localhost/health | jq -r .status)
```
