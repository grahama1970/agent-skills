"""triage-error classification: canonical match + ambiguous minting."""
from __future__ import annotations
import triage_error as t


def test_known_signal_maps_to_canonical_code() -> None:
    r = t.classify("attach_file_preflight_failed: zip contains 9 files; maximum is 5", "surf")
    assert r["code"] == "webgpt_attachment_bundle_rejected"
    assert r["ambiguous"] is False
    assert "open-bind" in r["not_this"] or "tab binding" in r["not_this"]


def test_scillm_route_signal_maps_to_canonical() -> None:
    r = t.classify("404 path /v4/v1/chat/completions", "scillm")
    assert r["code"] == "scillm_api_base_double_version_segment"
    assert r["recoverable"] is True


def test_ambiguous_signal_mints_deterministic_code() -> None:
    a = t.classify("novel gizmo exploded 0xdeadbeef", "tau")
    b = t.classify("novel gizmo exploded 0xdeadbeef", "tau")
    assert a["ambiguous"] is True
    assert a["code"] == b["code"]  # deterministic
    assert a["code"].startswith("tau_unclassified_")


def test_layer_filter_prevents_cross_layer_false_match() -> None:
    # The zip-limit tokens belong to surf; asking as scillm must not match it.
    r = t.classify("zip contains 9 files; maximum is 5", "scillm")
    assert r["ambiguous"] is True
