"""Deterministic check: _request_json retries once on 429 with the paid key.

Run: python3 test_paid_fallback.py
"""

import io
import json
import urllib.error
from unittest import mock

import brave_search


def _http_429(url):
    return urllib.error.HTTPError(
        url, 429, "Too Many Requests", hdrs=None,
        fp=io.BytesIO(b'{"error":{"code":"QUOTA_LIMITED"}}'),
    )


def demo():
    calls = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def fake_urlopen(req, timeout=30):
        key = req.headers.get("X-subscription-token")
        calls.append(key)
        if key == "FREE":
            raise _http_429(req.full_url)
        return FakeResp()

    with mock.patch.object(brave_search.urllib.request, "urlopen", fake_urlopen), \
         mock.patch.object(brave_search, "get_api_key", lambda paid=False: "PAID"), \
         mock.patch.object(brave_search.time, "sleep", lambda s: None):
        out = brave_search._request_json("https://x/res", "FREE")

    assert out == {"ok": True}, out
    assert calls == ["FREE", "PAID"], calls

    # Paid key itself exhausted: no infinite retry, error surfaces.
    calls.clear()

    def fake_urlopen_all_429(req, timeout=30):
        calls.append(req.headers.get("X-subscription-token"))
        raise _http_429(req.full_url)

    with mock.patch.object(brave_search.urllib.request, "urlopen", fake_urlopen_all_429), \
         mock.patch.object(brave_search, "get_api_key", lambda paid=False: "PAID"), \
         mock.patch.object(brave_search.time, "sleep", lambda s: None):
        try:
            brave_search._request_json("https://x/res", "FREE")
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "429" in str(exc)

    assert calls == ["FREE", "PAID"], calls
    print("PASS: 429 free->paid fallback fires once, fails closed when paid also 429s")


if __name__ == "__main__":
    demo()
