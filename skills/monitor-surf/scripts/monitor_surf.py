#!/usr/bin/env python3
"""monitor-surf: keep a fleet of WebGPT browser tabs healthy for headless work.

Heals conversations that hit the ChatGPT max-length wall, re-binds
browser-oracle names to their tabs, clears stuck webgpt submits, keeps a
producer process alive, and can install itself as a cron. Also offers a cheap
Surf transport health check that submits no provider prompts.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(monitor_surf.cpython-312.pyc) after the .py source was lost (never tracked in
git, no disk copy survived). Faithful to the 3.12 disassembly of all 18
functions. Now TRACKED so the skill cannot be lost again.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SCRIPT = Path(__file__).resolve()
SKILL_DIR = SCRIPT.parents[1]
SKILLS_DIR = SKILL_DIR.parent
SURF = os.environ.get("SURF_RUN", str(SKILLS_DIR / "surf" / "run.sh"))
SURF_CWD = str(Path(SURF).parent)
BO = os.environ.get("BROWSER_ORACLE_RUN", str(SKILLS_DIR / "browser-oracle" / "run.sh"))
EXHAUSTED = re.compile("maximum length for this conversation", re.I)
FRESH_CHAT = "https://chatgpt.com/"
PAUSE_FILE = "monitor-surf.paused"


def pause_path(workdir):
    return Path(workdir or "/tmp") / PAUSE_FILE


def is_paused(workdir):
    """The owning agent pauses this while it drives the tabs itself, so the
    healer does not reset a conversation mid-submit or fight a manual repair."""
    return pause_path(workdir).exists()


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def sh(cmd, cwd, timeout=90):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        log(f"  cmd failed: {str(exc)[:70]}")
        return None


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_probe(name, cmd, cwd, timeout=90):
    started = time.time()
    res = sh(cmd, cwd, timeout)
    elapsed_ms = int((time.time() - started) * 1000)
    if res is None:
        return {
            "name": name,
            "command": cmd,
            "ok": False,
            "returncode": None,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": "",
            "stderr_tail": "command did not run",
        }
    return {
        "name": name,
        "command": cmd,
        "ok": res.returncode == 0,
        "returncode": res.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_tail": res.stdout[-2000:],
        "stderr_tail": res.stderr[-2000:],
    }


def tab_inventory():
    """Preflight the PIPED read - this is exactly how webgpt consumes it."""
    res = sh([SURF, "tab.list", "--json"], SURF_CWD, 60)
    if not res:
        return (None, "tab.list did not run")
    raw = res.stdout
    try:
        data = json.loads(raw)
        tabs = data if isinstance(data, list) else data.get("tabs", [])
        return ({str(t.get("id")): t.get("url", "") for t in tabs}, None)
    except Exception as exc:
        return (None, f"piped tab.list TRUNCATED at {len(raw)} bytes ({str(exc)[:50]}) - see agent-skills#794")


def parse_tab_inventory(raw):
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return data.get("tabs", [])


def health_receipt_path(args):
    root = Path(args.receipt_dir or args.workdir or "/tmp/monitor-surf-health")
    root.mkdir(parents=True, exist_ok=True)
    return root / f"monitor-surf-health-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"


def health_check(args):
    """Cheap Surf health check: no provider prompt submission."""
    probes = []
    errors = []
    warnings = []
    tab_count = None
    binding_rows = None

    for path_name, path in (("surf", SURF), ("browser_oracle", BO)):
        if not Path(path).exists():
            errors.append(f"{path_name}_missing:{path}")
            continue
        if not os.access(path, os.X_OK):
            errors.append(f"{path_name}_not_executable:{path}")

    probes.append(run_probe("surf_extension_ping", [SURF, "extension.ping"], SURF_CWD, 30))
    if not probes[-1]["ok"]:
        errors.append("surf_extension_ping_failed")

    inventory_started = time.time()
    inventory_res = sh([SURF, "tab.list", "--json"], SURF_CWD, 60)
    inventory_stdout = inventory_res.stdout if inventory_res else ""
    inventory = {
        "name": "surf_tab_list_piped_json",
        "command": [SURF, "tab.list", "--json"],
        "ok": bool(inventory_res and inventory_res.returncode == 0),
        "returncode": inventory_res.returncode if inventory_res else None,
        "elapsed_ms": int((time.time() - inventory_started) * 1000),
        "stdout_bytes": len(inventory_stdout.encode()),
        "stdout_tail": inventory_stdout[-2000:],
        "stderr_tail": inventory_res.stderr[-2000:] if inventory_res else "command did not run",
    }
    probes.append(inventory)
    if inventory["ok"]:
        try:
            tabs = parse_tab_inventory(inventory_stdout)
            tab_count = len(tabs)
        except Exception:
            errors.append(f"surf_tab_list_invalid_json_at_{len(inventory_stdout.encode())}_bytes")
        focus = run_probe("surf_focus_state", [SURF, "focus.state", "--json"], SURF_CWD, 30)
        probes.append(focus)
        if not focus["ok"]:
            warnings.append("surf_focus_state_failed")

    bo_started = time.time()
    bo_res = sh([BO, "list", "--backend", "webgpt", "--verify", "--json"], None, 60)
    bo_stdout = bo_res.stdout if bo_res else ""
    bo = {
        "name": "browser_oracle_webgpt_verify",
        "command": [BO, "list", "--backend", "webgpt", "--verify", "--json"],
        "ok": bool(bo_res and bo_res.returncode == 0),
        "returncode": bo_res.returncode if bo_res else None,
        "elapsed_ms": int((time.time() - bo_started) * 1000),
        "stdout_bytes": len(bo_stdout.encode()),
        "stdout_tail": bo_stdout[-2000:],
        "stderr_tail": bo_res.stderr[-2000:] if bo_res else "command did not run",
    }
    probes.append(bo)
    if bo["ok"] and bo_stdout.strip():
        try:
            raw = bo_stdout
            binding_rows = json.loads(raw[raw.find("["):]) if "[" in raw else json.loads(raw)
        except Exception as exc:
            warnings.append(f"browser_oracle_verify_unparseable:{str(exc)[:120]}")
    elif not bo["ok"]:
        warnings.append("browser_oracle_verify_failed")

    if not errors and not warnings:
        status = "PASS"
    elif errors:
        status = "FAIL"
    else:
        status = "DEGRADED"

    receipt = {
        "schema": "monitor_surf.health_receipt.v1",
        "status": status,
        "ok": status == "PASS",
        "mocked": False,
        "live": True,
        "checked_at": utc_now(),
        "claims": {
            "proves": [
                "Surf wrapper path exists and was invoked",
                "Surf extension ping was attempted",
                "piped tab.list --json was attempted without provider prompt submission",
                "browser-oracle webgpt binding verification was attempted",
            ],
            "does_not_prove": [
                "WebGPT provider semantic correctness",
                "future long-running submit completion",
                "ChatGPT rate-limit absence",
            ],
        },
        "surf_run": SURF,
        "browser_oracle_run": BO,
        "tab_count": tab_count,
        "binding_count": len(binding_rows) if isinstance(binding_rows, list) else None,
        "errors": errors,
        "warnings": warnings,
        "probes": probes,
    }
    out = health_receipt_path(args)
    out.write_text(json.dumps(receipt, indent=2) + "\n")
    latest = out.parent / "latest.json"
    latest.write_text(json.dumps(receipt, indent=2) + "\n")
    log(f"health {status}: receipt={out}")
    return 0 if status != "FAIL" else 1


def tab_text(tab, workdir):
    out = Path(workdir) / f".monitor_surf_{tab}.md"
    sh([SURF, "webgpt.extract", "--tab-id", tab, "--output", str(out), "--timeout", "35"], SURF_CWD, 80)
    if out.exists():
        return out.read_text(errors="ignore")
    return ""


def rebind(tab, name, url):
    res = sh([BO, "bind", name, "--backend", "webgpt", "--tab-id", tab, "--url", url, "--manual"], None, 60)
    return bool(res and res.returncode == 0)


def heal_tab(tab, name, workdir):
    """Fresh conversation in the SAME tab id, then rebind - a refresh alone
    invalidates the binding because it pins tab id AND conversation url."""
    sh([SURF, "go", FRESH_CHAT, "--tab-id", tab], SURF_CWD, 70)
    time.sleep(6)
    urls, err = tab_inventory()
    url = (urls or {}).get(tab, "")
    if not url:
        log(f"  {tab}: reset but could not read new url ({err or 'tab missing'})")
        return False
    ok = rebind(tab, name, url)
    log(f"  {tab}: reset -> {url[:56]} | rebind={'ok' if ok else 'FAILED'}")
    return ok


def audit_bindings(tabs, names, urls):
    """Every name must own EXACTLY ONE tab. A heal that rebinds several names to
    the same tab silently starves the others - submits pile onto one
    conversation while the rest sit idle. Repair on sight."""
    res = sh([BO, "list", "--backend", "webgpt", "--verify", "--json"], None, 60)
    if not res or not res.stdout.strip():
        return 0
    try:
        raw = res.stdout
        rows = json.loads(raw[raw.find("["):])
        want = dict(zip(names, tabs))
        fixed = 0
        for row in rows:
            name = row.get("name")
            if name not in want:
                continue
            expected = want[name]
            if str(row.get("tab_id")) == expected:
                continue
            url = (urls or {}).get(expected, "")
            if not url:
                continue
            if not rebind(expected, name, url):
                continue
            log(f"  binding repaired: {name} -> {expected} (was {row.get('tab_id')})")
            fixed += 1
        return fixed
    except Exception:
        return 0


def alive(pattern):
    res = sh(["pgrep", "-f", pattern], None, 20)
    return bool(res and res.stdout.strip())


def cycle(args):
    workdir = args.workdir or "/tmp"
    if is_paused(workdir):
        reason = pause_path(workdir).read_text(errors="ignore").strip() or "no reason given"
        log(f"PAUSED - skipping cycle ({reason[:80]})")
        return 0

    tabs = [t for t in args.tabs.split(",") if t]
    names = args.bind_names.split(",") if args.bind_names else [f"sparta-{i + 1}" for i in range(len(tabs))]

    urls, err = tab_inventory()
    if err:
        log(f"INVENTORY: {err}")
        log("  -> close tabs until the piped read parses; every webgpt submit fails until then")

    healed = 0
    for tab, name in zip(tabs, names):
        text = tab_text(tab, workdir)
        if EXHAUSTED.search(text):
            log(f"tab {tab}: conversation EXHAUSTED")
            if heal_tab(tab, name, workdir):
                healed += 1
        elif urls and not urls.get(tab):
            log(f"tab {tab}: NOT OPEN in inventory")
            if heal_tab(tab, name, workdir):
                healed += 1

    if urls:
        healed += audit_bindings(tabs, names, urls)

    if healed:
        res = sh(["pgrep", "-f", "webgpt_cli.py submit"], None, 20)
        for pid in (res.stdout.split() if res and res.stdout else []):
            sh(["kill", "-9", pid], None, 10)
        log(f"healed {healed} tab(s); cleared stuck submits")

    if args.restart_cmd and not alive(args.restart_cmd.split()[-1]):
        subprocess.Popen(
            args.restart_cmd.split(),
            cwd=args.restart_cwd or None,
            stdout=open(Path(workdir) / "monitor-surf-restart.log", "a"),
            stderr=subprocess.STDOUT,
        )
        log(f"restarted producer: {args.restart_cmd}")

    if args.recover_cmd:
        res = sh(args.recover_cmd.split(), args.restart_cwd or None, 900)
        if res and res.stdout.strip():
            log(f"recover: {res.stdout.strip().splitlines()[-1][:110]}")

    return healed


def install_cron(args):
    script = Path(__file__).resolve()
    if args.health_only:
        cmd = (
            f"{sys.executable} {script} --health-only"
            f"{' --workdir ' + args.workdir if args.workdir else ''}"
            f"{' --receipt-dir ' + args.receipt_dir if args.receipt_dir else ''}"
        )
    else:
        cmd = (
            f"{sys.executable} {script} --tabs {args.tabs} --once"
            f"{' --bind-names ' + args.bind_names if args.bind_names else ''}"
            f"{' --workdir ' + args.workdir if args.workdir else ''}"
            f"{' --restart-cmd ' + repr(args.restart_cmd) if args.restart_cmd else ''}"
            f"{' --restart-cwd ' + args.restart_cwd if args.restart_cwd else ''}"
            f"{' --recover-cmd ' + repr(args.recover_cmd) if args.recover_cmd else ''}"
        )
    if args.cron_tag:
        cmd = f"{cmd} --cron-tag {args.cron_tag}"
    logf = Path(args.workdir or "/tmp") / "monitor-surf-cron.log"
    tag = args.cron_tag or "monitor-surf"
    entry = f"{args.install_cron} {cmd} >> {logf} 2>&1 # {tag}"
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    if tag in cur:
        lines = [l for l in cur.splitlines() if tag not in l]
        cur = "\n".join(lines) + ("\n" if lines else "")
    new = cur + entry + "\n"
    p = subprocess.run(["crontab", "-"], input=new, capture_output=True, text=True)
    if p.returncode == 0:
        log(f"cron installed: {entry}")
        log("verify with: crontab -l | grep monitor_surf")
        return p.returncode
    log(f"cron install FAILED: {p.stderr[:120]}")
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tabs", default="", help="comma-separated chrome tab ids (not needed for pause/resume/status)")
    ap.add_argument("--bind-names", default="", help="comma-separated browser-oracle names")
    ap.add_argument("--interval", type=int, default=600, help="daemon seconds between cycles (default 600 = 10 min)")
    ap.add_argument("--once", action="store_true", help="single cycle then exit (cron mode)")
    ap.add_argument("--workdir", default="", help="scratch + log dir")
    ap.add_argument("--restart-cmd", default="", help="producer to keep alive")
    ap.add_argument("--restart-cwd", default="", help="cwd for producer/recover")
    ap.add_argument("--recover-cmd", default="", help="recovery command for quarantined work")
    ap.add_argument("--install-cron", default="", help='cron expr, e.g. "*/10 * * * *"')
    ap.add_argument("--health-only", action="store_true", help="check Surf transport health without provider submits")
    ap.add_argument("--receipt-dir", default="", help="directory for health receipts")
    ap.add_argument("--cron-tag", default="", help="unique crontab marker for install/update")
    ap.add_argument("--pause", default="", nargs="?", const="paused by agent",
                    help="pause healing (optionally with a reason); cron keeps firing but does nothing")
    ap.add_argument("--resume", action="store_true", help="resume healing")
    ap.add_argument("--status", action="store_true", help="print paused/running state and exit")
    args = ap.parse_args()

    wd = args.workdir or "/tmp"
    if args.status:
        if is_paused(wd):
            log(f"PAUSED: {pause_path(wd).read_text(errors='ignore').strip()[:100]}")
            return 0
        log("RUNNING (not paused)")
        return 0
    if args.pause:
        pause_path(wd).write_text(f"{args.pause} @ {time.strftime('%F %T')}\n")
        log(f"PAUSED -> {pause_path(wd)} ({args.pause})")
        return 0
    if args.resume:
        if pause_path(wd).exists():
            pause_path(wd).unlink()
            log("RESUMED")
            return 0
        log("already running (no pause file)")
        return 0
    if args.install_cron:
        if not args.health_only and not args.tabs:
            log("--tabs is required for fleet cron; use --health-only for global Surf health cron")
            return 2
        return install_cron(args)
    if args.health_only:
        return health_check(args)
    if not args.tabs:
        log("--tabs is required for cycles and daemon mode; use --health-only for global Surf health")
        return 2
    if args.once:
        cycle(args)
        return 0
    log(f"monitor-surf daemon: {len(args.tabs.split(','))} tabs, every {args.interval}s")
    while True:
        try:
            cycle(args)
            time.sleep(args.interval)
        except Exception as exc:
            log(f"cycle error: {str(exc)[:100]}")


if __name__ == "__main__":
    sys.exit(main())
