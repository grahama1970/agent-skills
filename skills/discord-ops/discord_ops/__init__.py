"""
Discord Operations Skill - Modular Package

TOS-compliant notification monitor for YOUR Discord server.
Watches for security content forwarded by researchers, then pushes
to paper-writer/dogpile via webhooks and persists to graph-memory.

Architecture:
  External Sources -> Your Discord Server -> ClawDBot Monitor -> Webhooks -> Consumers
                      (you are admin)       (keyword watch)     + Memory

This skill does NOT scrape external servers (TOS violation).
Instead, it monitors channels where your bot has legitimate access.
"""

__version__ = "0.3.0"

# Lazy imports to avoid circular dependency issues
# Users should import from submodules directly:
#   from discord_ops.config import SKILL_DIR
#   from discord_ops.keyword_matcher import KeywordMatch
#   from discord_ops.utils import load_config
#   from discord_ops.graph_persistence import persist_match_to_memory
#   from discord_ops.webhook_monitor import run_monitor
