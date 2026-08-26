"""Control-plane server for the eval console.

Owns the run-matrix subprocess lifecycle and serves the React SPA + a small JSON
API the console drives:

  GET  /api/state            current run status, models, bank, progress
  GET  /api/models           selectable model aliases (live from scillm if up)
  GET  /api/banks            ground_truth/*.json bank names
  GET  /api/bank?name=<b>    a bank's questions (id/category/difficulty/input)
  GET  /api/results          current results JSON (live, incrementally written)
  POST /api/run              {models:[...], bank, trials} -> launch a run
  POST /api/control          {action: pause|resume|stop|restart}

Pause is clean (between cells): the runner polls <results>.control which this
server writes. Stop = control stop flag then SIGTERM if needed. Restart = stop
then run with the last params. Static files under ui/dist are served for
everything else. Stdlib only -- no extra deps (best-practices-python: uv/Typer
entrypoint, functions-first, finite timeouts).
"""
from __future__ import annotations

import json
import signal
import subprocess
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import typer

from eval_app import app, console

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
GT_DIR = HERE / "ground_truth"
DIST = HERE / "ui" / "dist"
RUN_SH = HERE / "run.sh"
LIVE_RESULT = RESULTS_DIR / "console.result.json"
CONTROL_FILE = Path(str(LIVE_RESULT) + ".control")
DEFAULT_JUDGE = "claude-fable-5"
SCILLM_MODELS_URL = "http://127.0.0.1:4001/v1/scillm/models"
SCILLM_KEY = "sk-local-4548c981fd9deceecc7ae7fc2f33d08fc909208a212c4fc74fe8fc5080dc2f0c"

# Fallback selectable models (config-known) when scillm isn't reachable.
FALLBACK_MODELS = [
    "local-glm", "gpt-5.5", "oc-glm", "zai-glm-flash", "claude-sonnet-5",
    "claude-opus-5", "claude-fable-5", "gemini-flash", "oc-kimi", "oc-qwen",
    "oc-deepseek", "moonshot-text",
]

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"proc": None, "bank": None, "models": [], "trials": 3, "paused": False}


def _write_control() -> None:
    CONTROL_FILE.write_text(json.dumps({"paused": _STATE["paused"], "stop": False}), encoding="utf-8")


def _stop_flag() -> None:
    CONTROL_FILE.write_text(json.dumps({"paused": False, "stop": True}), encoding="utf-8")


def _running() -> bool:
    proc = _STATE["proc"]
    return proc is not None and proc.poll() is None


def _list_models() -> list[str]:
    try:
        req = urllib.request.Request(SCILLM_MODELS_URL, headers={"Authorization": f"Bearer {SCILLM_KEY}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        return sorted(ids) or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


def _list_banks() -> list[str]:
    return sorted(p.name for p in GT_DIR.glob("*.json"))


def _start_run(models: list[str], bank: str, trials: int) -> None:
    if _running():
        raise RuntimeError("a run is already active; stop it first")
    if not models or not bank:
        raise RuntimeError("models and bank are required")
    _STATE.update(bank=bank, models=models, trials=trials, paused=False)
    _write_control()
    cmd = [str(RUN_SH), "run-matrix", "-g", str(GT_DIR / bank),
           "--models", ",".join(models), "--judge", DEFAULT_JUDGE,
           "--trials", str(trials), "-o", str(LIVE_RESULT)]
    _STATE["proc"] = subprocess.Popen(cmd, cwd=HERE)


def _stop_run() -> None:
    _stop_flag()
    proc = _STATE["proc"]
    if proc is not None and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    _STATE["paused"] = False


def _state_payload() -> dict[str, Any]:
    return {
        "running": _running(), "paused": _STATE["paused"], "bank": _STATE["bank"],
        "models": _STATE["models"], "trials": _STATE["trials"],
        "has_results": LIVE_RESULT.exists(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        query = dict(p.split("=", 1) for p in self.path.split("?", 1)[1].split("&")) if "?" in self.path else {}
        with _LOCK:
            if path == "/api/state":
                return self._json(_state_payload())
            if path == "/api/models":
                return self._json({"models": _list_models()})
            if path == "/api/banks":
                return self._json({"banks": _list_banks()})
            if path == "/api/bank":
                name = query.get("name", "")
                fp = GT_DIR / name
                if not name or not fp.exists():
                    return self._json({"error": "unknown bank"}, 404)
                gt = json.loads(fp.read_text(encoding="utf-8"))
                qs = [{"id": q["id"], "category": q.get("category"), "difficulty": q.get("difficulty"),
                       "input": q.get("input", "")[:200]} for q in gt.get("questions", [])]
                return self._json({"name": name, "models": gt.get("models", []), "questions": qs})
            if path == "/api/results":
                if LIVE_RESULT.exists():
                    return self._send(200, LIVE_RESULT.read_bytes(), "application/json")
                return self._json({"status": "idle", "models": [], "results": []})
        self._serve_static(path)

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (DIST / rel).resolve()
        if not str(target).startswith(str(DIST.resolve())) or not target.is_file():
            target = DIST / "index.html"  # SPA fallback
        if not target.is_file():
            return self._json({"error": "ui not built (run: cd ui && pnpm i && pnpm build)"}, 404)
        ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                 "svg": "image/svg+xml", "json": "application/json"}.get(target.suffix.lstrip("."), "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        if self.path == "/api/actions/register":
            # best-practices-react action ledger (local JSONL, no ArangoDB dep).
            try:
                with (RESULTS_DIR / "app_actions.jsonl").open("a", encoding="utf-8") as fh:
                    for a in body.get("actions", []):
                        fh.write(json.dumps(a) + "\n")
            except OSError:
                pass
            return self._json({"ok": True})
        with _LOCK:
            try:
                if self.path == "/api/run":
                    _start_run(body.get("models", []), body.get("bank", ""), int(body.get("trials", 3)))
                    return self._json({"ok": True, **_state_payload()})
                if self.path == "/api/control":
                    action = body.get("action")
                    if action == "pause":
                        _STATE["paused"] = True; _write_control()
                    elif action == "resume":
                        _STATE["paused"] = False; _write_control()
                    elif action == "stop":
                        _stop_run()
                    elif action == "restart":
                        _stop_run()
                        _start_run(_STATE["models"], _STATE["bank"], _STATE["trials"])
                    else:
                        return self._json({"error": f"unknown action {action!r}"}, 400)
                    return self._json({"ok": True, **_state_payload()})
            except RuntimeError as err:
                return self._json({"error": str(err)}, 409)
        self._json({"error": "not found"}, 404)


@app.command(name="serve")
def serve(
    port: int = typer.Option(8765, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
) -> None:
    """Run the eval-console control server (owns run-matrix; serves the SPA + API)."""
    RESULTS_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    console.print(f"[bold]eval-console[/bold] control server on http://{host}:{port}  "
                  f"(ui {'built' if DIST.exists() else 'NOT built'})")
    console.print("CONTROL_SERVER_READY")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _stop_run()
        httpd.shutdown()
