from __future__ import annotations

from pathlib import Path

import pytest

from battle_skill.adaptive_arena_creator_dag import (
    ARENA_SCENARIO_SCHEMA,
    AskTauArenaCreatorDagBackend,
    build_arena_creator_request,
    _extract_json_array,
    _parse_verdicts,
)
from battle_skill.adaptive_lineage_engine import GenerationRequest, RecallResult
from battle_skill.adaptive_lineage_oracles import (
    TauArenaCreatorDagBackend,
    TauArenaPopulationHooks,
)


def _request(tmp_path: Path, *, n: int = 3) -> GenerationRequest:
    return GenerationRequest(
        battle_id="battle-004",
        lineage_id="arena-main",
        run_id="r",
        role="arena-creator",
        generation=1,
        population_size=n,
        max_generations=2,
        max_recall_hops=3,
        out_dir=tmp_path,
        subgraph_scope={"role": "arena-creator"},
    )


def test_backend_satisfies_the_tau_dag_protocol(tmp_path: Path) -> None:
    backend = AskTauArenaCreatorDagBackend(ask_run=tmp_path / "run.sh")
    assert isinstance(backend, TauArenaCreatorDagBackend)
    # And plugs into the existing arena population-hooks adapter.
    TauArenaPopulationHooks(backend)


def test_request_carries_the_non_degeneracy_and_diversity_constraints(
    tmp_path: Path,
) -> None:
    text = build_arena_creator_request(request=_request(tmp_path), recall=RecallResult())
    assert ARENA_SCENARIO_SCHEMA in text
    assert "DIVERSIFY" in text
    assert "NON-DEGENERATE" in text.upper()
    assert "VERDICT: PASS" in text and "VERDICT: FAIL" in text
    assert "exactly 3" in text  # population_size threaded through


def test_compile_cmd_is_a_sequential_creator_then_reviewer_dag(tmp_path: Path) -> None:
    backend = AskTauArenaCreatorDagBackend(
        ask_run=tmp_path / "run.sh",
        creator_handler="gpt-5.5",
        reviewer_handler="claude-sonnet-5",
    )
    cmd = backend._compile_cmd(_request(tmp_path), "REQ")
    assert cmd[1] == "tau-dag"
    assert "--topology" in cmd and cmd[cmd.index("--topology") + 1] == "sequential"
    assert "--immutable-goal" in cmd  # ask contract requires it
    # creator handler appears BEFORE reviewer handler (sequential order).
    handlers = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--handler"]
    assert handlers == ["gpt-5.5", "claude-sonnet-5"]
    # compile-only by default (no live provider calls).
    assert "--execute" not in cmd


def test_creator_json_and_reviewer_verdicts_parse() -> None:
    creator = 'blah [{"scenario_id":"a","cwe":"CWE-22"},{"scenario_id":"b","cwe":"CWE-89"}] tail'
    parsed = _extract_json_array(creator)
    assert [c["scenario_id"] for c in parsed] == ["a", "b"]
    verdicts = _parse_verdicts("VERDICT: PASS balanced\nnoise\nVERDICT: FAIL degenerate")
    assert verdicts == [True, False]


def test_compile_only_returns_empty_population_not_fabricated(tmp_path: Path) -> None:
    """execute=False must NOT invent arenas; it returns the compiled contract."""

    class _FakeRun:
        def __call__(self, *a, **k):
            raise AssertionError("subprocess should be stubbed in this unit test")

    backend = AskTauArenaCreatorDagBackend(ask_run=tmp_path / "run.sh", execute=False)

    # Stub the subprocess call to return a READY compile bundle.
    import battle_skill.adaptive_arena_creator_dag as mod

    class _Proc:
        returncode = 0
        stdout = '{"status":"READY","run_dir":"/tmp/none"}'
        stderr = ""

    original = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: _Proc()  # type: ignore[assignment]
    try:
        result = backend.create_population(request=_request(tmp_path), recall=RecallResult())
    finally:
        mod.subprocess.run = original
    assert result.items == ()
    assert result.raw["compiled"] is True
