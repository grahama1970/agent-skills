"""HTTP boundary tests for retry, path encoding, and ambiguous writes."""

from __future__ import annotations

import httpx
import pytest

from gmail_skill.api import AmbiguousWriteError, GmailClient
from gmail_skill.models import OAuthProfile


def test_get_retries_bounded_transient_status() -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "temporary"}})
        return httpx.Response(200, json={"emailAddress": "owner@example.com"})

    client = GmailClient(
        access_token="test-token",
        profile=OAuthProfile.READONLY,
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    )
    try:
        result = client.get_profile()
    finally:
        client.close()
    assert result["emailAddress"] == "owner@example.com"
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert calls[0].endswith("/gmail/v1/users/me/profile")


def test_non_idempotent_send_is_not_retried_after_timeout() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("lost response", request=request)

    client = GmailClient(
        access_token="test-token",
        profile=OAuthProfile.COMPOSE,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    try:
        with pytest.raises(AmbiguousWriteError, match="transport failed"):
            client.send_message(raw="abc")
    finally:
        client.close()
    assert calls == 1


def test_non_idempotent_send_treats_server_error_as_ambiguous() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "unknown outcome"}})

    client = GmailClient(
        access_token="test-token",
        profile=OAuthProfile.COMPOSE,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )
    try:
        with pytest.raises(AmbiguousWriteError) as captured:
            client.send_message(raw="abc")
    finally:
        client.close()
    assert captured.value.code == "http_503_ambiguous"
    assert calls == 1


def test_opaque_resource_ids_are_percent_encoded_in_paths() -> None:
    raw_paths: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw_paths.append(request.url.raw_path)
        return httpx.Response(200, json={"id": "abc/def"})

    client = GmailClient(
        access_token="test-token",
        profile=OAuthProfile.READONLY,
        transport=httpx.MockTransport(handler),
    )
    try:
        client.get_message("abc/def")
    finally:
        client.close()
    assert raw_paths == [b"/gmail/v1/users/me/messages/abc%2Fdef?format=FULL"]
