"""Root conftest: make src/python importable as 'extract_tables' package.

Also registers sub-packages (parsers, etc.) so that both import styles work:
  - from extract_tables.parsers.hybrid import HybridParser  (package-relative)
  - from parsers.hybrid import HybridParser                 (direct, used by blind tests)
"""
import importlib
import os
import sys

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_src_python = os.path.join(SKILL_DIR, "src", "python")

# Ensure src/python is on sys.path so that non-relative imports
# within sub-modules (e.g. `from models import ...`) still resolve.
if _src_python not in sys.path:
    sys.path.insert(0, _src_python)

# Register src/python as the 'extract_tables' package so that
# `from extract_tables import read_pdf` works with relative imports.
if "extract_tables" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "extract_tables",
        os.path.join(_src_python, "__init__.py"),
        submodule_search_locations=[_src_python],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_tables"] = mod
    spec.loader.exec_module(mod)

# Register sub-packages as aliases so that `from parsers.hybrid import ...`
# resolves relative imports (from ..models) correctly by treating `parsers`
# as `extract_tables.parsers` rather than a standalone top-level package.
_parsers_dir = os.path.join(_src_python, "parsers")
if os.path.isdir(_parsers_dir) and "parsers" not in sys.modules:
    _et = sys.modules.get("extract_tables")
    if _et is not None:
        try:
            parsers_spec = importlib.util.spec_from_file_location(
                "extract_tables.parsers",
                os.path.join(_parsers_dir, "__init__.py"),
                submodule_search_locations=[_parsers_dir],
            )
            parsers_mod = importlib.util.module_from_spec(parsers_spec)
            sys.modules["extract_tables.parsers"] = parsers_mod
            sys.modules["parsers"] = parsers_mod  # alias for direct imports
            parsers_spec.loader.exec_module(parsers_mod)
        except Exception:
            # If parsers init fails (e.g. optional dependencies missing),
            # clean up partial registration so imports can fall through normally
            sys.modules.pop("extract_tables.parsers", None)
            sys.modules.pop("parsers", None)
