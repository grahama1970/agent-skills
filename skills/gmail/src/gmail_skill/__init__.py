"""Gmail API control skill for Codex.

The package exposes a machine-first CLI, Gmail REST client, OAuth profile
management, MIME helpers, and two-phase operation plans with auditable receipts.
"""

from .models import OAuthProfile, Operation, OperationPlan, OperationReceipt

__all__ = ["OAuthProfile", "Operation", "OperationPlan", "OperationReceipt"]
__version__ = "0.1.0"
