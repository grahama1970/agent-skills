"""OAuth profile management for the Gmail skill.

OAuth tokens are stored outside the repository with mode 0600. Google imports
are intentionally lazy so local schema and plan tests can run before optional
OAuth dependencies are installed by ``uv``.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .models import OAuthProfile, PROFILE_SCOPES


class GmailAuthError(RuntimeError):
    """Raised when OAuth material is absent, invalid, or under-scoped."""


def state_root() -> Path:
    """Return the private runtime state root outside the repository."""

    return Path.home() / ".local" / "state" / "agent-skills" / "gmail"


def token_path(profile: OAuthProfile) -> Path:
    """Return the token path for one isolated OAuth profile."""

    return state_root() / "oauth" / f"{profile.value}.json"


def ensure_private_directory(path: Path) -> None:
    """Create a directory and constrain it to the current user."""

    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def atomic_private_write(path: Path, text: str) -> None:
    """Atomically write UTF-8 text with owner-only permissions."""

    ensure_private_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_google_types() -> tuple[Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GmailAuthError(
            "Google OAuth dependencies are missing. Run through ./run.sh so uv installs "
            "google-auth and google-auth-oauthlib."
        ) from exc
    return Request, Credentials, InstalledAppFlow


def login(
    profile: OAuthProfile,
    client_secret: Path,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> Path:
    """Run installed-app OAuth consent and persist one scoped token."""

    if not client_secret.is_file():
        raise GmailAuthError(f"OAuth client-secret file not found: {client_secret}")
    if client_secret.stat().st_size > 1_000_000:
        raise GmailAuthError("OAuth client-secret file is unexpectedly large")
    client_mode = stat.S_IMODE(client_secret.stat().st_mode)
    if client_mode & 0o077:
        raise GmailAuthError(
            "OAuth client-secret permissions are too broad "
            f"({oct(client_mode)}): chmod 600 {client_secret}"
        )
    try:
        client_payload = json.loads(client_secret.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GmailAuthError("OAuth client-secret file is not valid JSON") from exc
    if not isinstance(client_payload, dict) or "installed" not in client_payload:
        raise GmailAuthError(
            "OAuth client-secret JSON must contain a Desktop app installed block"
        )

    _, _, InstalledAppFlow = _load_google_types()
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret),
            scopes=list(PROFILE_SCOPES[profile]),
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=port,
            open_browser=open_browser,
            access_type="offline",
            prompt="consent",
            authorization_prompt_message=(
                "Open this URL in your normal browser to authorize the Gmail skill:\n{url}"
            ),
            success_message="Gmail authorization completed. You may close this tab.",
        )
    except Exception as exc:
        raise GmailAuthError(
            f"Gmail OAuth consent failed: {type(exc).__name__}: {exc}"
        ) from exc
    output = token_path(profile)
    atomic_private_write(output, credentials.to_json())
    return output


def load_credentials(profile: OAuthProfile) -> Any:
    """Load, scope-check, refresh, and re-persist credentials."""

    Request, Credentials, _ = _load_google_types()
    path = token_path(profile)
    if not path.is_file():
        raise GmailAuthError(
            f"No {profile.value} OAuth token. Run: ./run.sh auth login "
            f"--profile {profile.value} --client-secret /path/to/client_secret.json"
        )

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise GmailAuthError(
            f"OAuth token permissions are too broad ({oct(mode)}): chmod 600 {path}"
        )

    try:
        credentials = Credentials.from_authorized_user_file(
            str(path),
            scopes=list(PROFILE_SCOPES[profile]),
        )
    except Exception as exc:
        raise GmailAuthError(
            f"OAuth token could not be loaded: {type(exc).__name__}: {exc}"
        ) from exc
    if not credentials.has_scopes(list(PROFILE_SCOPES[profile])):
        raise GmailAuthError(
            f"Stored token does not contain required {profile.value} scope; re-authorize it"
        )
    if credentials.expired:
        if not credentials.refresh_token:
            raise GmailAuthError("OAuth token expired and has no refresh token; re-authorize it")
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise GmailAuthError(
                f"OAuth token refresh failed: {type(exc).__name__}: {exc}"
            ) from exc
        atomic_private_write(path, credentials.to_json())
    if not credentials.valid or not credentials.token:
        raise GmailAuthError("OAuth credentials are invalid; re-authorize the profile")
    return credentials


def access_token(profile: OAuthProfile) -> str:
    """Return a current access token without exposing it in status output."""

    credentials = load_credentials(profile)
    return str(credentials.token)


def profile_status(profile: OAuthProfile, *, validate: bool = False) -> dict[str, Any]:
    """Return non-secret local status for one profile."""

    path = token_path(profile)
    result: dict[str, Any] = {
        "profile": profile.value,
        "required_scopes": list(PROFILE_SCOPES[profile]),
        "token_path": str(path),
        "exists": path.is_file(),
        "permissions": None,
        "validated": False,
        "valid": None,
        "error": None,
    }
    if not path.is_file():
        return result
    result["permissions"] = oct(stat.S_IMODE(path.stat().st_mode))
    if validate:
        result["validated"] = True
        try:
            credentials = load_credentials(profile)
            result["valid"] = bool(credentials.valid)
        except GmailAuthError as exc:
            result["valid"] = False
            result["error"] = str(exc)
    return result


def safe_token_metadata(profile: OAuthProfile) -> dict[str, Any]:
    """Read non-secret token metadata without returning tokens or client secrets."""

    path = token_path(profile)
    if not path.is_file():
        raise GmailAuthError(f"No token file for {profile.value}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GmailAuthError("OAuth token file is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise GmailAuthError("OAuth token file must contain a JSON object")
    return {
        "profile": profile.value,
        "scopes": raw.get("scopes", []),
        "token_uri": raw.get("token_uri"),
        "expiry": raw.get("expiry"),
        "has_refresh_token": bool(raw.get("refresh_token")),
    }
