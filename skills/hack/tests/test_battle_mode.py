import unittest
from pathlib import Path
import sys
import tempfile
import subprocess

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

    def test_battle_patch_writer_resolves_sibling_code_runner(self) -> None:
        skills_dir = Path(__file__).resolve().parents[2]
        battle_dir = skills_dir / "battle"
        if str(battle_dir) not in sys.path:
            sys.path.insert(0, str(battle_dir))

        from patch_writer import _resolve_code_runner_run

        run_sh = _resolve_code_runner_run(Path("/tmp/nonexistent-battle-target"))

        self.assertIsNotNone(run_sh)
        self.assertEqual(run_sh, skills_dir / "code-runner" / "run.sh")

    def test_battle_patch_writer_initializes_nested_workspace_as_repo_root(self) -> None:
        skills_dir = Path(__file__).resolve().parents[2]
        battle_dir = skills_dir / "battle"
        if str(battle_dir) not in sys.path:
            sys.path.insert(0, str(battle_dir))

        from patch_writer import _ensure_git_repo

        with tempfile.TemporaryDirectory(dir=str(battle_dir / "worktrees")) as tmp:
            workspace = Path(tmp)
            (workspace / "app.py").write_text("print('ok')\n")
            _ensure_git_repo(workspace)
            root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        self.assertEqual(Path(root), workspace)


if __name__ == "__main__":
    unittest.main()
