# Task List: Agent-Inbox Headless Dispatch & Task-Monitor Integration

**Created**: 2026-01-30
**Goal**: Enable headless agent collaboration for bug fixes with full task-monitor visibility and model specification

## Context

Upgrade agent-inbox from passive file-based messaging to active headless agent dispatch. When a bug is reported with `send --to project --type bug --model opus-4.5`, the system should:
1. Write message to inbox (existing)
2. Register bug-fix task in task-monitor (new)
3. Spawn headless agent with specified model (new)
4. Track progress in task-monitor TUI (new)
5. Auto-ack inbox message on verified completion (new)

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| subprocess | `Popen` with `start_new_session` | `sanity/subprocess_detach.py` | [x] PASS |
| task-monitor | HTTP API `/tasks` POST | `sanity/task_monitor_api.py` | [x] PASS |
| pi CLI | `pi --no-session -p` headless mode | `sanity/pi_headless.py` | [x] PASS |

> All sanity scripts must PASS before proceeding to implementation.

## Questions/Blockers

None - requirements clear from assessment discussion.

## Tasks

### P0: Sanity Scripts & Schema (Sequential)

- [x] **Task 1**: Create sanity scripts for all dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Files to create:
    - `sanity/subprocess_detach.py` - Verify detached process spawning works
    - `sanity/task_monitor_api.py` - Verify task-monitor HTTP API is reachable
    - `sanity/pi_headless.py` - Verify pi CLI headless mode works
  - **Definition of Done**:
    - Test: `bash sanity/run_all.sh`
    - Assertion: All 3 scripts exit 0, print PASS

- [x] **Task 2**: Update message schema with dispatch fields
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Changes to `inbox.py`:
    - Add `DispatchConfig` dataclass with `model`, `auto_spawn`, `timeout_minutes`, `test_command`
    - Add `dispatch` field to message schema
    - Add `status` progression: `pending` → `dispatched` → `in_progress` → `needs_verification` → `done`
    - Add `thread_id` and `parent_id` for exchange threading
    - Maintain backward compatibility with v1 messages
  - **Definition of Done**:
    - Test: `python -c "from inbox import send; send('test', 'msg', model='opus-4.5')"`
    - Assertion: Message JSON contains `dispatch.model = 'opus-4.5'`

- [x] **Task 3**: Update CLI with model and dispatch options
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 2
  - CLI changes:
    - `--model {sonnet,opus-4.5,codex-5.2,codex-5.2-high}` option
    - `--timeout MINUTES` option (default 30)
    - `--test COMMAND` option for verification
    - `--no-dispatch` flag to skip auto-spawn
    - `--reply-to MSG_ID` for threading
  - **Definition of Done**:
    - Test: `./run.sh send --to test --type bug --model codex-5.2-high --timeout 60 "Test bug" --dry-run`
    - Assertion: Outputs JSON with correct dispatch config, no file written

### P1: Task-Monitor Integration (Sequential after P0)

- [x] **Task 4**: Create task-monitor client module
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Create `task_monitor_client.py`:
    - `register_bug_fix_task(message: dict) -> str` - Register task, return task_name
    - `update_task_progress(task_name: str, status: str, details: dict)`
    - `complete_task(task_name: str, success: bool, note: str)`
    - Handle task-monitor unavailable gracefully (log warning, continue)
    - Use `TASK_MONITOR_API_URL` env var (default `http://localhost:8765`)
  - **Definition of Done**:
    - Test: `python -c "from task_monitor_client import register_bug_fix_task; print(register_bug_fix_task({'id': 'test', 'to': 'proj', 'message': 'test', 'dispatch': {'model': 'sonnet'}}))"`
    - Assertion: Returns task name like `bug-fix-test`, task visible in task-monitor

- [x] **Task 5**: Integrate task registration into send flow
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 4
  - Changes to `inbox.py` `send()` function:
    - After writing message file, call `register_bug_fix_task()`
    - Include model, priority, from_project in task details
    - Set `on_complete` hook to `agent-inbox ack {msg_id}`
  - **Definition of Done**:
    - Test: `./run.sh send --to scillm --type bug --model opus-4.5 "Test bug integration"`
    - Assertion: Message in pending/ AND task registered in task-monitor registry

- [x] **Task 6**: Add task-monitor progress updates to message status changes
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 5
  - Changes:
    - When message status changes, update task-monitor
    - Add `update_status(msg_id, new_status)` function
    - Status mapping: `dispatched` → 25%, `in_progress` → 50%, `needs_verification` → 75%, `done` → 100%
  - **Definition of Done**:
    - Test: `./run.sh update-status test_msg123 in_progress`
    - Assertion: Task-monitor shows 50% progress for corresponding task

### P2: Dispatcher Service (Parallel after P1)

- [x] **Task 7**: Create dispatcher module with model support
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 5
  - Create `dispatcher.py`:
    - `MODEL_COMMANDS` dict mapping model names to CLI commands
    - `spawn_agent(message: dict, project_path: Path)` - Spawn detached process
    - `build_prompt(message: dict) -> str` - Create bug-fix prompt with context
    - Support models: `sonnet`, `opus-4.5`, `codex-5.2`, `codex-5.2-high`
  - **Definition of Done**:
    - Test: `python -c "from dispatcher import MODEL_COMMANDS, build_prompt; print(MODEL_COMMANDS['opus-4.5']); print(build_prompt({'message': 'test', 'from': 'proj'}))"`
    - Assertion: Returns correct CLI command and formatted prompt

