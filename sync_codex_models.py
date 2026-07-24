#!/usr/bin/env python3
"""Rebuild the Codex catalog and 9router configuration from the bundled CLI catalog."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlparse


DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"


class SyncError(RuntimeError):
    """A safe, expected catalog synchronization failure."""


def codex_home() -> Path:
    configured_home = os.environ.get("CODEX_HOME")
    return Path(configured_home).expanduser() if configured_home else Path.home() / ".codex"


def validate_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SyncError("9router base URL must be an absolute http or https URL")
    return base_url


def prompt_base_url(
    *, input_func: Callable[[str], str] = input, default: str = DEFAULT_BASE_URL
) -> str:
    try:
        answer = input_func(f"9router base URL [{default}]: ")
    except EOFError:
        answer = ""
    return validate_base_url(answer or default)


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


def clone_model(model: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(model)
    clone["slug"] = f"cx/{model['slug']}"
    clone["display_name"] = f"{model['display_name']} (9router)"
    return clone


def provider_routing(clones: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "default_provider": "openai",
        "providers": [
            {
                "id": "openai",
                "label": "ChatGPT / OpenAI",
                "description": "Built-in provider; uses your signed-in ChatGPT account",
            },
            {
                "id": "9router",
                "label": "9router",
                "description": "Custom provider; uses [model_providers.9router] from config.toml",
            },
        ],
        "model_providers": {clone["slug"]: "9router" for clone in clones},
    }


def build_catalog_and_routing(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    models = validate_bundled_catalog(catalog)
    clones = [clone_model(model) for model in models]
    all_slugs = [model["slug"] for model in models + clones]
    if len(set(all_slugs)) != len(all_slugs):
        raise SyncError("The generated catalog would contain duplicate model slugs")
    generated_catalog = copy.deepcopy(catalog)
    generated_catalog["models"] = copy.deepcopy(models) + clones
    return generated_catalog, provider_routing(clones)


def toml_string(value: str) -> str:
    """JSON basic strings use the escaping rules accepted by TOML basic strings."""
    return json.dumps(value, ensure_ascii=False)


def update_root_setting(contents: str, key: str, value: str) -> str:
    table_match = re.search(r"(?m)^\s*\[", contents)
    root_end = table_match.start() if table_match else len(contents)
    root, tables = contents[:root_end], contents[root_end:]
    assignment = f"{key} = {toml_string(value)}\n"
    setting = re.compile(rf"(?m)^{re.escape(key)}\s*=.*(?:\n|$)")
    match = setting.search(root)
    if match:
        root = root[: match.start()] + assignment + root[match.end() :]
    else:
        if root and not root.endswith("\n"):
            root += "\n"
        root += assignment
    return root + tables


def replace_toml_table(contents: str, table: str, body: str) -> str:
    header = f"[{table}]\n"
    replacement = header + body.rstrip("\n") + "\n"
    table_header = re.compile(rf"(?m)^\[{re.escape(table)}\][^\n]*(?:\n|$)")
    match = table_header.search(contents)
    if match:
        next_header = re.search(r"(?m)^\[", contents[match.end() :])
        end = match.end() + next_header.start() if next_header else len(contents)
        return contents[: match.start()] + replacement + contents[end:]

    nested_table = re.search(rf"(?m)^\[{re.escape(table)}\.", contents)
    if nested_table:
        return contents[: nested_table.start()] + replacement + "\n" + contents[nested_table.start() :]

    if contents and not contents.endswith("\n"):
        contents += "\n"
    if contents:
        contents += "\n"
    return contents + replacement


def update_codex_toml(contents: str, catalog_path: Path, base_url: str) -> str:
    updated = update_root_setting(contents, "model_catalog_json", str(catalog_path))
    return replace_toml_table(
        updated,
        "model_providers.9router",
        "\n".join(
            (
                'name = "9Router"',
                f"base_url = {toml_string(validate_base_url(base_url))}",
                'wire_api = "responses"',
            )
        ),
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise SyncError(f"Cannot read {path}: {exc}") from exc


def atomic_write_text(path: Path, contents: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    except OSError as exc:
        raise SyncError(f"Cannot write {path}: {exc}") from exc


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_provider_routing(path: Path) -> Optional[dict[str, Any]]:
    contents = read_text(path).strip()
    if not contents:
        return None
    try:
        routing = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise SyncError("Existing provider-routing JSON is invalid") from exc
    if not isinstance(routing, dict):
        raise SyncError("Existing provider-routing JSON must be an object")

    providers = routing.get("providers")
    model_providers = routing.get("model_providers")
    if not isinstance(providers, list) or not isinstance(model_providers, dict):
        raise SyncError(
            "Existing provider-routing JSON has invalid providers or model_providers"
        )
    if any(
        not isinstance(provider, dict)
        or not isinstance(provider.get("id"), str)
        for provider in providers
    ):
        raise SyncError("Existing provider-routing JSON has an invalid provider entry")
    return routing


def merge_provider_routing(
    generated: dict[str, Any], existing: Optional[dict[str, Any]]
) -> dict[str, Any]:
    if existing is None:
        return generated

    generated_ids = {provider["id"] for provider in generated["providers"]}
    retained_providers = [
        provider for provider in existing["providers"] if provider["id"] not in generated_ids
    ]
    model_providers = dict(existing["model_providers"])
    model_providers.update(generated["model_providers"])
    return {
        "version": generated["version"],
        "default_provider": existing.get(
            "default_provider", generated["default_provider"]
        ),
        "providers": generated["providers"] + retained_providers,
        "model_providers": model_providers,
    }


def upsert_provider_menu_entry(
    routing: Optional[dict[str, Any]], provider_id: str, label: str
) -> dict[str, Any]:
    current = copy.deepcopy(routing) if routing is not None else {
        "version": 1,
        "default_provider": "openai",
        "providers": [
            {
                "id": "openai",
                "label": "ChatGPT / OpenAI",
                "description": "Built-in provider; uses your signed-in ChatGPT account",
            }
        ],
        "model_providers": {},
    }
    entry = {
        "id": provider_id,
        "label": label,
        "description": (
            f"Custom provider; uses [model_providers.{provider_id}] from config.toml"
        ),
    }
    current["providers"] = [
        provider for provider in current["providers"] if provider["id"] != provider_id
    ] + [entry]
    return current


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
    routing_path: Path,
    toml_path: Path,
    base_url: str,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    normalized_base_url = validate_base_url(base_url)
    bundled_catalog = read_bundled_catalog(codex_bin, command_runner=command_runner)
    existing_routing = read_provider_routing(routing_path)
    catalog, generated_routing = build_catalog_and_routing(bundled_catalog)
    routing = merge_provider_routing(generated_routing, existing_routing)
    updated_toml = update_codex_toml(read_text(toml_path), catalog_path, normalized_base_url)

    atomic_write_json(catalog_path, catalog)
    atomic_write_json(routing_path, routing)
    atomic_write_text(toml_path, updated_toml)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    home = codex_home()
    parser = argparse.ArgumentParser(
        description="Rebuild the Codex custom model catalog and 9router configuration."
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable (default: codex)")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=home / "model-catalogs" / "custom.json",
        help="Generated model catalog path",
    )
    parser.add_argument(
        "--provider-config",
        type=Path,
        default=home / "desktop-model-providers.json",
        help="Generated provider-routing JSON path",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=home / "config.toml",
        help="Codex TOML configuration path to update",
    )
    parser.add_argument(
        "--9router-base-url",
        dest="base_url",
        help=f"9router base URL; skips the prompt (default prompt value: {DEFAULT_BASE_URL})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url) if args.base_url else prompt_base_url()
        catalog_path = args.catalog.expanduser().resolve()
        routing_path = args.provider_config.expanduser().resolve()
        toml_path = args.config.expanduser().resolve()
        synchronize(args.codex_bin, catalog_path, routing_path, toml_path, base_url)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Updated model catalog: {catalog_path}")
    print(f"Updated provider routing: {routing_path}")
    print(f"Updated Codex configuration: {toml_path}")
    print("Restart ChatGPT/Codex to load the updated model catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
