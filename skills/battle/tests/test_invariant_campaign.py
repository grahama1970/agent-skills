"""Invariant campaign: Red generates a matrix of input versions, runs the target
on each, and an independent Judge scores every output. Proven both directions.
"""
from __future__ import annotations

from pathlib import Path

from battle_skill.invariant_campaign import run_campaign

HERE = Path(__file__).resolve().parent
GEN = str(HERE / "fixtures/mini_generator.py")
JUDGE = str(HERE.parent / "fixtures/reference-judges/no_data_leak_judge.py")


def test_campaign_fails_on_leaky_target() -> None:
    # target = plain copy (no anonymization) -> every version leaks.
    r = run_campaign(
        GEN,
        "mkdir -p {output}/corpus && cp -r {input}/corpus/. {output}/corpus/ && echo '{{}}' > {output}/report.json",
        JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert r.failures and any(f["violations"] for f in r.failures)


def test_campaign_passes_when_value_removed() -> None:
    # target = strip the value from every file -> no version leaks.
    r = run_campaign(
        GEN,
        "mkdir -p {output}/corpus && for f in {input}/corpus/*; do sed 's/5551234567/REDACTED/g' \"$f\" > {output}/corpus/$(basename \"$f\"); done && echo '{{}}' > {output}/report.json",
        JUDGE, output_subdir="corpus")
    assert r.passed is True and not r.failures


def test_beyond_brief_generator_yields_complete_bundles() -> None:
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "beyond_brief_gen", str(HERE.parent / "fixtures/reference-generators/anon_beyond_brief_matrix.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as td:
        cases = list(mod.generate(td, {}))
        names = [n for n, _ in cases]
        assert len(cases) == 13
        for name, input_dir in cases:
            assert (Path(input_dir) / "policy.json").is_file(), name
            assert any((Path(input_dir) / "corpus").iterdir()), name
        assert "bb-json-object-key" in names and "bb-filename-value" in names
        assert "bb-utf16le-bomless-text" in names


def test_beyond_brief_judge_catches_filename_and_utf16_leaks() -> None:
    import importlib.util
    import json
    import tempfile

    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    judge_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(judge_mod)
    value = "Mara Ellison"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        (out / "corpus").mkdir(parents=True)
        (out / "policy.json").write_text(json.dumps({
            "sensitive_values": [{"value": value}]}))
        # leak 1: value carried in the FILE NAME, contents clean
        (out / "corpus" / f"{value}.txt").write_text("clean\n")
        # leak 2: value inside a UTF-16LE text file (invisible to plain utf-8 scan)
        (out / "corpus" / "u.txt").write_bytes(
            b"\xff\xfe" + f"note: {value}\n".encode("utf-16-le"))
        # leak 3: BOM-less UTF-16LE passes strict UTF-8 decode with embedded
        # NULs; the NUL-triggered scan must still catch it (Red win #18).
        (out / "corpus" / "u2.txt").write_bytes(
            f"note: {value}\n".encode("utf-16-le"))
        r = judge_mod.judge(str(out), {"policy": str(out / "policy.json"),
                                       "output_subdir": "corpus"})
    assert r["passed"] is False and len(r["violations"]) == 1
