"""Environment sanitising for sibling-skill subprocesses.

Sibling runners (`ask/run.sh`, `memory/run.sh`, ...) invoke `uv`, which honours
`UV_PROJECT_ENVIRONMENT`. When the Live Evidence server is itself started with
that variable set, every runner it spawns inherits it and rebuilds *the
server's own virtualenv* mid-request.

Observed 2026-08-17 on a live run: the Ask lane reported
"Removed virtual environment at: .../server-venv" as its detail, the Memory
lane failed with FileNotFoundError, and an unrelated httpx client blew up in
`ssl.load_verify_locations` because the CA bundle disappeared underneath the
running process. All three were the same cause.

`VIRTUAL_ENV` is stripped for the same reason; `ask/run.sh` and
`agentic-evals/run.sh` already unset it defensively at their own entry points.
"""

from __future__ import annotations

import os

# Variables that let a child `uv` invocation retarget or rebuild the parent's
# environment. Removing them makes each runner resolve its own project venv.
_UNSAFE_INHERITED = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment safe to hand to a sibling-skill subprocess."""

    env = {key: value for key, value in os.environ.items() if key not in _UNSAFE_INHERITED}
    if extra:
        env.update(extra)
    return env
