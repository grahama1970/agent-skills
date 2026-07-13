from __future__ import annotations

import json
import os
import stat
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "skills" / "surf" / "scripts" / "live-tab-maintenance-canary.sh"


def run_canary(args, *, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        text=True,
        capture_output=True,
        env=merged,
        timeout=20,
    )


def test_refuses_by_default_without_extension_socket_and_local_app():
    proc = run_canary([
        "--json",
        "--local-app-url",
        "http://127.0.0.1:9",
    ], env={"SURF_EXTENSION_SOCKET": "/tmp/surf-canary-definitely-missing.sock"})

    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["status"] == "refused"
    assert payload["reason"] == "extension_socket_unreachable"


def test_help_documents_bounded_disposable_live_canary_contract():
    proc = run_canary(["--help"])

    assert proc.returncode == 0
    assert "disposable local-app browser tabs" in proc.stdout
    assert "one intended recoverable reload" in proc.stdout
    assert "draft-present guarded skip" in proc.stdout
    assert "ambiguous-URL guarded skip" in proc.stdout
    assert "active-generation guarded skip" in proc.stdout


def test_canary_uses_only_created_tabs_validates_receipts_and_cleans_up(tmp_path):
    db = tmp_path / "surf-db.json"
    fake_surf = tmp_path / "fake-surf.py"
    fake_surf.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(f"""
        import json, sys
        from pathlib import Path

        db = Path({str(db)!r})

        def load():
            if db.exists():
                return json.loads(db.read_text())
            return {{"next_id": 100, "tabs": [], "closed": []}}

        def save(data):
            db.write_text(json.dumps(data, sort_keys=True))

        data = load()
        args = sys.argv[1:]
        cmd = args[0] if args else ""

        if cmd == "focus.state":
            print(json.dumps({{"activeTabId": "42", "focusedWindowId": "7"}}))
            sys.exit(0)

        if cmd == "tab.list":
            if "--json" in args:
                print(json.dumps(data["tabs"]))
            else:
                for tab in data["tabs"]:
                    print(f"{{tab['tab_id']}}\\t{{tab.get('title', '')}}\\t{{tab['url']}}")
            sys.exit(0)

        if cmd == "tab.new":
            url = args[-1]
            tab_id = str(data["next_id"])
            data["next_id"] += 1
            data["tabs"].append({{"tab_id": tab_id, "title": "canary", "url": url}})
            save(data)
            print(json.dumps({{"tab_id": tab_id}}))
            sys.exit(0)

        if cmd == "tab.close":
            tab_id = args[-1]
            before = list(data["tabs"])
            data["tabs"] = [t for t in data["tabs"] if str(t.get("tab_id")) != str(tab_id)]
            if len(before) != len(data["tabs"]):
                data.setdefault("closed", []).append(str(tab_id))
            save(data)
            print("OK")
            sys.exit(0)

        if cmd == "tab.recovery-state":
            tab_id = args[args.index("--tab-id") + 1]
            tab = next((t for t in data["tabs"] if str(t.get("tab_id")) == str(tab_id)), None)
            url = tab.get("url", "") if tab else ""
            guards = {{
                "chatgptGeneration": False,
                "nonEmptyEditableDraft": False,
                "activeDownload": False,
            }}
            if "draft-present" in url:
                guards["nonEmptyEditableDraft"] = True
            if "active-generation" in url:
                guards["chatgptGeneration"] = True
            print(json.dumps({{"guards": guards}}))
            sys.exit(0)

        if cmd == "tab.reload":
            tab_id = args[args.index("--tab-id") + 1]
            if not any(str(t.get("tab_id")) == str(tab_id) for t in data["tabs"]):
                print("missing", file=sys.stderr)
                sys.exit(1)
            data.setdefault("reloaded", []).append(str(tab_id))
            save(data)
            print("OK")
            sys.exit(0)

        print(f"unknown command: {{args}}", file=sys.stderr)
        sys.exit(2)
    """))
    fake_surf.chmod(fake_surf.stat().st_mode | stat.S_IXUSR)

    work_dir = tmp_path / "work"
    proc = run_canary([
        "--json",
        "--allow-unreachable",
        "--surf-run",
        str(fake_surf),
        "--local-app-url",
        "http://127.0.0.1:8765",
        "--work-dir",
        str(work_dir),
    ])

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["status"] == "pass"
    assert len(payload["created_tab_ids"]) == 5
    assert payload["focus_before"] == payload["focus_after"] == {"activeTabId": "42", "focusedWindowId": "7"}
    assert payload["receipts"]["reload"]["status"] == "reloaded"
    assert payload["receipts"]["draft"]["reason"] == "guards_not_safe"
    assert payload["receipts"]["generation"]["reason"] == "guards_not_safe"
    assert payload["receipts"]["ambiguous"]["reason"] == "stored_tab_not_live"

    state = json.loads(db.read_text())
    assert state["tabs"] == []
    assert sorted(state["closed"]) == sorted(payload["created_tab_ids"])
    assert state["reloaded"] == [payload["created_tab_ids"][0]]
    assert not any((work_dir / "bindings").glob("*.json"))
