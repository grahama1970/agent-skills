"""CLI package for RunPod operations management."""

from runpod_ops_fixed.cli.main import app, RunPodCLI  # noqa: F401

try:
    from runpod_ops_fixed.cli.unified_cli import unified_app, main  # noqa: F401
    from runpod_ops_fixed.cli.granger_slash_mcp_mixin import add_slash_mcp_commands as granger_add_slash_mcp_commands  # noqa: F401
    from runpod_ops_fixed.cli.slash_mcp_mixin import add_slash_mcp_commands  # noqa: F401
except ImportError:
    unified_app = main = add_slash_mcp_commands = granger_add_slash_mcp_commands = None