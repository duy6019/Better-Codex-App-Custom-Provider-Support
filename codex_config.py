"""Shared local Codex configuration primitives."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Optional
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    """A safe, expected local configuration failure."""


OPENAI_PROVIDER = {
    "id": "openai",
    "label": "ChatGPT / OpenAI",
    "description": "Built-in provider; uses your signed-in ChatGPT account",
}


def codex_home() -> Path:
    configured_home = os.environ.get("CODEX_HOME")
    return Path(configured_home).expanduser() if configured_home else Path.home() / ".codex"


def validate_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("Base URL must be an absolute http or https URL")
    return base_url


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


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


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
        raise ConfigError(f"Cannot write {path}: {exc}") from exc


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def read_provider_routing(path: Path) -> Optional[dict[str, Any]]:
    contents = read_text(path).strip()
    if not contents:
        return None
    try:
        routing = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise ConfigError("Existing provider-routing JSON is invalid") from exc
    if not isinstance(routing, dict):
        raise ConfigError("Existing provider-routing JSON must be an object")

    providers = routing.get("providers")
    model_providers = routing.get("model_providers")
    if not isinstance(providers, list) or not isinstance(model_providers, dict):
        raise ConfigError(
            "Existing provider-routing JSON has invalid providers or model_providers"
        )
    if any(
        not isinstance(provider, dict)
        or not isinstance(provider.get("id"), str)
        for provider in providers
    ):
        raise ConfigError("Existing provider-routing JSON has an invalid provider entry")
    return routing


def upsert_provider_menu_entry(
    routing: Optional[dict[str, Any]], provider_id: str, label: str
) -> dict[str, Any]:
    current = copy.deepcopy(routing) if routing is not None else {
        "version": 1,
        "default_provider": "openai",
        "providers": [copy.deepcopy(OPENAI_PROVIDER)],
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
