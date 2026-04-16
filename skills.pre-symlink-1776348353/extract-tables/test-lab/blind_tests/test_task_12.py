"""Blind adversarial tests for Task 12: Strategy router."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")
COLUMN_SPAN_PDF = os.path.join(FIXTURE_DIR, "column_span_2.pdf")


@pytest.fixture(scope="module")
def router():
    try:
        from strategy_router import StrategyRouter
        return StrategyRouter()
    except ImportError:
        try:
            from strategy_router import pick_strategy, route_strategy
            return type("Router", (), {
                "pick_strategy": staticmethod(pick_strategy if callable(pick_strategy) else lambda *a: pick_strategy(*a)),
                "route_strategy": staticmethod(route_strategy if callable(route_strategy) else lambda *a: route_strategy(*a)),
            })()
        except ImportError as e:
            pytest.fail(f"Cannot import strategy_router: {e}")


class TestStrategySelection:
    def test_picks_lattice_for_bordered(self, router):
        """foo.pdf has a bordered table - should pick lattice."""
        if hasattr(router, "pick_strategy"):
            strategy = router.pick_strategy(FOO_PDF, 0)
        elif hasattr(router, "route_strategy"):
            strategy = router.route_strategy(FOO_PDF, 0)
        else:
            pytest.fail("Router must have pick_strategy or route_strategy method")

        assert strategy is not None, "Strategy should not be None"
        strategy_str = str(strategy).lower()
        assert "lattice" in strategy_str, (
            f"foo.pdf (bordered) should route to lattice, got: {strategy}"
        )

    def test_picks_stream_for_borderless(self, router):
        """column_span_2.pdf is borderless - should pick stream."""
        if hasattr(router, "pick_strategy"):
            strategy = router.pick_strategy(COLUMN_SPAN_PDF, 0)
        elif hasattr(router, "route_strategy"):
            strategy = router.route_strategy(COLUMN_SPAN_PDF, 0)
        else:
            pytest.fail("Router must have pick_strategy or route_strategy method")

        assert strategy is not None
        strategy_str = str(strategy).lower()
        assert "stream" in strategy_str or "network" in strategy_str, (
            f"column_span_2.pdf (borderless) should route to stream/network, got: {strategy}"
        )


class TestStrategyHistory:
    def test_returns_valid_strategy_name(self, router):
        if hasattr(router, "pick_strategy"):
            strategy = router.pick_strategy(FOO_PDF, 0)
        elif hasattr(router, "route_strategy"):
            strategy = router.route_strategy(FOO_PDF, 0)
        else:
            pytest.skip("No strategy method available")

        valid = {"lattice", "stream", "network", "hybrid"}
        strategy_str = str(strategy).lower()
        assert any(v in strategy_str for v in valid), (
            f"Strategy '{strategy}' not in valid set: {valid}"
        )
