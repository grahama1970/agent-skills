"""Battle skill package.

Import concrete modules such as ``battle_skill.cli`` or
``battle_skill.battle_fixture`` for behavior. The package initializer stays thin
so optional downstream skills are not imported during basic package discovery.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
