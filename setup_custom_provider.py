#!/usr/bin/env python3
"""Set up one macOS Keychain-backed Codex custom provider."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import getpass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Optional, Sequence

from sync_codex_models import (
    SyncError,
    atomic_write_json,
    atomic_write_text,
    codex_home,
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
AUTH_METHODS = {"keychain", "credential-manager", "none"}


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


def default_auth_method(*, platform_name: Optional[str] = None) -> str:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return "keychain"
    if platform_name == "win32":
        return "credential-manager"
    raise SetupError("Secure credential storage is supported only on macOS and Windows")


def validate_auth_method(value: str, *, platform_name: Optional[str] = None) -> str:
    auth_method = value.strip().lower()
    if auth_method not in AUTH_METHODS:
        raise SetupError("Authentication must be 'keychain', 'credential-manager', or 'none'")
    current_platform = platform_name or sys.platform
    if auth_method == "keychain" and current_platform != "darwin":
        if current_platform == "win32":
            raise SetupError("Use Windows Credential Manager authentication on Windows")
        raise SetupError("macOS Keychain authentication is available only on macOS")
    if auth_method == "credential-manager" and current_platform != "win32":
        if current_platform == "darwin":
            raise SetupError("Use macOS Keychain authentication on macOS")
        raise SetupError("Windows Credential Manager authentication is available only on Windows")
    return auth_method


def keychain_service(provider_id: str) -> str:
    return f"codex-{validate_provider_id(provider_id)}"


def user_level_config_path(path: Path) -> Path:
    config_path = path.expanduser().resolve()
    default_path = (codex_home() / "config.toml").expanduser().resolve()
    if (
        config_path.name == "config.toml"
        and config_path.parent.name == ".codex"
        and config_path != default_path
    ):
        raise SetupError("Custom providers must use a user-level config.toml")
    return config_path


def remove_toml_table(contents: str, table: str) -> str:
    header = re.compile(rf"(?m)^\[{re.escape(table)}\][^\n]*(?:\n|$)")
    match = header.search(contents)
    if not match:
        return contents
    next_header = re.search(r"(?m)^\[", contents[match.end() :])
    end = match.end() + next_header.start() if next_header else len(contents)
    return contents[: match.start()] + contents[end:]


def powershell_single_quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def windows_credential_lookup_script(target_name: str) -> str:
    script = r'''& {
$target = __TARGET__
$source = @'
using System;
using System.Runtime.InteropServices;
public static class CredentialManager {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct CREDENTIAL {
    public UInt32 Flags; public UInt32 Type; public IntPtr TargetName;
    public IntPtr Comment; public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public UInt32 CredentialBlobSize; public IntPtr CredentialBlob; public UInt32 Persist;
    public UInt32 AttributeCount; public IntPtr Attributes; public IntPtr TargetAlias; public IntPtr UserName;
  }
  [DllImport("Advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern bool CredReadW(string target, UInt32 type, UInt32 flags, out IntPtr credential);
  [DllImport("Advapi32.dll", SetLastError = true)]
  public static extern void CredFree(IntPtr credential);
}
'@
Add-Type -TypeDefinition $source
$credential = [IntPtr]::Zero
try {
  if (-not [CredentialManager]::CredReadW($target, 1, 0, [ref]$credential)) { throw "Could not read Windows Credential Manager entry '$target'" }
  $entry = [Runtime.InteropServices.Marshal]::PtrToStructure($credential, [type][CredentialManager+CREDENTIAL])
  [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringUni($entry.CredentialBlob, [int]($entry.CredentialBlobSize / 2)))
} finally {
  if ($credential -ne [IntPtr]::Zero) { [CredentialManager]::CredFree($credential) }
}
}'''
    return script.replace("__TARGET__", powershell_single_quoted(target_name))


def windows_credential_write_script(target_name: str, username: str) -> str:
    script = r'''& {
$target = __TARGET__
$username = __USERNAME__
$encodedKey = [Console]::In.ReadToEnd()
$source = @'
using System;
using System.Runtime.InteropServices;
public static class CredentialManager {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct CREDENTIAL {
    public UInt32 Flags; public UInt32 Type; public IntPtr TargetName;
    public IntPtr Comment; public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
    public UInt32 CredentialBlobSize; public IntPtr CredentialBlob; public UInt32 Persist;
    public UInt32 AttributeCount; public IntPtr Attributes; public IntPtr TargetAlias; public IntPtr UserName;
  }
  [DllImport("Advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern bool CredWriteW(ref CREDENTIAL credential, UInt32 flags);
}
'@
Add-Type -TypeDefinition $source
$targetPointer = [IntPtr]::Zero
$usernamePointer = [IntPtr]::Zero
$blob = [IntPtr]::Zero
try {
  $targetPointer = [Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($target)
  $usernamePointer = [Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($username)
  $bytes = [Convert]::FromBase64String($encodedKey)
  $blob = [Runtime.InteropServices.Marshal]::AllocCoTaskMem($bytes.Length)
  [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $blob, $bytes.Length)
  $entry = New-Object CredentialManager+CREDENTIAL
  $entry.Type = 1; $entry.TargetName = $targetPointer; $entry.UserName = $usernamePointer
  $entry.CredentialBlobSize = $bytes.Length; $entry.CredentialBlob = $blob; $entry.Persist = 2
  if (-not [CredentialManager]::CredWriteW([ref]$entry, 0)) { throw "Could not write Windows Credential Manager entry '$target'" }
} finally {
  if ($targetPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::FreeCoTaskMem($targetPointer) }
  if ($usernamePointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::FreeCoTaskMem($usernamePointer) }
  if ($blob -ne [IntPtr]::Zero) {
    for ($index = 0; $index -lt $bytes.Length; $index++) { [Runtime.InteropServices.Marshal]::WriteByte($blob, $index, 0) }
    [Runtime.InteropServices.Marshal]::FreeCoTaskMem($blob)
  }
  if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
}
}'''
    return (
        script.replace("__TARGET__", powershell_single_quoted(target_name))
        .replace("__USERNAME__", powershell_single_quoted(username))
    )


def update_provider_toml(
    contents: str, provider: ProviderSetup, *, platform_name: Optional[str] = None
) -> str:
    provider_id = validate_provider_id(provider.provider_id)
    auth_method = validate_auth_method(provider.auth_method, platform_name=platform_name)
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

    if auth_method == "keychain":
        auth_body = "\n".join(
            (
                'command = "security"',
                "args = " + json.dumps(
                    ["find-generic-password", "-s", keychain_service(provider_id), "-a", provider_id, "-w"]
                ),
            )
        )
    else:
        auth_body = "\n".join(
            (
                'command = "powershell.exe"',
                "args = " + json.dumps(
                    ["-NoProfile", "-NonInteractive", "-Command", windows_credential_lookup_script(keychain_service(provider_id))]
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


def store_api_key(
    provider_id: str,
    api_key: str,
    auth_method: str,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: Optional[str] = None,
) -> None:
    auth_method = validate_auth_method(auth_method, platform_name=platform_name)
    if not api_key:
        raise SetupError("API key cannot be empty")
    if auth_method == "keychain":
        store_keychain_api_key(provider_id, api_key, command_runner=command_runner)
        return
    if auth_method == "credential-manager":
        encoded_key = base64.b64encode(api_key.encode("utf-16le")).decode("ascii")
        command = [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            windows_credential_write_script(keychain_service(provider_id), provider_id),
        ]
        try:
            command_runner(
                command,
                input=encoded_key,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise SetupError(
                f"Could not store Windows Credential Manager entry '{keychain_service(provider_id)}'"
            ) from exc


def setup_provider(
    provider: ProviderSetup,
    toml_path: Path,
    routing_path: Path,
    *,
    api_key: Optional[str] = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: Optional[str] = None,
) -> None:
    toml_path = user_level_config_path(toml_path)
    provider = ProviderSetup(
        validate_provider_id(provider.provider_id),
        provider.label.strip(),
        validate_base_url(provider.base_url),
        validate_wire_api(provider.wire_api),
        validate_auth_method(provider.auth_method, platform_name=platform_name),
    )
    if not provider.label:
        raise SetupError("Provider display name cannot be empty")

    updated_toml = update_provider_toml(read_text(toml_path), provider, platform_name=platform_name)
    routing = upsert_provider_menu_entry(
        read_provider_routing(routing_path), provider.provider_id, provider.label
    )
    if provider.auth_method != "none":
        store_api_key(
            provider.provider_id, api_key or "", provider.auth_method,
            command_runner=command_runner, platform_name=platform_name,
        )

    try:
        atomic_write_text(toml_path, updated_toml)
        atomic_write_json(routing_path, routing)
    except SyncError as exc:
        if provider.auth_method != "none":
            raise SetupError(
                "Configuration update failed after storing secure credential entry "
                f"'{keychain_service(provider.provider_id)}'"
            ) from exc
        raise


def prompt_provider_setup(
    *,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass.getpass,
    platform_name: Optional[str] = None,
) -> tuple[ProviderSetup, Optional[str]]:
    provider_id = validate_provider_id(input_func("Provider ID: "))
    label = input_func("Display name: ").strip()
    if not label:
        raise SetupError("Provider display name cannot be empty")
    base_url = validate_base_url(input_func("Base URL: "))
    wire_api = validate_wire_api(input_func("Wire API [responses]: ") or "responses")
    try:
        default_method = default_auth_method(platform_name=platform_name)
    except SetupError:
        default_method = "none"
    auth_method = validate_auth_method(
        input_func(
            f"Authentication [keychain/credential-manager/none] [{default_method}]: "
        ) or default_method,
        platform_name=platform_name,
    )
    api_key = (
        getpass_func(f"API key for {keychain_service(provider_id)}: ")
        if auth_method != "none"
        else None
    )
    return ProviderSetup(provider_id, label, base_url, wire_api, auth_method), api_key


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    home = codex_home()
    parser = argparse.ArgumentParser(
        description="Add or update one Codex custom provider."
    )
    parser.add_argument("--config", type=Path, default=home / "config.toml")
    parser.add_argument(
        "--provider-config",
        type=Path,
        default=home / "desktop-model-providers.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        provider, api_key = prompt_provider_setup()
        config_path = args.config.expanduser().resolve()
        routing_path = args.provider_config.expanduser().resolve()
        setup_provider(provider, config_path, routing_path, api_key=api_key)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Updated Codex configuration: {config_path}")
    print(f"Updated provider routing: {routing_path}")
    if provider.auth_method == "keychain":
        print(
            f"Stored API key in Keychain service: "
            f"{keychain_service(provider.provider_id)}"
        )
    print("Restart ChatGPT/Codex before starting a task with this provider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
