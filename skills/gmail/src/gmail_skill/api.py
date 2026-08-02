"""Thin Gmail REST client using httpx with bounded, operation-aware retries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx

from .models import MAX_RESOURCE_ID_LENGTH, OAuthProfile


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
AMBIGUOUS_WRITE_STATUS = {408, 500, 502, 503, 504}


class GmailApiError(RuntimeError):
    """A deterministic Gmail API or transport failure."""

    def __init__(self, message: str, *, code: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AmbiguousWriteError(GmailApiError):
    """A non-idempotent write lost certainty after dispatch."""


@dataclass(frozen=True, slots=True)
class GmailResponse:
    """Validated response wrapper used at the API boundary."""

    status_code: int
    data: dict[str, Any]


def _path_segment(value: str, *, field_name: str) -> str:
    """Validate and percent-encode one opaque Gmail resource ID."""

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > MAX_RESOURCE_ID_LENGTH:
        raise ValueError(f"{field_name} is unexpectedly long")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{field_name} contains a control character")
    return quote(normalized, safe="")


class GmailClient:
    """Stateful authenticated Gmail REST client."""

    def __init__(
        self,
        *,
        access_token: str,
        profile: OAuthProfile,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not access_token:
            raise ValueError("access_token must not be empty")
        self.profile = profile
        self._sleeper = sleeper
        self._client = httpx.Client(
            base_url="https://gmail.googleapis.com/gmail/v1/users/me/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "agent-skills-gmail/0.1.0",
            },
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GmailClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _safe_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Gmail API returned HTTP {response.status_code}"
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message", "Gmail API request failed"))
            return message[:1000]
        return f"Gmail API returned HTTP {response.status_code}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_safe: bool = False,
        expect_json: bool = True,
    ) -> GmailResponse:
        normalized_method = method.upper()
        attempts = 3 if retry_safe else 1
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    normalized_method,
                    path,
                    params=params,
                    json=json_body,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if retry_safe and attempt + 1 < attempts:
                    self._sleeper(0.5 * (2**attempt))
                    continue
                error_type = (
                    GmailApiError
                    if normalized_method in {"GET", "HEAD"}
                    else AmbiguousWriteError
                )
                code = (
                    "transport_error"
                    if error_type is GmailApiError
                    else "transport_ambiguous"
                )
                raise error_type(
                    "Gmail transport failed during "
                    f"{normalized_method} {path}: {type(exc).__name__}",
                    code=code,
                ) from exc

            if (
                response.status_code in RETRYABLE_STATUS
                and retry_safe
                and attempt + 1 < attempts
            ):
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else 0.5 * (2**attempt)
                )
                self._sleeper(min(delay, 10.0))
                continue
            if response.is_error:
                message = self._safe_error(response)
                if (
                    not retry_safe
                    and normalized_method not in {"GET", "HEAD"}
                    and response.status_code in AMBIGUOUS_WRITE_STATUS
                ):
                    raise AmbiguousWriteError(
                        message,
                        code=f"http_{response.status_code}_ambiguous",
                        status_code=response.status_code,
                    )
                raise GmailApiError(
                    message,
                    code=f"http_{response.status_code}",
                    status_code=response.status_code,
                )
            if not expect_json or response.status_code == 204 or not response.content:
                return GmailResponse(status_code=response.status_code, data={})
            try:
                data = response.json()
            except ValueError as exc:
                raise GmailApiError(
                    "Gmail API returned invalid JSON",
                    code="invalid_json",
                    status_code=response.status_code,
                ) from exc
            if not isinstance(data, dict):
                raise GmailApiError(
                    "Gmail API returned a non-object JSON body",
                    code="invalid_shape",
                )
            return GmailResponse(status_code=response.status_code, data=data)
        raise GmailApiError("retry loop exhausted", code="retry_exhausted")

    def get_profile(self) -> dict[str, Any]:
        return self._request("GET", "profile", retry_safe=True).data

    def list_messages(
        self,
        *,
        query: str = "",
        label_ids: list[str] | None = None,
        max_results: int = 10,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        if not 1 <= max_results <= 500:
            raise ValueError("max_results must be between 1 and 500")
        params: dict[str, Any] = {
            "maxResults": max_results,
            "includeSpamTrash": str(include_spam_trash).lower(),
        }
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = label_ids
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", "messages", params=params, retry_safe=True).data

    def get_message(self, message_id: str, *, format_: str = "FULL") -> dict[str, Any]:
        encoded_id = _path_segment(message_id, field_name="message ID")
        return self._request(
            "GET",
            f"messages/{encoded_id}",
            params={"format": format_},
            retry_safe=True,
        ).data

    def get_thread(self, thread_id: str, *, format_: str = "FULL") -> dict[str, Any]:
        encoded_id = _path_segment(thread_id, field_name="thread ID")
        return self._request(
            "GET",
            f"threads/{encoded_id}",
            params={"format": format_},
            retry_safe=True,
        ).data

    def list_labels(self) -> dict[str, Any]:
        return self._request("GET", "labels", retry_safe=True).data

    def list_drafts(
        self,
        *,
        query: str = "",
        max_results: int = 10,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= max_results <= 500:
            raise ValueError("max_results must be between 1 and 500")
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", "drafts", params=params, retry_safe=True).data

    def get_draft(self, draft_id: str, *, format_: str = "FULL") -> dict[str, Any]:
        encoded_id = _path_segment(draft_id, field_name="draft ID")
        return self._request(
            "GET",
            f"drafts/{encoded_id}",
            params={"format": format_},
            retry_safe=True,
        ).data

    def get_attachment(self, message_id: str, attachment_id: str) -> dict[str, Any]:
        encoded_message_id = _path_segment(message_id, field_name="message ID")
        encoded_attachment_id = _path_segment(
            attachment_id,
            field_name="attachment ID",
        )
        return self._request(
            "GET",
            f"messages/{encoded_message_id}/attachments/{encoded_attachment_id}",
            retry_safe=True,
        ).data

    def batch_modify(
        self,
        message_ids: list[str],
        *,
        add_label_ids: list[str],
        remove_label_ids: list[str],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "messages/batchModify",
            json_body={
                "ids": message_ids,
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids,
            },
            retry_safe=True,
        ).data

    def trash_message(self, message_id: str) -> dict[str, Any]:
        encoded_id = _path_segment(message_id, field_name="message ID")
        return self._request(
            "POST",
            f"messages/{encoded_id}/trash",
            json_body={},
            retry_safe=True,
        ).data

    def untrash_message(self, message_id: str) -> dict[str, Any]:
        encoded_id = _path_segment(message_id, field_name="message ID")
        return self._request(
            "POST",
            f"messages/{encoded_id}/untrash",
            json_body={},
            retry_safe=True,
        ).data

    def create_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "labels",
            json_body=payload,
            retry_safe=False,
        ).data

    def create_draft(self, *, raw: str, thread_id: str | None = None) -> dict[str, Any]:
        message: dict[str, Any] = {"raw": raw}
        if thread_id:
            message["threadId"] = thread_id
        return self._request(
            "POST",
            "drafts",
            json_body={"message": message},
            retry_safe=False,
        ).data

    def send_message(self, *, raw: str, thread_id: str | None = None) -> dict[str, Any]:
        message: dict[str, Any] = {"raw": raw}
        if thread_id:
            message["threadId"] = thread_id
        return self._request(
            "POST",
            "messages/send",
            json_body=message,
            retry_safe=False,
        ).data

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "drafts/send",
            json_body={"id": draft_id},
            retry_safe=False,
        ).data
