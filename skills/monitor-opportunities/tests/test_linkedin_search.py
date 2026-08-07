"""Pure-logic tests for LinkedIn advanced-search URL/query construction.

These prove the search-URL builder maps candidate preferences to LinkedIn's own
filter params correctly WITHOUT any browser/surf calls, so the advanced-search
capture is ready and verified the moment surf is stable.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from monitor_opportunities.browser_capture import (
    _LINKEDIN_SENIOR_EXPERIENCE,
    build_linkedin_search_url,
    linkedin_search_queries_from_profile,
)


def _params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_remote_hybrid_maps_to_f_wt_2_3() -> None:
    url = build_linkedin_search_url("document extraction AI", ["remote", "hybrid"])
    p = _params(url)
    assert p["keywords"] == ["document extraction AI"]
    assert p["f_WT"] == ["2,3"]
    assert p["f_E"] == [",".join(_LINKEDIN_SENIOR_EXPERIENCE)]
    assert p["sortBy"] == ["DD"]


def test_onsite_and_location_present_for_buffalo() -> None:
    url = build_linkedin_search_url(
        "AI architect", ["on-site", "remote", "hybrid"], location="Buffalo, NY"
    )
    p = _params(url)
    assert p["f_WT"] == ["1,2,3"]
    assert p["location"] == ["Buffalo, NY"]


def test_unknown_work_type_ignored_no_empty_f_wt() -> None:
    url = build_linkedin_search_url("x", ["teleport"])
    assert "f_WT" not in _params(url)


def test_empty_experience_levels_omits_f_e() -> None:
    url = build_linkedin_search_url("x", ["remote"], experience_levels=[])
    assert "f_E" not in _params(url)


def test_query_set_has_remote_and_buffalo_per_group() -> None:
    profile = {
        "mandates": ["agentic-compliance (flagship: sparta)", "document-extraction (flagships: pdf_oxide)"],
        "workplace_preference": {"preferred": ["remote", "hybrid"]},
        "identity": {"location": "Buffalo, NY"},
    }
    queries = linkedin_search_queries_from_profile(profile)
    labels = [q["label"] for q in queries]
    assert any("remote+hybrid" in l for l in labels)
    assert any("Buffalo, NY on-site OK" in l for l in labels)
    # every url is a well-formed LinkedIn job-search URL
    for q in queries:
        assert q["url"].startswith("https://www.linkedin.com/jobs/search/?")
        assert "keywords=" in q["url"]


def test_empty_mandates_falls_back_not_empty() -> None:
    queries = linkedin_search_queries_from_profile({})
    assert queries  # never silently empty
    for q in queries:
        assert "keywords=" in q["url"]
