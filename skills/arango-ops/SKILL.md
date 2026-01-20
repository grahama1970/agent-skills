---
name: arango-ops
description: >
  Manage ArangoDB operations including backups with automatic retention.
  Works with local or containerized ArangoDB.
triggers:
  - backup arangodb
  - dump arango
  - create database backup
  - arango dump
  - backup memory database
  - arango ops
---

# Arango Ops

Reliable ArangoDB operations. Currently focused on backups.

## Commands

```bash
# Create dump (Local 'arangodump' binary must be in PATH)
./scripts/dump.sh

# Create dump from Docker Container
CONTAINER=arangodb ./scripts/dump.sh

# Custom database and retention
ARANGO_DB=memory RETENTION_N=14 ./scripts/dump.sh
```

## Output Location

Backups saved to: `~/.local/state/devops-agent/arangodumps/<timestamp>/`

## Features

- **Explicit Mode**: Set `CONTAINER` env var to use Docker. Default is local binary.
- **Integrity Check**: Verifies `manifest.json` existence.
- **Safe Retention**: Keeps last N backups automatically (default 7).

## Environment Variables

| Variable      | Default               | Description                                 |
| ------------- | --------------------- | ------------------------------------------- |
| `ARANGO_URL`  | http://127.0.0.1:8529 | ArangoDB endpoint                           |
| `ARANGO_DB`   | \_system              | Database to dump                            |
| `ARANGO_USER` | -                     | Username (optional)                         |
| `ARANGO_PASS` | -                     | Password (optional)                         |
| `CONTAINER`   | -                     | **Required for Docker**. Name of container. |
| `RETENTION_N` | 7                     | Number of backups to keep                   |
