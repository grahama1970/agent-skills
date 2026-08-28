"""ask composes /triage-error: the aggregator canonicalizes any provider signal
(browser AND api) via the shared classifier, at the recovery boundary."""
from __future__ import annotations
from ask import tau_dag as td


def test_ask_classifies_scillm_route_error() -> None:
    r = td._triage_classify("scillm_provider_route_failed 404 /v4/v1/chat/completions", None)
    assert r["code"] == "scillm_api_base_double_version_segment"
    assert r["ambiguous"] is False


def test_ask_classifies_surf_attach_error() -> None:
    r = td._triage_classify("attach_file_preflight_failed: zip contains 9 files; maximum is 5", None)
    assert r["code"] == "webgpt_attachment_bundle_rejected"


def test_ask_novel_signal_is_ambiguous_not_forced() -> None:
    r = td._triage_classify("some brand new gremlin 0xabcdef", None)
    assert r["ambiguous"] is True
