#!/usr/bin/env python3
"""Simplified error tracking and logging for Dogpile.

Provides structured error logging, rate limit tracking, and session management.
Replaces the previous 425-line singleton with ~120 lines of module-level state.
"""
import json
import os
import sys
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorType(str, Enum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    AUTH_FAILURE = "auth_failure"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    API_ERROR = "api_error"
    CONFIG_ERROR = "config_error"
    DEPENDENCY_MISSING = "dependency_missing"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Module-level state (replaces singleton)
# ---------------------------------------------------------------------------
_LOG_DIR = Path(__file__).parent
_ERROR_LOG = _LOG_DIR / "dogpile_errors.json"
_HUMAN_LOG = _LOG_DIR / "dogpile.log"

_session: Optional[Dict[str, Any]] = None
_errors: List[Dict[str, Any]] = []
_rate_limits: Dict[str, Dict[str, Any]] = {}


def _log_human(msg: str):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_HUMAN_LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception as e:
        logger.error("file write failed: {}", e)


def _save_session():
    if not _session:
        return
    try:
        sessions = []
        if _ERROR_LOG.exists():
            try:
                sessions = json.loads(_ERROR_LOG.read_text()).get("sessions", [])
            except Exception as e:
                logger.error("JSON parse failed: {}", e)
        sessions.append(_session)
        sessions = sessions[-50:]
        tmp = _ERROR_LOG.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_updated": datetime.now().isoformat(), "sessions": sessions}, indent=2))
        os.replace(tmp, _ERROR_LOG)
    except Exception as e:
        logger.warning("formatting failed: {}", e)


# ---------------------------------------------------------------------------
# Public API (same signatures as before)
# ---------------------------------------------------------------------------

def start_session(query: str) -> str:
    global _session
    sid = f"dogpile_{int(time.time())}"
    _session = {
        "session_id": sid, "query": query, "started_at": datetime.now().isoformat(),
        "status": "running", "succeeded": [], "failed": [], "errors": [], "rate_limits_hit": {},
    }
    _log_human(f"=== Session {sid} started: {query[:60]} ===")
    return sid


def end_session(status: str = "completed"):
    global _session
    if _session:
        _session["ended_at"] = datetime.now().isoformat()
        _session["status"] = status
        _session["error_count"] = len(_session.get("errors", []))
        _save_session()
        _log_human(f"=== Session {_session['session_id']} {status} ===")
        _session = None


def log_error(
    provider: str,
    error_type: ErrorType,
    message: str,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    details: Optional[Dict[str, Any]] = None,
    http_status: Optional[int] = None,
    retry_after: Optional[float] = None,
    traceback: Optional[str] = None,
):
    event = {
        "timestamp": datetime.now().isoformat(), "provider": provider,
        "error_type": error_type.value if isinstance(error_type, ErrorType) else str(error_type),
        "severity": severity.value if isinstance(severity, ErrorSeverity) else str(severity),
        "message": message, "details": details, "http_status": http_status,
        "retry_after_seconds": retry_after,
    }
    _errors.append(event)
    if _session:
        _session["errors"].append(event)
        if provider not in _session["failed"]:
            _session["failed"].append(provider)
    _log_human(f"[{severity.value.upper()}] [{provider}] {error_type.value}: {message}")
    try:
        sys.stderr.write(f"[DOGPILE-ERROR] [{provider}] {error_type.value}: {message}\n")
        sys.stderr.flush()
    except Exception as e:
        logger.error("file write failed: {}", e)
    return event


def log_rate_limit(provider: str, retry_after: Optional[float] = None, **kwargs):
    _rate_limits.setdefault(provider, {"total_hits": 0, "backoff_multiplier": 1.0})
    state = _rate_limits[provider]
    state["total_hits"] += 1
    state["last_hit"] = datetime.now().isoformat()
    state["backoff_multiplier"] = min(state["backoff_multiplier"] * 1.5, 10.0)
    if _session:
        _session["rate_limits_hit"][provider] = _session["rate_limits_hit"].get(provider, 0) + 1
    wait_msg = f"waiting {retry_after:.0f}s" if retry_after else "backoff active"
    log_error(provider, ErrorType.RATE_LIMIT, f"Rate limited ({wait_msg})",
              severity=ErrorSeverity.WARNING, http_status=kwargs.get("http_status", 429),
              retry_after=retry_after, details=kwargs.get("details"))


def log_success(provider: str, message: str = ""):
    if _session:
        if provider not in _session["succeeded"]:
            _session["succeeded"].append(provider)
        if provider in _session["failed"]:
            _session["failed"].remove(provider)
    if provider in _rate_limits:
        _rate_limits[provider]["backoff_multiplier"] = 1.0
    _log_human(f"[OK] [{provider}] {message or 'completed'}")


def get_backoff_time(provider: str, base: float = 30.0) -> float:
    state = _rate_limits.get(provider)
    if not state:
        return base
    return base * state.get("backoff_multiplier", 1.0)


def get_error_summary() -> Dict[str, Any]:
    session_summary = None
    if _session:
        session_summary = {
            "session_id": _session["session_id"], "query": _session["query"][:50],
            "status": _session["status"], "succeeded": _session["succeeded"],
            "failed": _session["failed"], "error_count": len(_session["errors"]),
            "rate_limits_hit": _session["rate_limits_hit"],
        }
    return {
        "current_session": session_summary,
        "recent_errors": _errors[-10:],
        "rate_limits": {p: {"total_hits": s["total_hits"], "last_hit": s.get("last_hit"),
                            "backoff_multiplier": s["backoff_multiplier"]}
                        for p, s in _rate_limits.items()},
        "total_errors": len(_errors),
    }


class _TrackerCompat:
    """Compatibility shim exposing both file paths (for cli.py errors command)
    and logging methods (for utils.py log_status)."""
    error_log = _ERROR_LOG
    human_log = _HUMAN_LOG
    log_dir = _LOG_DIR

    # Delegate logging to module-level functions so callers can use
    # tracker.log_error(...) / tracker.log_rate_limit(...) / tracker.log_success(...)
    log_error = staticmethod(log_error)
    log_rate_limit = staticmethod(log_rate_limit)
    log_success = staticmethod(log_success)

_compat = _TrackerCompat()

def get_tracker():
    return _compat
