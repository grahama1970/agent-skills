# Skills Conventions

Guidelines for creating and maintaining shared skills across agents.

## Directory Structure

Each skill follows this pattern:

```
skill-name/
├── SKILL.md           # Documentation (required)
├── pyproject.toml     # Dependencies (if Python)
├── main_script.py     # Main entry point
├── sanity.sh          # Verification script (optional)
└── install_services.sh # Systemd setup (if daemon)
```

## Code vs Data Separation

**Critical Rule**: Skills are synced to multiple locations. Data MUST be stored globally.

### Code (Ephemeral)

- Stored in: `.pi/skills/`, `.agent/skills/`, `.codex/skills/`, etc.
- Synced by: `skills-sync push`
- Can be overwritten anytime

### Data (Persistent)

- Stored in: `~/.pi/<skill-name>/`
- Never synced or overwritten
- Survives skill updates

### Example

```python
# ❌ Wrong - data stored relative to script
DATA_FILE = Path(__file__).parent / "registry.json"

# ✅ Correct - data stored globally
DATA_FILE = Path.home() / ".pi" / "task-monitor" / "registry.json"
```

## Skills Using This Pattern

| Skill          | Global Data Location               |
| -------------- | ---------------------------------- |
| `task-monitor` | `~/.pi/task-monitor/registry.json` |
| `scheduler`    | `~/.pi/scheduler/jobs.json`        |
| `memory`       | ArangoDB (external)                |

## Running Daemons

Systemd services should be installed **once** from any copy:

```bash
cd .pi/skills/task-monitor
./install_services.sh
```

The service uses absolute paths, so all skill copies use the same running daemon.

## Task Monitoring

Long-running skills (high latency, multi-stage, or batch processes) MUST report progress to the global `task-monitor`.

### Standard Implementation

1.  **Registry**: Register your task once using `monitor.py register`.
2.  **State File**: Store state in `~/.pi/<skill-name>/state.json`.
3.  **Frequency**: Update state at least every 5-10 seconds or after each significant item.
4.  **Format**: Use the standard state schema (completed, total, current_item, stats).

### Adapters

- **Python**: Use `from monitor_adapter import Monitor`.
- **Bash**: Source `common.sh` and use `report_progress`.

## Verification

To verify a skill works from multiple locations:

```bash
# From pi-mono
cd ~/workspace/experiments/pi-mono/.pi/skills/task-monitor
uv run python monitor.py status

# From memory (should show same data)
cd ~/workspace/experiments/memory/.pi/skills/task-monitor
uv run python monitor.py status
```
