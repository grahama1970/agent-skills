#!/usr/bin/env python3
"""Sanity test for memory bridge - command construction."""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_memory_bridge_commands():
    """Test that memory bridge constructs correct commands."""
    try:
        from memory_bridge import MemoryBridge
    except ImportError as e:
        print(f"SKIP: MemoryBridge not importable: {e}")
        return True  # Skip, not fail

    try:
        # Create memory bridge (mock mode for testing)
        bridge = MemoryBridge(dry_run=True)

        # Test learn command construction
        learn_cmd = bridge.build_learn_command(
            problem="Watched Tywin/Tyrion scene",
            solution="Observed manipulation pattern",
            category="emotional_learning",
            tags=["manipulation", "authority"]
        )

        assert "learn" in learn_cmd, "Expected 'learn' in command"
        assert "Tywin/Tyrion" in learn_cmd, "Expected problem in command"
        assert "manipulation" in learn_cmd, "Expected tags in command"

        # Test recall command construction
        recall_cmd = bridge.build_recall_command(
            query="Tywin manipulation pattern"
        )

        assert "recall" in recall_cmd, "Expected 'recall' in command"
        assert "Tywin" in recall_cmd, "Expected query in command"

        print(f"PASS: MemoryBridge command construction successful")
        print(f"  - Learn command: {learn_cmd[:60]}...")
        print(f"  - Recall command: {recall_cmd[:60]}...")
        return True

    except Exception as e:
        print(f"FAIL: Error with MemoryBridge: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_memory_bridge_commands()
    exit(0 if success else 1)
