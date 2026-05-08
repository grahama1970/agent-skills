import unittest
from pathlib import Path

from hack.battle_mode import build_battle_command_args


class BattleModeTests(unittest.TestCase):
    def test_hack_battle_delegates_to_sibling_battle_skill(self) -> None:
        args = build_battle_command_args(
            target="/tmp/repo",
            rounds=100,
            overnight=False,
            mode="docker",
            docker_image=None,
        )

        self.assertEqual(Path(args[0]).name, "run.sh")
        self.assertIn("/battle/run.sh", args[0])
        self.assertEqual(args[1:4], ["battle", "/tmp/repo", "--mode"])
        self.assertIn("--rounds", args)
        self.assertIn("100", args)

    def test_hack_battle_supports_docker_image_and_overnight(self) -> None:
        args = build_battle_command_args(
            target=None,
            rounds=100,
            overnight=True,
            mode=None,
            docker_image="nginx:latest",
        )

        self.assertIn("--docker-image", args)
        self.assertIn("nginx:latest", args)
        self.assertIn("--overnight", args)
        self.assertNotIn("--rounds", args)


if __name__ == "__main__":
    unittest.main()
