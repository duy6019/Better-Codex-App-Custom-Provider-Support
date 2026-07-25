from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

import setup


class SetupTests(unittest.TestCase):
    def test_no_argument_opens_menu_and_runs_selected_action(self):
        output: list[str] = []
        commands: list[list[str]] = []

        result = setup.main(
            [],
            input_func=lambda _prompt: "2",
            output_func=output.append,
            command_runner=lambda command: (
                commands.append(command) or subprocess.CompletedProcess(command, 0)
            ),
        )

        self.assertEqual(result, 0)
        self.assertIn("ChatGPT custom-provider setup", output)
        self.assertIn("  4. Run all steps (patch, catalog, provider)", output)
        self.assertEqual(commands, [[setup.sys.executable, str(setup.ROOT / "sync_model_catalog.py")]])

    def test_all_runs_scripts_in_documented_order(self):
        commands: list[list[str]] = []

        result = setup.run_actions(
            "all",
            output_func=lambda _line: None,
            command_runner=lambda command: (
                commands.append(command) or subprocess.CompletedProcess(command, 0)
            ),
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            [Path(command[1]).name for command in commands],
            [
                "patch_chatgpt_providers.py",
                "sync_model_catalog.py",
                "setup_custom_provider.py",
            ],
        )

    def test_all_stops_after_the_first_failed_step(self):
        output: list[str] = []
        commands: list[list[str]] = []

        def runner(command: list[str]) -> subprocess.CompletedProcess[object]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 9)

        result = setup.run_actions("all", command_runner=runner, output_func=output.append)

        self.assertEqual(result, 9)
        self.assertEqual(len(commands), 1)
        self.assertIn("stopping", output[-1])

    def test_empty_menu_choice_makes_no_changes(self):
        output: list[str] = []

        result = setup.main(
            [],
            input_func=lambda _prompt: "",
            output_func=output.append,
            command_runner=lambda _command: self.fail("command should not run"),
        )

        self.assertEqual(result, 0)
        self.assertEqual(output[-1], "No action selected; no changes were made.")

    def test_named_actions_are_accepted(self):
        self.assertEqual(setup.parse_args(["patch"]).action, "patch")
        self.assertEqual(setup.parse_args(["catalog"]).action, "catalog")
        self.assertEqual(setup.parse_args(["provider"]).action, "provider")
        self.assertEqual(setup.parse_args(["all"]).action, "all")


if __name__ == "__main__":
    unittest.main()
