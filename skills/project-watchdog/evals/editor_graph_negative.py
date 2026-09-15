#!/usr/bin/env python3
"""Check draft conflicts and invalid graph/run identifiers without touching production."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from watchdog_workflow_cli import read_run, wd
import watchdog_graph as graph_module


def main() -> None:
    graph = deepcopy(graph_module.read_graph("active")[0])
    graph["nodes"][0]["depends_on"] = ["reviewer"]
    try:
        graph_module.validate_graph(graph)
    except graph_module.GraphError:
        pass
    else:
        raise AssertionError("cycle accepted")
    try:
        read_run("../../etc/passwd")
    except graph_module.GraphError:
        pass
    else:
        raise AssertionError("unsafe run identifier accepted")
    with patch.dict(os.environ, {"PATH": "/workspace/node_modules/.bin:/global/bin", "PROJECT_WATCHDOG_PI_BIN": ""}, clear=False):
        with patch.object(wd.shutil, "which", return_value="/global/bin/pi"):
            selected = wd.pi_environment()
    assert selected["PI_SUBAGENT_PI_BINARY"] == "/global/bin/pi"
    assert selected["PATH"] == "/global/bin"
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "draft.json"
        original = graph_module.canonical_bytes(graph_module.read_graph("active")[0])
        path.write_bytes(original)
        with patch.object(graph_module, "DRAFT_GRAPH", path), patch.dict(os.environ, {"PROJECT_WATCHDOG_STATE_ROOT": root}):
            try:
                graph_module.save_graph(graph_module.read_graph("active")[0], "wrong-revision")
            except graph_module.RevisionConflict:
                pass
            else:
                raise AssertionError("stale draft write accepted")
        assert path.read_bytes() == original
    print("PROJECT_WATCHDOG_EDITOR_NEGATIVE_OK")


if __name__ == "__main__":
    main()
