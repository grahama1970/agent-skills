"""Invariant campaign: Red generates a matrix of input versions, runs the target
on each, and an independent Judge scores every output. Proven both directions.
"""
from __future__ import annotations

from pathlib import Path

from battle_skill.invariant_campaign import run_campaign

HERE = Path(__file__).resolve().parent
GEN = str(HERE / "fixtures/mini_generator.py")
GEN_EXP = str(HERE / "fixtures/mini_expectation_generator.py")
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


def test_anonymizer_generator_includes_roundtable_red_wins() -> None:
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "anon_brief_gen", str(HERE.parent / "fixtures/reference-generators/anon_brief_matrix.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as td:
        cases = list(mod.generate(td, {"fuzz": 0}))
        by_name = {case[0]: case for case in cases}
        assert by_name["adv-formatted-phone-json-integer"][2] == "MUST_ACCEPT"
        assert by_name["adv-formatted-phone-sqlite-integer"][2] == "MUST_ACCEPT"
        assert by_name["adv-cross-format-same-identity-trap"][2] == "MUST_ACCEPT"
        assert by_name["adv-leading-zero-json-integer"][2] == "MUST_REJECT"
        assert by_name["adv-lossy-big-json-float"][2] == "MUST_REJECT"


def test_beyond_brief_generator_yields_complete_bundles() -> None:
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "beyond_brief_gen", str(HERE.parent / "fixtures/reference-generators/anon_beyond_brief_matrix.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as td:
        cases = list(mod.generate(td, {}))
        names = [c[0] for c in cases]
        expectations = [c[2] for c in cases]
        assert len(cases) == 23
        for name, input_dir, _ in cases:
            assert (Path(input_dir) / "policy.json").is_file(), name
            assert any((Path(input_dir) / "corpus").iterdir()), name
        assert "bb-json-object-key" in names and "bb-filename-value" in names
        assert "bb-json-object-key-numeric-alias" in names
        assert "bb-csv-header-numeric-alias" in names
        assert "bb-csv-multiline-quoted-cell" in names
        assert "bb-sqlite-column-identifier-numeric-alias" in names
        assert "bb-sqlite-default-numeric-alias" in names
        assert "bb-sqlite-generated-reconstruction" in names
        assert "bb-sqlite-partial-index" in names
        assert "bb-utf16le-bomless-text" in names
        assert "bb-filename-numeric-alias" in names
        assert expectations.count("MUST_ACCEPT") == 5
        assert expectations.count("MUST_REJECT") == 12
        assert expectations.count("MAY_REJECT") == 6


def _profile(tmp_dir: Path, **data) -> str:
    import json
    p = tmp_dir / "profile.json"
    base = {"schema": "battle.campaign_profile.v1", "profile_id": "test-profile.v1",
            "required_case_ids": []}
    base.update(data)
    p.write_text(json.dumps(base))
    return str(p)


def test_profile_resolves_may_reject_and_enforces_it() -> None:
    # Overlay may-reject-case -> MUST_ACCEPT; the reject-everything target must
    # then FAIL the campaign through the profile-resolved expectation.
    import tempfile
    from battle_skill.invariant_campaign import load_profile
    with tempfile.TemporaryDirectory() as td:
        profile = _profile(Path(td), expectation_overrides={"may-reject-case": "MUST_ACCEPT"})
        prof = load_profile(profile)
    r = run_campaign(GEN_EXP, "exit 1", JUDGE, output_subdir="corpus", profile=prof)
    assert r.passed is False
    assert r.profile_id == "test-profile.v1"
    assert any("required-accept-case-rejected" in v for f in r.failures for v in f["violations"])
    resolved = [c for c in r.case_log if c["case"] == "may-reject-case"]
    assert resolved and resolved[0]["expectation_source"] == "profile"


def test_profile_cannot_downgrade_spec_floor() -> None:
    import tempfile
    from battle_skill.invariant_campaign import load_profile
    with tempfile.TemporaryDirectory() as td:
        profile = _profile(Path(td), expectation_overrides={"must-accept-case": "MUST_REJECT"})
        prof = load_profile(profile)
    r = run_campaign(GEN_EXP, "exit 1", JUDGE, output_subdir="corpus", profile=prof)
    assert r.passed is False
    assert any("profile-illegal-expectation-override" in v for f in r.failures for v in f["violations"])


def test_profile_rejects_unknown_case_and_missing_required_case() -> None:
    import tempfile
    from battle_skill.invariant_campaign import load_profile
    with tempfile.TemporaryDirectory() as td:
        prof = load_profile(_profile(Path(td),
                                     expectation_overrides={"no-such-case": "MUST_REJECT"},
                                     required_case_ids=["must-accept-case", "never-generated-case"]))
    r = run_campaign(GEN_EXP, "exit 1", JUDGE, output_subdir="corpus", profile=prof)
    assert r.passed is False
    assert any("profile-unknown-case-override" in v for f in r.failures for v in f["violations"])
    assert any("profile-required-case-missing:never-generated-case" in v for f in r.failures for v in f["violations"])


def test_campaign_fails_when_target_rejects_everything() -> None:
    # Vacuous-pass killer: an always-rejecting target FAILS the two-axis gate
    # because the MUST_ACCEPT case was not processed (WebGPT roadmap #1).
    r = run_campaign(GEN_EXP, "exit 1", JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert r.declares_expectations is True and r.accepted_count == 0
    assert any("required-accept-case-rejected" in v for f in r.failures for v in f["violations"])


def test_campaign_fails_when_required_reject_case_is_accepted() -> None:
    # A target that accepts the out-of-domain MUST_REJECT input fails coverage
    # even though the judge finds no leak in the copied bytes.
    r = run_campaign(
        GEN_EXP,
        "mkdir -p {output}/corpus && cp -r {input}/corpus/. {output}/corpus/ && echo '{{}}' > {output}/report.json",
        JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert any("required-reject-case-accepted" in v for f in r.failures for v in f["violations"])


def test_campaign_fails_on_vacuous_expectation_declaration() -> None:
    # A generator that declares expectations but zero MUST_ACCEPT cases is a
    # vacuous campaign contract and must fail.
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location("gen_exp", GEN_EXP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    original = mod.generate

    def only_may(work_dir, params):
        for name, d, _ in original(work_dir, params):
            yield name, d, "MAY_REJECT"

    with tempfile.TemporaryDirectory() as td:
        gen_path = Path(td) / "gen.py"
        gen_path.write_text(
            "import json\nfrom pathlib import Path\n\n"
            "def generate(work_dir, params):\n"
            "    d = Path(work_dir); (d / 'c').mkdir(parents=True, exist_ok=True)\n"
            "    (d / 'policy.json').write_text(json.dumps({'sensitive_values': [{'value': 'x'}]}))\n"
            "    (d / 'c' / 'd.txt').write_text('x')\n"
            "    yield 'only-case', str(d), 'MAY_REJECT'\n")
        r = run_campaign(str(gen_path), "exit 1", JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert any("vacuous_campaign_no_required_accept_cases" in v for f in r.failures for v in f["violations"])


def test_no_data_leak_judge_catches_numeric_aliases() -> None:
    import importlib.util
    import json
    import tempfile

    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    judge_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(judge_mod)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        (out / "corpus").mkdir(parents=True)
        (out / "policy.json").write_text(json.dumps({
            "sensitive_values": [{"value": "555-123-4567"}]}))
        (out / "corpus" / "d.json").write_text(json.dumps({"phone": 5551234567}))
        r = judge_mod.judge(str(out), {"policy": str(out / "policy.json"),
                                       "output_subdir": "corpus"})
    assert r["passed"] is False
    assert "555-123-4567" in r["violations"][0]


def test_judge_scans_report_and_execution_logs() -> None:
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
        (out / ".battle-execution").mkdir()
        (out / "policy.json").write_text(json.dumps({
            "sensitive_values": [{"value": value}]}))
        (out / "corpus" / "d.txt").write_text("clean\n")
        (out / "report.json").write_text(json.dumps({"debug": value}))
        (out / ".battle-execution" / "stderr.txt").write_text(f"bad log: {value}\n")
        r = judge_mod.judge(str(out), {"policy": str(out / "policy.json"),
                                       "output_subdir": "corpus"})
    assert r["passed"] is False and value in r["violations"][0]


def test_rejected_campaign_case_fails_if_execution_log_leaks_policy_value() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        gen = Path(td) / "gen.py"
        gen.write_text(
            "import json\nfrom pathlib import Path\n"
            "def generate(work_dir, params):\n"
            "    d = Path(work_dir) / 'case'; (d / 'corpus').mkdir(parents=True)\n"
            "    (d / 'policy.json').write_text(json.dumps({'sensitive_values': [{'value': 'Alice'}]}))\n"
            "    (d / 'corpus' / 'd.txt').write_text('clean')\n"
            "    (d / 'invalid_input.json').write_text(json.dumps({'schema': 'battle.invalid_input_predicate.v1', 'approved': True, 'predicate': 'invalid rejection fixture'}))\n"
            "    yield 'reject-log-leak', str(d), 'MUST_REJECT'\n"
        )
        r = run_campaign(str(gen), "echo Alice >&2; exit 1", JUDGE, output_subdir="corpus")
    assert r.passed is False
    assert any("Alice" in v for f in r.failures for v in f["violations"])


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
