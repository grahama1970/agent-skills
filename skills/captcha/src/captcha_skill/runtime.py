"""Public runtime facade for the CAPTCHA skill.

Implementation is split by concern to keep every Python module below the
repository's 800-line hygiene limit.
"""

from .execution import execute_evaluation
from .verification import verify_run
from .layout import (
    ask_skill_path,
    build_recap_argv,
    default_recap_python,
    repository_root,
    skill_root,
    status_report,
    surf_run_path,
    validate_recap_runtime,
    validate_storage_path,
)
from .planning import build_ask_dag, build_evaluation_plan, compute_plan_hash
from .preflight import (
    build_recap_environment,
    collect_surf_capabilities,
    preflight_model_endpoint,
    preflight_surf_target,
    preflight_target,
)

__all__ = [
    "ask_skill_path",
    "build_ask_dag",
    "build_evaluation_plan",
    "build_recap_argv",
    "build_recap_environment",
    "collect_surf_capabilities",
    "compute_plan_hash",
    "default_recap_python",
    "execute_evaluation",
    "preflight_model_endpoint",
    "preflight_surf_target",
    "preflight_target",
    "repository_root",
    "skill_root",
    "status_report",
    "surf_run_path",
    "validate_recap_runtime",
    "validate_storage_path",
    "verify_run",
]
