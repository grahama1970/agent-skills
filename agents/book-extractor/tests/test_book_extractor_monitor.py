import json
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "book_extractor_monitor.py"
SPEC = importlib.util.spec_from_file_location("book_extractor_monitor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
book_extractor_monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(book_extractor_monitor)
install_cron_block_text = book_extractor_monitor.install_cron_block_text
remove_cron_block_text = book_extractor_monitor.remove_cron_block_text
default_tick_command = book_extractor_monitor.default_tick_command
default_tmux_session_name = book_extractor_monitor.default_tmux_session_name
tmux_attach_command = book_extractor_monitor.tmux_attach_command


def test_install_cron_block_replaces_only_matching_job() -> None:
    original = "\n".join(
        [
            "# unrelated",
            "* * * * * echo keep",
            "# book-extractor-monitor begin job_id=old",
            "* * * * * old",
            "# book-extractor-monitor end job_id=old",
            "# book-extractor-monitor begin job_id=target",
            "* * * * * stale",
            "# book-extractor-monitor end job_id=target",
            "",
        ]
    )

    updated, replaced = install_cron_block_text(
        original,
        job_id="target",
        schedule="*/5 * * * *",
        command="/bin/book-extractor monitor --job target",
    )

    assert replaced is True
    assert "echo keep" in updated
    assert "job_id=old" in updated
    assert "stale" not in updated
    assert "*/5 * * * * /bin/book-extractor monitor --job target" in updated


def test_remove_cron_block_removes_only_matching_job() -> None:
    original = "\n".join(
        [
            "# book-extractor-monitor begin job_id=target",
            "* * * * * target",
            "# book-extractor-monitor end job_id=target",
            "# book-extractor-monitor begin job_id=other",
            "* * * * * other",
            "# book-extractor-monitor end job_id=other",
            "",
        ]
    )

    updated, removed = remove_cron_block_text(original, "target")

    assert removed is True
    assert "job_id=target" not in updated
    assert "job_id=other" in updated
    assert "other" in updated


def test_tick_terminal_state_removes_cron_and_writes_stop_report(tmp_path: Path) -> None:
    controller = tmp_path / "controller"
    controller.mkdir()
    (controller / "state.json").write_text(json.dumps({"status": "accepted", "phase": "verification"}), encoding="utf-8")
    crontab = tmp_path / "crontab"
    crontab.write_text(
        "\n".join(
            [
                "# book-extractor-monitor begin job_id=job1",
                "* * * * * run job1",
                "# book-extractor-monitor end job_id=job1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "controller_root": controller,
            "job_id": "job1",
            "crontab_file": crontab,
        },
    )()

    report = book_extractor_monitor.tick(args)

    assert report["cron_entry_removed"] is True
    assert "job_id=job1" not in crontab.read_text(encoding="utf-8")
    stop_report = json.loads((controller / "monitor_stop_report.json").read_text(encoding="utf-8"))
    assert stop_report["reason"] == "terminal_state:accepted"
    assert stop_report["cron_entry_removed"] is True


def test_cli_install_and_tick_removes_terminal_cron_block(tmp_path: Path) -> None:
    controller = tmp_path / "controller"
    controller.mkdir()
    (controller / "state.json").write_text(json.dumps({"status": "accepted", "phase": "verification"}), encoding="utf-8")
    crontab = tmp_path / "crontab"

    install = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "install-cron",
            "--controller-root",
            str(controller),
            "--job-id",
            "job1",
            "--crontab-file",
            str(crontab),
            "--schedule",
            "* * * * *",
            "--command",
            "echo job1",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr
    assert "job_id=job1" in crontab.read_text(encoding="utf-8")

    tick = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "tick",
            "--controller-root",
            str(controller),
            "--job-id",
            "job1",
            "--crontab-file",
            str(crontab),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert tick.returncode == 0, tick.stderr
    assert "job_id=job1" not in crontab.read_text(encoding="utf-8")
    stop_report = json.loads((controller / "monitor_stop_report.json").read_text(encoding="utf-8"))
    assert stop_report["cron_entry_removed"] is True


def test_install_cron_generates_tick_command_when_command_omitted(tmp_path: Path) -> None:
    controller = tmp_path / "controller"
    controller.mkdir()
    crontab = tmp_path / "crontab"

    install = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "install-cron",
            "--controller-root",
            str(controller),
            "--job-id",
            "job1",
            "--crontab-file",
            str(crontab),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert install.returncode == 0, install.stderr
    content = crontab.read_text(encoding="utf-8")
    assert "book_extractor_monitor.py tick" in content
    assert "--controller-root" in content
    assert "--job-id job1" in content
    state = json.loads((controller / "monitor_state.json").read_text(encoding="utf-8"))
    assert state["monitor_log_path"] == str(controller / "monitor.log")


def test_default_tick_command_can_embed_test_crontab_path(tmp_path: Path) -> None:
    command = default_tick_command(
        controller_root=tmp_path / "controller",
        job_id="job1",
        crontab_file=tmp_path / "crontab",
    )

    assert "book_extractor_monitor.py tick" in command
    assert "--crontab-file" in command
    assert "job1" in command


def test_tmux_session_name_and_attach_command_are_deterministic(tmp_path: Path) -> None:
    session = default_tmux_session_name("Flight Of The Eisenstein: Horus/Lupercal")
    socket = tmp_path / "tmux.sock"

    command = tmux_attach_command(socket, session)

    assert session == "book-extractor-flight-of-the-eisenstein-horus-lupercal"
    assert "tmux -S" in command
    assert "attach-session" in command
    assert session in command


def test_tick_writes_project_agent_monitor_log_and_status(tmp_path: Path) -> None:
    controller = tmp_path / "controller"
    controller.mkdir()
    (controller / "state.json").write_text(json.dumps({"status": "running", "phase": "fact_extraction"}), encoding="utf-8")
    (controller / "commands.jsonl").write_text(json.dumps({"command_id": "cmd-1", "exit_code": 0}) + "\n", encoding="utf-8")
    (controller / "chapter_step_progress.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "book_extractor_chapter_step_progress.v1",
                "timestamp": "2026-06-15T12:00:00+00:00",
                "chapter_id": "book_ch01",
                "chapter_index": 1,
                "chunk_id": "c01",
                "accepted": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    crontab = tmp_path / "crontab"
    args = type(
        "Args",
        (),
        {
            "controller_root": controller,
            "job_id": "job1",
            "crontab_file": crontab,
            "restart_command": None,
        },
    )()

    row = book_extractor_monitor.tick(args)

    assert row["progress"]["accepted_step_count"] == 1
    assert (controller / "heartbeat.jsonl").exists()
    assert (controller / "monitor.log").exists()
    assert "status=running" in (controller / "monitor.log").read_text(encoding="utf-8")
    assert "Single tail log" in (controller / "monitor_status.md").read_text(encoding="utf-8")


def test_install_cron_can_derive_paths_from_job_file(tmp_path: Path) -> None:
    output_root = tmp_path / "book_output"
    controller = output_root / "book_extractor"
    controller.mkdir(parents=True)
    job_file = tmp_path / "job.yaml"
    job_file.write_text(
        "\n".join(
            [
                "schema_version: book_extractor_job.v1",
                "job_id: job-from-yaml",
                "outputs:",
                f"  root: {output_root}",
                "runtime:",
                "  self_monitor_schedule: '*/5 * * * *'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    crontab = tmp_path / "crontab"

    install = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "install-cron",
            "--job-file",
            str(job_file),
            "--crontab-file",
            str(crontab),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert install.returncode == 0, install.stderr
    content = crontab.read_text(encoding="utf-8")
    assert "job_id=job-from-yaml" in content
    assert "*/5 * * * *" in content
    state = json.loads((controller / "monitor_state.json").read_text(encoding="utf-8"))
    assert state["job_id"] == "job-from-yaml"


def test_cli_launch_attach_print_and_stop_tmux(tmp_path: Path) -> None:
    if shutil.which("tmux") is None:
        return
    controller = tmp_path / "controller"
    controller.mkdir()
    (controller / "state.json").write_text(json.dumps({"status": "running", "phase": "fact_extraction"}), encoding="utf-8")

    launch = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "launch-tmux",
            "--controller-root",
            str(controller),
            "--job-id",
            "job1",
            "--tmux-command",
            "printf ready; sleep 60",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        assert launch.returncode == 0, launch.stderr
        state = json.loads((controller / "tmux_state.json").read_text(encoding="utf-8"))
        assert state["schema_version"] == "book_extractor_tmux_state.v1"
        assert state["running"] is True
        assert state["attach_command"].startswith("tmux -S ")

        attach = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "attach-tmux",
                "--controller-root",
                str(controller),
                "--job-id",
                "job1",
                "--print-command",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert attach.returncode == 0, attach.stderr
        attach_payload = json.loads(attach.stdout)
        assert attach_payload["running"] is True
        assert attach_payload["attach_command"] == state["attach_command"]
    finally:
        stop = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "stop-tmux",
                "--controller-root",
                str(controller),
                "--job-id",
                "job1",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert stop.returncode == 0, stop.stderr
    stopped = json.loads((controller / "tmux_state.json").read_text(encoding="utf-8"))
    assert stopped["schema_version"] == "book_extractor_tmux_stop.v1"
    assert stopped["running"] is False
