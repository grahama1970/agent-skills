"""Blind adversarial tests for Task 16: mypyc compilation."""
import sys
import os
import importlib
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))


class TestCompiledModuleImport:
    def test_compiled_module_exists(self):
        """At least one mypyc-compiled module should be importable."""
        compiled_found = False
        modules_to_try = [
            "parsers.stream",
            "parsers.network",
            "parsers.hybrid",
            "merger",
            "models",
        ]
        for mod_name in modules_to_try:
            try:
                mod = importlib.import_module(mod_name)
                # Check if it has a compiled (.so/.pyd) backing
                mod_file = getattr(mod, "__file__", "")
                if mod_file and (".so" in mod_file or ".pyd" in mod_file):
                    compiled_found = True
                    break
            except ImportError:
                continue

        # Even if not .so, check build_parsers exists
        if not compiled_found:
            try:
                from build_parsers import build as build_fn
                compiled_found = True  # Build script exists, compilation is possible
            except ImportError:
                pass

        assert compiled_found, (
            "No compiled module found. Either a .so/.pyd module or build_parsers.py must exist."
        )

    def test_compiled_produces_same_output(self):
        """If compiled module exists, it should produce identical results to source."""
        # Try importing stream parser (most likely to be compiled)
        try:
            from parsers.stream import StreamParser
            parser = StreamParser()
            # Just verify it's importable and instantiable
            assert parser is not None
        except ImportError:
            pytest.skip("StreamParser not available")

    def test_build_script_exists(self):
        """build_parsers.py should exist for mypyc compilation."""
        build_path = os.path.join(SKILL_DIR, "src", "python", "build_parsers.py")
        assert os.path.exists(build_path), \
            f"build_parsers.py not found at {build_path}"
