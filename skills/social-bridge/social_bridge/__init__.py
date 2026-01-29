"""
Social Bridge - Security Content Aggregator

A modular social media aggregator for security content.

Modules:
- config: Constants, paths, and configuration
- utils: Common utilities (retry logic, rate limiting, data classes)
- telegram: Telegram channel monitoring via Telethon
- twitter: X/Twitter monitoring via surf browser automation
- discord_webhook: Discord webhook delivery
- graph_storage: Graph memory persistence
- cli_commands: CLI command implementations
"""

__version__ = "0.2.0"

# Re-export commonly used items for convenience
# Note: These are imported explicitly to avoid circular dependencies

__all__ = [
    "__version__",
]