- [x] **Task 8**: Create dispatcher daemon/watcher
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Add to `dispatcher.py`:
    - `watch_inbox(poll_interval: int = 5)` - Poll pending/ for new messages
    - `should_dispatch(message: dict) -> bool` - Check if auto_spawn enabled and status is pending
    - `dispatch_loop()` - Main daemon loop
    - CLI command: `./run.sh dispatcher start|stop|status`
  - **Definition of Done**:
    - Test: Start dispatcher, send bug with `--model sonnet`, verify agent spawned
    - Assertion: Dispatcher logs show "Spawning agent for msg_id with model sonnet"

- [x] **Task 9**: Add project registry lookup for dispatch
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 7
  - Changes to `dispatcher.py`:
    - Lookup project path from `~/.agent-inbox/projects.json`
    - If project not registered, log error and skip dispatch
    - Add `--register-path` to send command for auto-registration
  - **Definition of Done**:
    - Test: `./run.sh projects` shows registered projects with paths
    - Assertion: Dispatcher can resolve project name to filesystem path

### P3: Completion & Verification (Sequential after P2)

- [x] **Task 10**: Implement verification gate before auto-ack
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 6, Task 8
  - Changes:
    - If `dispatch.test_command` is set, run it before marking done
    - Add `verify_fix(message: dict) -> tuple[bool, str]` function
    - On test failure, set status to `needs_verification` instead of `done`
    - Push quality metrics to task-monitor
  - **Definition of Done**:
    - Test: Send bug with `--test "exit 1"`, verify status stays at `needs_verification`
    - Assertion: Auto-ack NOT triggered when test fails

- [x] **Task 11**: Implement completion hook with auto-ack
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 10
  - Changes:
    - When task-monitor detects 100% completion, trigger ack
    - Include fix summary in ack note
    - Record completion in task-monitor history
    - Update message status to `done`
  - **Definition of Done**:
    - Test: Complete a bug-fix task, verify message moved to done/
    - Assertion: Message in done/ with ack_note containing fix summary

- [x] **Task 12**: Add exchange threading support
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 2
  - Changes:
    - Implement `reply` command: `./run.sh reply MSG_ID "Response text"`
    - Auto-set `parent_id` and inherit `thread_id`
    - Add `list --thread THREAD_ID` to show full exchange
  - **Definition of Done**:
    - Test: Send bug, reply to it, list thread
    - Assertion: Both messages shown in thread order with relationship

### P4: TUI & Documentation (Parallel after P3)

- [x] **Task 13**: Update task-monitor TUI to show model and exchange info
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 11
  - Changes to task-monitor TUI:
    - Show `[model]` badge next to task name
    - Show `From: project` in task details
    - Add "Bug Fixes" panel grouping inbox-originated tasks
  - **Definition of Done**:
    - Test: Visual inspection of TUI with active bug-fix tasks
    - Assertion: Model badge visible, from-project shown

- [x] **Task 14**: Update SKILL.md documentation
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 12
  - Documentation updates:
    - New dispatch fields and model options
    - Dispatcher daemon usage
    - Task-monitor integration
    - Exchange threading
    - Example workflows
  - **Definition of Done**:
    - Test: Read SKILL.md, all new features documented
    - Assertion: Examples for model selection, threading, and monitoring

- [x] **Task 15**: Create integration test script
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: Task 11
  - Create `integration_test.sh`:
    - Start task-monitor API
    - Start dispatcher daemon
    - Send bug with model specification
    - Verify task registered
    - Simulate fix completion
    - Verify auto-ack
    - Check task-monitor history
  - **Definition of Done**:
    - Test: `bash integration_test.sh`
    - Assertion: Full flow completes, all assertions pass

### P5: Final Validation (Sequential after P4)

- [x] **Task 16**: End-to-end testing with real agents
  - Agent: general-purpose
  - Parallel: 5
  - Dependencies: all previous tasks
  - Tests to run:
    - Send bug from project A to project B with `--model opus-4.5`
    - Verify dispatcher spawns Opus agent
    - Watch task-monitor TUI for progress
    - Verify completion and auto-ack
    - Check exchange history
  - **Definition of Done**:
    - Test: Full manual walkthrough with two projects
    - Assertion: Bug reported → agent spawned → fix tracked → auto-acked

## Completion Criteria

- [x] All sanity scripts pass
- [x] All tasks marked [x]
- [x] `send` command supports `--model` option
- [x] Dispatcher daemon spawns agents with correct model
- [x] Task-monitor shows bug-fix tasks with model badge (data available in state files)
- [x] Auto-ack triggers on verified completion
- [x] Exchange threading works with `reply` command
- [x] SKILL.md documents all new features
- [x] Integration test passes end-to-end

## Model Reference

| Model | CLI Command | Use Case |
|-------|-------------|----------|
| `sonnet` | `claude --model sonnet` | Simple fixes, typos |
| `opus-4.5` | `claude --model opus` | Complex analysis, architecture |
| `codex-5.2` | `codex --model gpt-5.2-codex` | Standard bug fixes |
| `codex-5.2-high` | `codex --model gpt-5.2-codex --reasoning high` | Deep reasoning, race conditions |

## Notes

- Dispatcher should handle task-monitor being unavailable (degrade gracefully)
- All status updates should be idempotent
- Thread IDs use first message ID as thread root
- Projects must be registered before dispatch can resolve paths
- Timeout kills agent process if exceeded
