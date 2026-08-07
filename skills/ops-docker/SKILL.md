---
name: ops-docker
description: >
  Safe Docker cleanup and compose stack management.
  Prune unused containers/images/volumes, redeploy stacks.
triggers:
  - clean up docker
  - prune docker
  - docker cleanup
  - redeploy stack
  - restart containers
  - docker compose redeploy
  - free docker disk space
allowed-tools: Bash
metadata:
  short-description: Safe Docker cleanup and stack management

provides:
  - ops-docker
composes: [task-monitor]
disciplines:
  - observability-operations
---

# Docker Ops

Safe Docker management with dry-run defaults.

## Commands

```bash
# Prune unused resources (dry-run by default)
./scripts/prune.sh

# Actually prune
./scripts/prune.sh --execute

# Prune images older than 24h
./scripts/prune.sh --until 24h --execute

# Redeploy compose stack (dry-run)
./scripts/redeploy.sh --stack docker-compose.yml

# Actually redeploy
./scripts/redeploy.sh --stack docker-compose.yml --execute

# Redeploy specific service
./scripts/redeploy.sh --stack docker-compose.yml --service web --execute
```

## Environment Variables

| Variable             | Default            | Description                   |
| -------------------- | ------------------ | ----------------------------- |
| `DOCKER_PRUNE_UNTIL` | -                  | Default age filter for prune  |
| `STACK_FILE`         | docker-compose.yml | Default compose file          |
| `HEALTH_CMD`         | -                  | Command to run after redeploy |

## Common Mistakes

### WRONG: Running prune without --execute (or running --execute without checking first)
```bash
./scripts/prune.sh --execute  # prunes without previewing what will be removed
```

### RIGHT: Dry-run first, then execute
```bash
./scripts/prune.sh            # preview (dry-run default)
./scripts/prune.sh --execute  # actually prune after reviewing
```

### WRONG: Redeploying without specifying the stack file
```bash
./scripts/redeploy.sh --execute  # uses default docker-compose.yml, may be wrong stack
```

### RIGHT: Always specify the stack file explicitly
```bash
./scripts/redeploy.sh --stack /path/to/docker-compose.yml --execute
```

### WRONG: Pruning without age filter (removes recently-used images)
```bash
./scripts/prune.sh --execute  # removes all unused, including recent pulls
```

### RIGHT: Use --until to protect recent images
```bash
./scripts/prune.sh --until 24h --execute  # only prune images older than 24h
```
