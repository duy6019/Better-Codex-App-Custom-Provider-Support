#!/usr/bin/env python3
"""Guided entry point for the ChatGPT custom-provider tools."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parent
ACTION_SCRIPTS = {
    "patch": ("Patch the ChatGPT/Codex desktop app", "patch_chatgpt_providers.py"),
    "catalog": ("Refresh the bundled Codex model catalog", "sync_model_catalog.py"),
    "provider": ("Add or update a custom provider", "setup_custom_provider.py"),
}
ALL_ACTIONS = ("patch", "catalog", "provider")
MENU_CHOICES = {
    "1": "patch",
    "2": "catalog",
    "3": "provider",
    "4": "all",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ChatGPT custom-provider setup tools.",
        epilog=(
            "Run without ACTION to open the guided menu. On Windows, run the "
            "patch action from an elevated PowerShell session."
        ),
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=(*ACTION_SCRIPTS, "all"),
        metavar="ACTION",
        help="one of: patch, catalog, provider, all",
    )
    return parser.parse_args(argv)


def choose_action(
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> str | None:
    output_func("ChatGPT custom-provider setup")
    output_func("  1. Patch the desktop app")
    output_func("  2. Refresh the bundled Codex model catalog")
    output_func("  3. Add or update a custom provider")
    output_func("  4. Run all steps (patch, catalog, provider)")
    output_func("")
    output_func("Choose a number, or press Enter to exit without making changes.")

    while True:
        try:
            choice = input_func("Choice [1-4]: ").strip()
        except (EOFError, KeyboardInterrupt):
            output_func("No action selected; no changes were made.")
            return None
        if not choice:
            output_func("No action selected; no changes were made.")
            return None
        action = MENU_CHOICES.get(choice)
        if action:
            return action
        output_func("Invalid choice. Enter a number from 1 to 4.")


def actions_for(action: str) -> tuple[str, ...]:
    if action == "all":
        return ALL_ACTIONS
    if action in ACTION_SCRIPTS:
        return (action,)
    raise ValueError(f"Unknown setup action: {action}")


def run_actions(
    action: str,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
    output_func: Callable[[str], None] = print,
) -> int:
    for current_action in actions_for(action):
        description, filename = ACTION_SCRIPTS[current_action]
        script = ROOT / filename
        output_func(f"\n==> {description}")
        try:
            result = command_runner([sys.executable, str(script)])
        except OSError as exc:
            output_func(f"Could not start {filename}: {exc}")
            return 1
        if result.returncode:
            output_func(f"{filename} failed with exit code {result.returncode}; stopping.")
            return result.returncode

    output_func("\nSetup completed. Restart ChatGPT/Codex before using the changes.")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    command_runner: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
) -> int:
    args = parse_args(argv)
    action = args.action or choose_action(input_func=input_func, output_func=output_func)
    if action is None:
        return 0
    return run_actions(
        action,
        command_runner=command_runner,
        output_func=output_func,
    )


if __name__ == "__main__":
    raise SystemExit(main())
