#!/usr/bin/env python3
"""Set up one macOS Keychain-backed Codex custom provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Callable, Optional

from sync_codex_models import (
    SyncError,
    atomic_write_json,
    atomic_write_text,
    read_provider_routing,
    read_text,
    replace_toml_table,
    toml_string,
    upsert_provider_menu_entry,
    validate_base_url,
)


RESERVED_PROVIDER_IDS = {"openai", "ollama", "lmstudio", "9router"}
PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
WIRE_APIS = {"responses", "chat"}
AUTH_METHODS = {"keychain", "none"}


class SetupError(SyncError):
    """A safe, expected provider-setup failure."""


@dataclass(frozen=True)
class ProviderSetup:
    provider_id: str
    label: str
    base_url: str
    wire_api: str
    auth_method: str


def validate_provider_id(value: str) -> str:
    provider_id = value.strip()
    if (
        not PROVIDER_ID_PATTERN.fullmatch(provider_id)
        or provider_id in RESERVED_PROVIDER_IDS
    ):
        raise SetupError(
            "Provider ID must be lowercase, start with a letter, and not be reserved"
        )
    return provider_id


def validate_wire_api(value: str) -> str:
    wire_api = value.strip().lower()
    if wire_api not in WIRE_APIS:
        raise SetupError("Wire API must be 'responses' or 'chat'")
    return wire_api


def validate_auth_method(value: str) -> str:
    auth_method = value.strip().lower()
    if auth_method not in AUTH_METHODS:
        raise SetupError("Authentication must be 'keychain' or 'none'")
    return auth_method


def keychain_service(provider_id: str) -> str:
    return f"codex-{validate_provider_id(provider_id)}"


def remove_toml_table(contents: str, table: str) -> str:
    header = re.compile(rf"(?m)^\[{re.escape(table)}\][^\n]*(?:\n|$)")
    match = header.search(contents)
    if not match:
        return contents
    next_header = re.search(r"(?m)^\[", contents[match.end() :])
    end = match.end() + next_header.start() if next_header else len(contents)
    return contents[: match.start()] + contents[end:]


def update_provider_toml(contents: str, provider: ProviderSetup) -> str:
    provider_id = validate_provider_id(provider.provider_id)
    auth_method = validate_auth_method(provider.auth_method)
    table = f"model_providers.{provider_id}"
    body = "\n".join(
        (
            f"name = {toml_string(provider.label.strip())}",
            f"base_url = {toml_string(validate_base_url(provider.base_url))}",
            f"wire_api = {toml_string(validate_wire_api(provider.wire_api))}",
        )
    )
    updated = replace_toml_table(contents, table, body)
    auth_table = f"{table}.auth"
    if auth_method == "none":
        return remove_toml_table(updated, auth_table)

    auth_body = "\n".join(
        (
            'command = "security"',
            "args = "
            + json.dumps(
                [
                    "find-generic-password",
                    "-s",
                    keychain_service(provider_id),
                    "-a",
                    provider_id,
                    "-w",
                ]
            ),
        )
    )
    return replace_toml_table(updated, auth_table, auth_body)


def store_keychain_api_key(
    provider_id: str,
    api_key: str,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    if not api_key:
        raise SetupError("API key cannot be empty")
    command = [
        "security",
        "add-generic-password",
        "-U",
        "-s",
        keychain_service(provider_id),
        "-a",
        provider_id,
        "-w",
        api_key,
    ]
    try:
        command_runner(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SetupError(
            f"Could not store Keychain entry '{keychain_service(provider_id)}'"
        ) from exc


def setup_provider(
    provider: ProviderSetup,
    toml_path: Path,
    routing_path: Path,
    *,
    api_key: Optional[str] = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    provider = ProviderSetup(
        validate_provider_id(provider.provider_id),
        provider.label.strip(),
        validate_base_url(provider.base_url),
        validate_wire_api(provider.wire_api),
        validate_auth_method(provider.auth_method),
    )
    if not provider.label:
        raise SetupError("Provider display name cannot be empty")

    updated_toml = update_provider_toml(read_text(toml_path), provider)
    routing = upsert_provider_menu_entry(
        read_provider_routing(routing_path), provider.provider_id, provider.label
    )
    if provider.auth_method == "keychain":
        store_keychain_api_key(
            provider.provider_id, api_key or "", command_runner=command_runner
        )

    try:
        atomic_write_text(toml_path, updated_toml)
        atomic_write_json(routing_path, routing)
    except SyncError as exc:
        if provider.auth_method == "keychain":
            raise SetupError(
                "Configuration update failed after storing Keychain entry "
                f"'{keychain_service(provider.provider_id)}'"
            ) from exc
        raise
