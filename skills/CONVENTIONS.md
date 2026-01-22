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
