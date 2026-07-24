#!/usr/bin/env python3
"""Rebuild the Codex custom model catalog from the bundled CLI catalog."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Sequence

from codex_config import (
    ConfigError,
    atomic_write_json,
    atomic_write_text,
    codex_home,
    read_text,
    update_root_setting,
)


SyncError = ConfigError


def validate_bundled_catalog(catalog: Any) -> list[dict[str, Any]]:
    if not isinstance(catalog, dict):
        raise SyncError("The bundled Codex catalog must be a JSON object")
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        raise SyncError("The bundled Codex catalog must contain a non-empty models array")

    slugs: set[str] = set()
    validated: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            raise SyncError("Every bundled model must be a JSON object")
        slug = model.get("slug")
        display_name = model.get("display_name")
        if not isinstance(slug, str) or not slug.strip():
            raise SyncError("Every bundled model needs a non-empty slug")
        if not isinstance(display_name, str) or not display_name.strip():
            raise SyncError(f"Bundled model '{slug}' needs a non-empty display_name")
        if slug in slugs:
            raise SyncError(f"The bundled catalog has duplicate model slug '{slug}'")
        slugs.add(slug)
        validated.append(model)
    return validated


def build_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    models = validate_bundled_catalog(catalog)
    generated_catalog = copy.deepcopy(catalog)
    generated_catalog["models"] = copy.deepcopy(models)
    return generated_catalog


def update_codex_toml(contents: str, catalog_path: Path) -> str:
    return update_root_setting(contents, "model_catalog_json", catalog_path.as_posix())


def read_bundled_catalog(
    codex_bin: str,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = [codex_bin, "debug", "models", "--bundled"]
    try:
        result = command_runner(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SyncError(f"Cannot find Codex CLI executable '{codex_bin}'") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        detail = f": {output}" if output else ""
        raise SyncError(f"Codex CLI could not read its bundled model catalog{detail}") from exc

    try:
        return json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SyncError("Codex CLI returned invalid JSON for its bundled model catalog") from exc


def synchronize(
    codex_bin: str,
    catalog_path: Path,
    toml_path: Path,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    bundled_catalog = read_bundled_catalog(codex_bin, command_runner=command_runner)
    catalog = build_catalog(bundled_catalog)
    updated_toml = update_codex_toml(read_text(toml_path), catalog_path)

    atomic_write_json(catalog_path, catalog)
    atomic_write_text(toml_path, updated_toml)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    home = codex_home()
    parser = argparse.ArgumentParser(
        description="Rebuild the Codex custom model catalog from the bundled CLI catalog."
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable (default: codex)")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=home / "model-catalogs" / "custom.json",
        help="Generated model catalog path",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=home / "config.toml",
        help="Codex TOML configuration path to update",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        catalog_path = args.catalog.expanduser().resolve()
        toml_path = args.config.expanduser().resolve()
        synchronize(args.codex_bin, catalog_path, toml_path)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Updated model catalog: {catalog_path}")
    print(f"Updated Codex configuration: {toml_path}")
    print("Restart ChatGPT/Codex to load the updated model catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
