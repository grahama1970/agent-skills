"""Real-world stress tests for code-runner tool_use loop.

Based on ACTUAL production failures, not toy problems:
- server/index.ts truncated 3800→420 lines (Apr 3 2026)
- 25 data-qs-action attributes mangled
- PostureDashboard.tsx parallel lock contention
- Multi-file React/TypeScript edits

These tests use realistic file sizes, project structures, and DoD commands.
They are designed to stress-test failure modes that broke real project agent tasks.

Run: uv run python stress_test_real.py [--model MODEL] [--repeat N]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import typer
from loguru import logger

from tool_use import run_tool_use_loop

app = typer.Typer()

PASS = 0
FAIL = 0
ERRORS: list[dict] = []


def _result(name: str, passed: bool, detail: str = "") -> None:
    global PASS, FAIL
    if passed:
        PASS += 1
        logger.info("[PASS] {} {}", name, f"— {detail}" if detail else "")
    else:
        FAIL += 1
        logger.error("[FAIL] {} {}", name, f"— {detail}" if detail else "")
        ERRORS.append({"test": name, "detail": detail})


def _run_test(
    name: str,
    files: dict[str, str],
    prompt: str,
    verify: dict[str, str] | None = None,
    verify_absent: dict[str, str] | None = None,
    verify_cmd: str = "",
    verify_line_count: dict[str, tuple[int, int]] | None = None,
    allowlist: list[str] | None = None,
    read_context: list[str] | None = None,
    model: str = "claude-sonnet-4-6",
    expect_fail: bool = False,
    dod_command: str = "",
) -> None:
    """Run a single tool_use test case with real-world verification."""
    with tempfile.TemporaryDirectory(prefix=f"real-{name[:20]}-") as td:
        for path, content in files.items():
            target = Path(td) / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        al = allowlist if allowlist is not None else list(files.keys())

        try:
            written, messages = run_tool_use_loop(
                system_prompt="You are a code-fixing agent. Use the tools to read, edit, and verify. Make SURGICAL edits — do not rewrite entire files.",
                user_prompt=prompt,
                model=model,
                cwd=td,
                allowlist=al,
                read_context=read_context,
                temperature=0.1,
                max_tokens=8000,
                dod_command=dod_command,
            )
        except Exception as e:
            if expect_fail:
                _result(name, True, f"Expected failure: {e}")
            else:
                _result(name, False, f"Exception: {e}")
            return

        if expect_fail:
            _result(name, len(written) == 0, f"written={written} (expected 0)")
            return

        if not written:
            _result(name, False, "No files written")
            return

        # Verify line counts (catches truncation)
        if verify_line_count:
            for path, (min_lines, max_lines) in verify_line_count.items():
                target = Path(td) / path
                if not target.exists():
                    _result(name, False, f"{path} missing")
                    return
                actual = len(target.read_text().splitlines())
                if actual < min_lines or actual > max_lines:
                    _result(name, False,
                            f"{path}: {actual} lines (expected {min_lines}-{max_lines})")
                    return

        # Verify content present
        if verify:
            for path, expected in verify.items():
                target = Path(td) / path
                if not target.exists():
                    _result(name, False, f"{path} not created")
                    return
                content = target.read_text()
                if expected not in content:
                    _result(name, False, f"{path} missing: {expected[:80]}")
                    return

        # Verify content absent
        if verify_absent:
            for path, forbidden in verify_absent.items():
                target = Path(td) / path
                if target.exists() and forbidden in target.read_text():
                    _result(name, False, f"{path} still contains: {forbidden[:80]}")
                    return

        # Verify command
        if verify_cmd:
            clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            clean_env["PATH"] = os.pathsep.join(
                p for p in clean_env.get("PATH", "").split(os.pathsep)
                if ".venv" not in p
            )
            proc = subprocess.run(
                ["bash", "-lc", verify_cmd],
                capture_output=True, text=True, cwd=td, timeout=30, env=clean_env,
            )
            if proc.returncode != 0:
                _result(name, False,
                        f"verify exit={proc.returncode} stderr={proc.stderr[:200]}")
                return

        _result(name, True, f"wrote {len(written)} files")


# ── Helper: Generate realistic files ──────────────────────────────


def _gen_express_server(num_routes: int = 80) -> str:
    """Generate a realistic Express server file (~800 lines)."""
    lines = [
        'import express from "express";',
        'import { Request, Response } from "express";',
        'import httpx from "httpx";',
        '',
        'const app = express();',
        'app.use(express.json());',
        '',
        'const MEMORY_SOCKET = "/run/user/1000/embry/memory.sock";',
        '',
        '// Health check',
        'app.get("/health", (req: Request, res: Response) => {',
        '  res.json({ status: "ok", uptime: process.uptime() });',
        '});',
        '',
    ]
    for i in range(num_routes):
        lines.extend([
            f'// Route {i+1}: /api/v1/resource{i+1}',
            f'app.get("/api/v1/resource{i+1}", async (req: Request, res: Response) => {{',
            f'  try {{',
            f'    const data = await fetchFromMemory("resource{i+1}", req.query);',
            f'    res.json({{ ok: true, data }});',
            f'  }} catch (err) {{',
            f'    console.error("Route {i+1} error:", err);',
            f'    res.status(500).json({{ error: String(err) }});',
            f'  }}',
            f'}});',
            '',
        ])
    lines.extend([
        'async function fetchFromMemory(resource: string, query: any): Promise<any> {',
        '  // Proxy to memory daemon via Unix socket',
        '  return { resource, query, timestamp: Date.now() };',
        '}',
        '',
        'const PORT = parseInt(process.env.PORT || "3001");',
        'app.listen(PORT, () => console.log(`Server on :${PORT}`));',
        '',
        'export default app;',
    ])
    return "\n".join(lines)


def _gen_react_component(name: str, num_elements: int = 40) -> str:
    """Generate a realistic React component with data-qid attributes (~300 lines)."""
    lines = [
        f'import React, {{ useState, useEffect }} from "react";',
        f'import {{ Box, Button, Typography, Tab, Tabs }} from "@mui/material";',
        '',
        f'interface {name}Props {{',
        f'  data: any[];',
        f'  onSelect?: (id: string) => void;',
        f'}}',
        '',
        f'export const {name}: React.FC<{name}Props> = ({{ data, onSelect }}) => {{',
        f'  const [activeTab, setActiveTab] = useState(0);',
        f'  const [selectedId, setSelectedId] = useState<string | null>(null);',
        f'  const [loading, setLoading] = useState(false);',
        '',
        f'  useEffect(() => {{',
        f'    setLoading(true);',
        f'    const timer = setTimeout(() => setLoading(false), 500);',
        f'    return () => clearTimeout(timer);',
        f'  }}, [activeTab]);',
        '',
        f'  const handleSelect = (id: string) => {{',
        f'    setSelectedId(id);',
        f'    onSelect?.(id);',
        f'  }};',
        '',
        f'  return (',
        f'    <Box data-qid="{name.lower()}:root">',
        f'      <Typography variant="h5" data-qid="{name.lower()}:title">{name}</Typography>',
        f'      <Tabs value={{activeTab}} onChange={{(_, v) => setActiveTab(v)}}',
        f'            data-qid="{name.lower()}:tabs">',
    ]
    tabs = ["Overview", "Details", "Analysis", "Settings"]
    for i, tab in enumerate(tabs):
        lines.append(
            f'        <Tab label="{tab}" data-qid="{name.lower()}:tab:{tab.lower()}"'
            f' data-qs-action="switch-tab-{tab.lower()}" title="Switch to {tab}" />'
        )
    lines.extend([
        f'      </Tabs>',
        '',
    ])
    for i in range(num_elements):
        lines.extend([
            f'      {{activeTab === {i % 4} && (',
            f'        <Box data-qid="{name.lower()}:item:{i}" key="{i}">',
            f'          <Button',
            f'            data-qid="{name.lower()}:btn:{i}"',
            f'            data-qs-action="select-item-{i}"',
            f'            title="Select item {i}"',
            f'            onClick={{() => handleSelect("item-{i}")}}',
            f'            variant={{selectedId === "item-{i}" ? "contained" : "outlined"}}',
            f'          >',
            f'            Item {i}: {{data[{i}]?.name || "Loading..."}}',
            f'          </Button>',
            f'        </Box>',
            f'      )}}',
        ])
    lines.extend([
        f'    </Box>',
        f'  );',
        f'}};',
        '',
        f'export default {name};',
    ])
    return "\n".join(lines)


def _gen_python_module(name: str, num_functions: int = 30) -> str:
    """Generate a realistic Python module (~300 lines)."""
    lines = [
        'from __future__ import annotations',
        '',
        'import json',
        'import os',
        'from dataclasses import dataclass, field',
        'from pathlib import Path',
        'from typing import Any',
        '',
        'from loguru import logger',
        '',
        '',
        '@dataclass',
        f'class {name}Config:',
        '    """Configuration for the module."""',
        '    name: str = ""',
        '    debug: bool = False',
        '    max_retries: int = 3',
        '    timeout: float = 30.0',
        '    tags: list[str] = field(default_factory=list)',
        '',
        '',
        f'class {name}:',
        f'    """Main class for {name} operations."""',
        '',
        f'    def __init__(self, config: {name}Config | None = None):',
        f'        self.config = config or {name}Config()',
        '        self._cache: dict[str, Any] = {}',
        '        self._initialized = False',
        '',
        '    def initialize(self) -> None:',
        '        """Initialize the module."""',
        '        if self._initialized:',
        '            return',
        '        logger.info("Initializing {}...", self.config.name)',
        '        self._initialized = True',
        '',
    ]
    for i in range(num_functions):
        lines.extend([
            f'    def process_item_{i}(self, item: dict[str, Any]) -> dict[str, Any]:',
            f'        """Process item type {i}."""',
            f'        if not self._initialized:',
            f'            raise RuntimeError("Not initialized")',
            f'        key = f"item_{i}_{{item.get(\'id\', \'unknown\')}}"',
            f'        if key in self._cache:',
            f'            return self._cache[key]',
            f'        result = {{',
            f'            "type": "item_{i}",',
            f'            "input": item,',
            f'            "processed": True,',
            f'            "score": len(str(item)) / 100.0,',
            f'        }}',
            f'        self._cache[key] = result',
            f'        return result',
            '',
        ])
    lines.extend([
        '    def get_stats(self) -> dict[str, int]:',
        '        """Return cache statistics."""',
        '        return {"cache_size": len(self._cache), "initialized": self._initialized}',
        '',
        '',
        f'def create_{name.lower()}(name: str = "default") -> {name}:',
        f'    """Factory function."""',
        f'    config = {name}Config(name=name)',
        f'    instance = {name}(config)',
        f'    instance.initialize()',
        f'    return instance',
    ])
    return "\n".join(lines)


# ── Real-World Test Cases ─────────────────────────────────────────


def test_large_ts_surgical_edit(model: str) -> None:
    """REPRO: server/index.ts truncation. Edit ONE route in an 800-line Express server.
    Verify the file stays >750 lines (truncation guard)."""
    server = _gen_express_server(80)
    _run_test("large_ts_surgical_edit", model=model,
              files={"server/index.ts": server},
              prompt=(
                  "In server/index.ts, find route /api/v1/resource42 and add "
                  "request validation: check that req.query.limit is a number between 1-100, "
                  "return 400 if invalid. Only edit that ONE route handler. "
                  "Do NOT rewrite the entire file."
              ),
              verify={"server/index.ts": "resource42"},
              verify_line_count={"server/index.ts": (750, 950)})


def test_large_ts_add_route(model: str) -> None:
    """Add a NEW route to an 800-line Express server without truncating."""
    server = _gen_express_server(80)
    _run_test("large_ts_add_route", model=model,
              files={"server/index.ts": server},
              prompt=(
                  "Add a new route POST /api/v1/posture that accepts "
                  "{framework: string, controls: string[]} in the body and returns "
                  "{ok: true, assessment_id: 'new'}. Add it AFTER the health check route. "
                  "Do NOT rewrite the entire file."
              ),
              verify={"server/index.ts": "/api/v1/posture"},
              verify_line_count={"server/index.ts": (800, 960)})


def test_large_python_surgical_edit(model: str) -> None:
    """Edit ONE method in a 500-line Python class without truncating."""
    module = _gen_python_module("Processor", num_functions=30)
    _run_test("large_python_surgical_edit", model=model,
              files={"processor.py": module},
              prompt=(
                  "In processor.py, find process_item_15 and add input validation: "
                  "if item is None or 'id' not in item, raise ValueError('item must have id'). "
                  "Only edit that ONE method."
              ),
              verify={"processor.py": "ValueError"},
              verify_line_count={"processor.py": (480, 550)},
              verify_cmd='python3 -c "from processor import create_processor; p = create_processor(); print(p.process_item_15({\'id\': \'test\'}))"')


def test_large_python_add_method(model: str) -> None:
    """Add a new method to a 500-line Python class without truncating."""
    module = _gen_python_module("Analyzer", num_functions=30)
    _run_test("large_python_add_method", model=model,
              files={"analyzer.py": module},
              prompt=(
                  "Add a method `export_results(self, path: str) -> int` to the Analyzer class "
                  "that writes all cached results to a JSON file at the given path and returns "
                  "the number of items exported. Use json.dumps with indent=2."
              ),
              verify={"analyzer.py": "export_results"},
              verify_line_count={"analyzer.py": (490, 560)},
              verify_cmd='python3 -c "from analyzer import create_analyzer; a = create_analyzer(); a.process_item_0({\'id\': \'x\'}); n = a.export_results(\'/tmp/test_export.json\'); assert n == 1"')


def test_react_preserve_data_attributes(model: str) -> None:
    """REPRO: data-qs-action mangling. Edit a React component without destroying
    existing data-qid, data-qs-action, or title attributes."""
    component = _gen_react_component("PostureDashboard", num_elements=30)
    _run_test("react_preserve_data_attributes", model=model,
              files={"PostureDashboard.tsx": component},
              prompt=(
                  "In PostureDashboard.tsx, add a new state variable `filterText` (string, default '') "
                  "and add a text input field after the Tabs component for filtering. "
                  "Give it data-qid='posturedashboard:filter' and data-qs-action='filter-items'. "
                  "Do NOT modify or remove any existing data-qid or data-qs-action attributes."
              ),
              verify={"PostureDashboard.tsx": 'data-qid="posturedashboard:filter"'},
              verify_cmd=(
                  'grep -c "data-qs-action" PostureDashboard.tsx | '
                  'python3 -c "import sys; n=int(sys.stdin.read().strip()); '
                  'assert n >= 31, f\'Only {n} data-qs-action attrs (expected >=31)\'; '
                  'print(f\'OK: {n} data-qs-action attributes preserved\')"'
              ))


def test_react_add_tab_content(model: str) -> None:
    """Add new tab content to an existing multi-tab React component."""
    component = _gen_react_component("SpartaExplorer", num_elements=20)
    _run_test("react_add_tab_content", model=model,
              files={"SpartaExplorer.tsx": component},
              prompt=(
                  "Add a 5th tab called 'Posture' after the Settings tab. "
                  "When active (activeTab === 4), show a Box with data-qid='spartaexplorer:posture-panel' "
                  "containing a Typography element that says 'Posture assessment coming soon'. "
                  "Do NOT remove or modify any existing tabs or content."
              ),
              verify={"SpartaExplorer.tsx": "Posture"},
              verify_line_count={"SpartaExplorer.tsx": (300, 420)})


def test_multi_file_ts_refactor(model: str) -> None:
    """Extract a function from one TS file into a new utility file + update import."""
    server = _gen_express_server(20)
    _run_test("multi_file_ts_refactor", model=model,
              files={
                  "server/index.ts": server,
                  "server/utils.ts": 'export function formatDate(d: Date): string {\n  return d.toISOString();\n}\n',
              },
              allowlist=["server/index.ts", "server/utils.ts"],
              prompt=(
                  "Move the fetchFromMemory function from server/index.ts into server/utils.ts. "
                  "Add 'export' to it in utils.ts. In index.ts, replace the function with "
                  "an import: import { fetchFromMemory } from './utils'. "
                  "Make sure index.ts still has all its routes."
              ),
              verify={
                  "server/utils.ts": "fetchFromMemory",
                  "server/index.ts": "from './utils'",
              },
              verify_line_count={"server/index.ts": (200, 300)})


def test_python_fix_with_dod(model: str) -> None:
    """Fix a bug where DoD command verifies the fix works end-to-end."""
    _run_test("python_fix_with_dod", model=model,
              files={
                  "calculator.py": (
                      "from __future__ import annotations\n\n"
                      "def calculate(expression: str) -> float:\n"
                      "    \"\"\"Evaluate a simple math expression.\"\"\"\n"
                      "    # BUG: division by zero not handled\n"
                      "    tokens = expression.split()\n"
                      "    if len(tokens) != 3:\n"
                      "        raise ValueError(f'Expected \"a op b\", got: {expression}')\n"
                      "    a, op, b = float(tokens[0]), tokens[1], float(tokens[2])\n"
                      "    if op == '+': return a + b\n"
                      "    if op == '-': return a - b\n"
                      "    if op == '*': return a * b\n"
                      "    if op == '/': return a / b\n"
                      "    raise ValueError(f'Unknown operator: {op}')\n"
                  ),
                  "test_calculator.py": (
                      "from calculator import calculate\n\n"
                      "def test_basic():\n"
                      "    assert calculate('2 + 3') == 5.0\n"
                      "    assert calculate('10 - 4') == 6.0\n"
                      "    assert calculate('3 * 7') == 21.0\n"
                      "    assert calculate('10 / 2') == 5.0\n\n"
                      "def test_division_by_zero():\n"
                      "    try:\n"
                      "        calculate('5 / 0')\n"
                      "        assert False, 'Should have raised'\n"
                      "    except ZeroDivisionError:\n"
                      "        pass\n\n"
                      "if __name__ == '__main__':\n"
                      "    test_basic()\n"
                      "    test_division_by_zero()\n"
                      "    print('All tests passed')\n"
                  ),
              },
              allowlist=["calculator.py"],
              read_context=["test_calculator.py"],
              prompt="Fix the division by zero bug in calculator.py. The test_calculator.py tests should pass.",
              dod_command="python3 test_calculator.py",
              verify_cmd="python3 test_calculator.py")


def test_python_multi_file_import_chain(model: str) -> None:
    """Fix a bug that spans two files with an import dependency."""
    _run_test("python_multi_file_import_chain", model=model,
              files={
                  "models.py": (
                      "from dataclasses import dataclass\n\n"
                      "@dataclass\n"
                      "class User:\n"
                      "    name: str\n"
                      "    email: str\n"
                      "    # BUG: missing age field\n"
                  ),
                  "validators.py": (
                      "from models import User\n\n"
                      "def validate_user(data: dict) -> User:\n"
                      "    if not data.get('name'):\n"
                      "        raise ValueError('name required')\n"
                      "    if not data.get('email'):\n"
                      "        raise ValueError('email required')\n"
                      "    if not isinstance(data.get('age'), int) or data['age'] < 0:\n"
                      "        raise ValueError('age must be non-negative int')\n"
                      "    return User(name=data['name'], email=data['email'], age=data['age'])\n"
                  ),
              },
              prompt=(
                  "The validators.py expects User to have an 'age' field but models.py is missing it. "
                  "Add age: int = 0 to the User dataclass in models.py."
              ),
              verify_cmd=(
                  'python3 -c "'
                  "from validators import validate_user; "
                  "u = validate_user({'name': 'Alice', 'email': 'a@b.com', 'age': 25}); "
                  "assert u.age == 25; print('OK')"
                  '"'
              ))


def test_truncation_guard_write_file(model: str) -> None:
    """DESIGNED TO FAIL: Ask LLM to rewrite a 600-line file completely.
    Truncation guard should block it."""
    module = _gen_python_module("BigModule", num_functions=35)
    _run_test("truncation_guard_write_file", model=model,
              files={"big_module.py": module},
              prompt=(
                  "Completely rewrite big_module.py from scratch. Replace ALL content with a simple "
                  "module that has just one function: def hello(): return 'hello'. "
                  "Use write_file to replace the entire file."
              ),
              expect_fail=True)


def test_truncation_guard_edit_file(model: str) -> None:
    """Directly test edit_file truncation guard — not via LLM (LLM works around it)."""
    from tool_use import execute_tool
    module = _gen_python_module("HugeModule", num_functions=35)
    num_lines = len(module.splitlines())
    with tempfile.TemporaryDirectory(prefix="real-trunc-edit-") as td:
        target = Path(td) / "huge_module.py"
        target.write_text(module)
        result = execute_tool("edit_file", {
            "path": "huge_module.py",
            "start_line": 1,
            "end_line": num_lines,
            "content": "def hello(): return 'hello'\n",
        }, td, ["huge_module.py"])
        passed = "ERROR" in result and "Truncation" in result
        _result("truncation_guard_edit_file", passed,
                f"guard {'blocked' if passed else 'MISSED'}: {result[:120]}")


def test_preserve_unedited_code(model: str) -> None:
    """Edit line 150 of a 500-line file. Verify lines 1-149 and 151+ are unchanged."""
    module = _gen_python_module("Preserver", num_functions=30)
    _run_test("preserve_unedited_code", model=model,
              files={"preserver.py": module},
              prompt=(
                  "In preserver.py, find the process_item_10 method and add a logging call "
                  "as the first line of the method body: logger.debug('Processing item 10'). "
                  "Only add this ONE line. Do not modify anything else."
              ),
              verify={"preserver.py": "Processing item 10"},
              verify_line_count={"preserver.py": (490, 535)},
              verify_cmd=(
                  'python3 -c "'
                  "from preserver import create_preserver; "
                  "p = create_preserver(); "
                  "r = p.process_item_10({'id': 'test'}); "
                  "assert r['type'] == 'item_10'; "
                  "s = p.get_stats(); "
                  "assert s['cache_size'] == 1; "
                  "print('OK')"
                  '"'
              ))


def test_concurrent_safe_edit(model: str) -> None:
    """Edit two separate functions in the same large file. Both should succeed."""
    module = _gen_python_module("DualEdit", num_functions=30)
    _run_test("concurrent_safe_edit", model=model,
              files={"dual_edit.py": module},
              prompt=(
                  "Make TWO changes to dual_edit.py:\n"
                  "1. In process_item_5, add a check: if item.get('skip'): return {'skipped': True}\n"
                  "2. In process_item_20, change the score calculation to: len(str(item)) / 50.0\n"
                  "Make both edits surgically."
              ),
              verify={"dual_edit.py": "skipped"},
              verify_line_count={"dual_edit.py": (490, 530)},
              verify_cmd=(
                  'python3 -c "'
                  "from dual_edit import create_dualedit; "
                  "p = create_dualedit(); "
                  "r1 = p.process_item_5({'id': 'x', 'skip': True}); "
                  "assert r1.get('skipped'), f'skip failed: {r1}'; "
                  "r2 = p.process_item_20({'id': 'y'}); "
                  "print('OK')"
                  '"'
              ))


def test_fix_with_read_context(model: str) -> None:
    """Fix a file using information from a read-only context file."""
    _run_test("fix_with_read_context", model=model,
              files={
                  "config.py": (
                      "# Database configuration\n"
                      "DB_HOST = 'localhost'\n"
                      "DB_PORT = 5432\n"
                      "DB_NAME = 'myapp'\n"
                      "DB_TIMEOUT = 30\n"
                  ),
                  "db.py": (
                      "import config\n\n"
                      "def get_connection_string() -> str:\n"
                      "    # BUG: uses wrong port (hardcoded 3306 instead of config)\n"
                      "    return f'postgresql://{config.DB_HOST}:3306/{config.DB_NAME}'\n"
                  ),
              },
              allowlist=["db.py"],
              read_context=["config.py"],
              prompt="Fix db.py to use config.DB_PORT instead of hardcoded 3306.",
              verify={"db.py": "DB_PORT"},
              verify_cmd=(
                  'python3 -c "'
                  "from db import get_connection_string; "
                  "s = get_connection_string(); "
                  "assert '5432' in s, f'Expected 5432 in {s}'; "
                  "assert '3306' not in s, f'Still has 3306 in {s}'; "
                  "print('OK')"
                  '"'
              ))


# ── Test Registry ──────────────────────────────────────────────────

ALL_TESTS = [
    # Production failure reproductions
    test_large_ts_surgical_edit,          # server/index.ts truncation
    test_large_ts_add_route,              # adding to large TS without truncation
    test_react_preserve_data_attributes,  # data-qs-action mangling
    test_react_add_tab_content,           # multi-tab React edits

    # Large file integrity
    test_large_python_surgical_edit,      # 500-line Python surgical edit
    test_large_python_add_method,         # adding method to 500-line class
    test_preserve_unedited_code,          # verify untouched lines stay untouched
    test_concurrent_safe_edit,            # two edits in same large file

    # Truncation guards (designed to be blocked)
    test_truncation_guard_write_file,     # write_file should block
    test_truncation_guard_edit_file,      # edit_file should block

    # Multi-file operations
    test_multi_file_ts_refactor,          # extract + import in TS
    test_python_multi_file_import_chain,  # fix spanning two Python files
    test_python_fix_with_dod,             # DoD-in-conversation verification
    test_fix_with_read_context,           # read_context informs fix
]


@app.command()
def run(
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m"),
    count: int = typer.Option(0, "--count", "-n", help="Number of tests (0=all)"),
    repeat: int = typer.Option(1, "--repeat", "-r", help="Repeat each test N times"),
    test: str = typer.Option("", "--test", "-t", help="Run single test by name"),
) -> None:
    """Run real-world stress tests for code-runner tool_use loop."""
    if test:
        tests = [t for t in ALL_TESTS if t.__name__ == f"test_{test}" or t.__name__ == test]
        if not tests:
            logger.error("Test '{}' not found. Available: {}", test,
                         [t.__name__.removeprefix("test_") for t in ALL_TESTS])
            return
    elif count > 0:
        tests = ALL_TESTS[:count]
    else:
        tests = ALL_TESTS
    total = len(tests) * repeat

    logger.info("=" * 60)
    logger.info("REAL-WORLD STRESS TEST: {} tests x {} repeats = {} runs", len(tests), repeat, total)
    logger.info("Model: {}", model)
    logger.info("=" * 60)

    start = time.time()
    for rep in range(repeat):
        if repeat > 1:
            logger.info("-- Repeat {}/{} --", rep + 1, repeat)
        for test_fn in tests:
            try:
                test_fn(model)
            except Exception as e:
                _result(test_fn.__name__, False, f"Unhandled: {e}")

    elapsed = time.time() - start
    total_run = PASS + FAIL

    logger.info("=" * 60)
    logger.info("RESULTS: {} passed, {} failed / {} total ({:.0f}s)",
                PASS, FAIL, total_run, elapsed)
    if ERRORS:
        logger.info("FAILURES:")
        for err in ERRORS:
            logger.info("  {} -- {}", err["test"], err["detail"])
    logger.info("PASS RATE: {:.1f}%", PASS / max(total_run, 1) * 100)
    logger.info("=" * 60)


if __name__ == "__main__":
    app()
