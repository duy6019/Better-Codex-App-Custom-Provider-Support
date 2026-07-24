# Custom Provider Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone interactive script that securely configures one Keychain-backed or unauthenticated custom provider per run without removing existing provider menu entries.

**Architecture:** A new `setup_custom_provider.py` owns prompting, Keychain writes, and configuration updates. `sync_codex_models.py` gains validated JSON helpers so the wizard and the existing 9router sync retain unrelated desktop providers and model mappings.

**Tech Stack:** Python 3.9+, standard library (`argparse`, `getpass`, `json`, `subprocess`, `unittest`), macOS `security` CLI, TOML text tables.

## Global Constraints

- Support macOS only and Python 3.9 or newer; add no dependencies.
- Configure exactly one provider per wizard invocation.
- Provider IDs match `^[a-z][a-z0-9_-]*$` and cannot be `openai`, `ollama`, `lmstudio`, or `9router`.
- Keychain service names are exactly `codex-<provider-id>`; the account is the provider ID.
- Authentication is either Keychain or no auth; `wire_api` is `responses` or `chat`.
- API keys must not be written to config, JSON, output, errors, or documentation examples.
- The setup script must not create or route model catalog entries.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `sync_codex_models.py` | Validated provider-routing JSON read, merge, and menu-update helpers. |
| `setup_custom_provider.py` | Provider prompts, Keychain storage, TOML/menu updates, and standalone CLI. |
| `tests/test_sync_codex_models.py` | 9router sync regression tests for retaining custom providers. |
| `tests/test_setup_custom_provider.py` | Wizard unit and integration tests. |
| `README.md` | New-command usage and Keychain/model boundary. |

## Task 1: Preserve Provider Routing During 9router Sync

**Files:**
- Modify: `sync_codex_models.py`
- Modify: `tests/test_sync_codex_models.py`

**Interfaces:**
- Produces: `read_provider_routing(path: Path) -> Optional[dict[str, Any]]`
- Produces: `merge_provider_routing(generated: dict[str, Any], existing: Optional[dict[str, Any]]) -> dict[str, Any]`
- Produces: `upsert_provider_menu_entry(routing: Optional[dict[str, Any]], provider_id: str, label: str) -> dict[str, Any]`
- Consumed by Task 2: validated routing-file access and menu mutation.

- [ ] **Step 1: Write the failing routing tests**

Add this test class to `tests/test_sync_codex_models.py`:

```python
class ProviderRoutingMergeTests(unittest.TestCase):
    def test_merge_keeps_unrelated_provider_and_model_mapping(self):
        generated = sync.provider_routing([{"slug": "cx/gpt-5.6-sol"}])
        existing = {
            "version": 1,
            "default_provider": "openai",
            "providers": [
                {"id": "openai", "label": "Old OpenAI"},
                {"id": "acme", "label": "Acme", "description": "Custom"},
            ],
            "model_providers": {"acme/gpt-5.6-sol": "acme"},
        }

        merged = sync.merge_provider_routing(generated, existing)

        self.assertEqual(merged["default_provider"], "openai")
        self.assertEqual(
            [provider["id"] for provider in merged["providers"]],
            ["openai", "9router", "acme"],
        )
        self.assertEqual(merged["providers"][0]["label"], "ChatGPT / OpenAI")
        self.assertEqual(merged["model_providers"]["cx/gpt-5.6-sol"], "9router")
        self.assertEqual(merged["model_providers"]["acme/gpt-5.6-sol"], "acme")

    def test_synchronize_rejects_invalid_existing_routing_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            routing_path = root / "routing.json"
            routing_path.write_text("not json", encoding="utf-8")
            result = subprocess.CompletedProcess(
                ["codex", "debug", "models", "--bundled"], 0,
                stdout=json.dumps(FIXTURE_CATALOG), stderr="",
            )

            with self.assertRaisesRegex(sync.SyncError, "provider-routing JSON"):
                sync.synchronize(
                    "codex", root / "catalog.json", routing_path, root / "config.toml",
                    "http://127.0.0.1:20128/v1", command_runner=mock.Mock(return_value=result),
                )
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.ProviderRoutingMergeTests -v
```

Expected: FAIL with `AttributeError` for `merge_provider_routing`.

- [ ] **Step 3: Implement routing validation, merge, and upsert**

Add `Optional` to the existing `typing` import, then add this code after `atomic_write_json` in `sync_codex_models.py`:

```python
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
    providers = routing.get("providers", [])
    mappings = routing.get("model_providers", {})
    if not isinstance(providers, list) or not isinstance(mappings, dict):
        raise SyncError("Existing provider-routing JSON has invalid providers or model_providers")
    if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in providers):
        raise SyncError("Existing provider-routing JSON has an invalid provider entry")
    return routing


def merge_provider_routing(generated: dict[str, Any], existing: Optional[dict[str, Any]]) -> dict[str, Any]:
    if existing is None:
        return generated
    generated_ids = {provider["id"] for provider in generated["providers"]}
    retained = [provider for provider in existing["providers"] if provider["id"] not in generated_ids]
    mappings = dict(existing["model_providers"])
    mappings.update(generated["model_providers"])
    return {
        "version": generated["version"],
        "default_provider": existing.get("default_provider", generated["default_provider"]),
        "providers": generated["providers"] + retained,
        "model_providers": mappings,
    }


def upsert_provider_menu_entry(
    routing: Optional[dict[str, Any]], provider_id: str, label: str
) -> dict[str, Any]:
    current = routing or {
        "version": 1,
        "default_provider": "openai",
        "providers": [{
            "id": "openai",
            "label": "ChatGPT / OpenAI",
            "description": "Built-in provider; uses your signed-in ChatGPT account",
        }],
        "model_providers": {},
    }
    entry = {
        "id": provider_id,
        "label": label,
        "description": f"Custom provider; uses [model_providers.{provider_id}] from config.toml",
    }
    current["providers"] = [item for item in current["providers"] if item["id"] != provider_id] + [entry]
    return current
```

Update `synchronize` before writing generated JSON:

```python
existing_routing = read_provider_routing(routing_path)
catalog, generated_routing = build_catalog_and_routing(bundled_catalog)
routing = merge_provider_routing(generated_routing, existing_routing)
```

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.ProviderRoutingMergeTests -v
```

Expected: PASS with both tests reporting `ok`.

- [ ] **Step 5: Commit the completed task**

```bash
git add sync_codex_models.py tests/test_sync_codex_models.py
git commit -m "fix: preserve custom providers during model sync"
```

## Task 2: Implement Provider Setup Core and Keychain Storage

**Files:**
- Create: `setup_custom_provider.py`
- Create: `tests/test_setup_custom_provider.py`

**Interfaces:**
- Consumes: `SyncError`, `atomic_write_json`, `atomic_write_text`, `read_provider_routing`, `replace_toml_table`, `toml_string`, `upsert_provider_menu_entry`, and `validate_base_url` from `sync_codex_models.py`.
- Produces: `ProviderSetup`, `SetupError`, `validate_provider_id`, `validate_wire_api`, `keychain_service`, `update_provider_toml`, `store_keychain_api_key`, and `setup_provider`.
- Consumed by Task 3: interactive prompts and the command entrypoint.

- [ ] **Step 1: Write the failing core tests**

Create `tests/test_setup_custom_provider.py` with this test coverage:

```python
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import setup_custom_provider as setup


class ProviderValidationTests(unittest.TestCase):
    def test_validate_provider_id_accepts_keychain_safe_identifier(self):
        self.assertEqual(setup.validate_provider_id("acme-router"), "acme-router")
        self.assertEqual(setup.keychain_service("acme-router"), "codex-acme-router")

    def test_validate_provider_id_rejects_reserved_or_invalid_identifiers(self):
        for value in ("openai", "9router", "Acme", "has space"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(setup.SetupError, "Provider ID"):
                    setup.validate_provider_id(value)


class ProviderConfigurationTests(unittest.TestCase):
    def test_keychain_auth_toml_contains_lookup_command_but_not_key(self):
        provider = setup.ProviderSetup("acme", "Acme", "https://api.acme.example/v1", "responses", "keychain")

        updated = setup.update_provider_toml('[model_providers.other]\\nname = "Other"\\n', provider)

        self.assertIn('[model_providers.acme]\\nname = "Acme"', updated)
        self.assertIn('[model_providers.acme.auth]\\ncommand = "security"', updated)
        self.assertIn('"codex-acme"', updated)
        self.assertIn('[model_providers.other]\\nname = "Other"', updated)
        self.assertNotIn("test-key", updated)

    def test_no_auth_removes_existing_auth_table(self):
        contents = """[model_providers.acme]
name = "Old"

[model_providers.acme.auth]
command = "security"
args = ["find-generic-password"]
"""
        provider = setup.ProviderSetup("acme", "Acme", "https://api.acme.example/v1", "chat", "none")

        updated = setup.update_provider_toml(contents, provider)

        self.assertIn('wire_api = "chat"', updated)
        self.assertNotIn("[model_providers.acme.auth]", updated)

    def test_store_keychain_api_key_uses_provider_specific_service(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

        setup.store_keychain_api_key("acme", "test-key", command_runner=runner)

        self.assertEqual(
            runner.call_args.args[0],
            ["security", "add-generic-password", "-U", "-s", "codex-acme", "-a", "acme", "-w", "test-key"],
        )
```

- [ ] **Step 2: Run the core tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'setup_custom_provider'`.

- [ ] **Step 3: Write the minimal provider core**

Create `setup_custom_provider.py` with this implementation. Use `Sequence` rather than Python 3.10-only annotations when adding CLI code later.

```python
#!/usr/bin/env python3
"""Interactively add one macOS Keychain-backed Codex custom provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Callable, Optional

from sync_codex_models import (
    SyncError, atomic_write_json, atomic_write_text, read_provider_routing,
    replace_toml_table, toml_string, upsert_provider_menu_entry, validate_base_url,
)


RESERVED_PROVIDER_IDS = {"openai", "ollama", "lmstudio", "9router"}
PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
WIRE_APIS = {"responses", "chat"}


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
    if not PROVIDER_ID_PATTERN.fullmatch(provider_id) or provider_id in RESERVED_PROVIDER_IDS:
        raise SetupError("Provider ID must be lowercase, start with a letter, and not be reserved")
    return provider_id


def validate_wire_api(value: str) -> str:
    wire_api = value.strip().lower()
    if wire_api not in WIRE_APIS:
        raise SetupError("Wire API must be 'responses' or 'chat'")
    return wire_api


def keychain_service(provider_id: str) -> str:
    return f"codex-{validate_provider_id(provider_id)}"


def remove_toml_table(contents: str, table: str) -> str:
    header = re.compile(rf"(?m)^\\[{re.escape(table)}\\][^\\n]*(?:\\n|$)")
    match = header.search(contents)
    if not match:
        return contents
    next_header = re.search(r"(?m)^\\[", contents[match.end():])
    end = match.end() + next_header.start() if next_header else len(contents)
    return contents[:match.start()] + contents[end:]


def update_provider_toml(contents: str, provider: ProviderSetup) -> str:
    table = f"model_providers.{validate_provider_id(provider.provider_id)}"
    body = "\\n".join((
        f"name = {toml_string(provider.label)}",
        f"base_url = {toml_string(validate_base_url(provider.base_url))}",
        f"wire_api = {toml_string(validate_wire_api(provider.wire_api))}",
    ))
    updated = replace_toml_table(contents, table, body)
    auth_table = f"{table}.auth"
    if provider.auth_method == "none":
        return remove_toml_table(updated, auth_table)
    if provider.auth_method != "keychain":
        raise SetupError("Authentication must be 'keychain' or 'none'")
    auth_body = '\\n'.join((
        'command = "security"',
        "args = " + json.dumps([
            "find-generic-password", "-s", keychain_service(provider.provider_id),
            "-a", provider.provider_id, "-w",
        ]),
    ))
    return replace_toml_table(updated, auth_table, auth_body)


def store_keychain_api_key(provider_id: str, api_key: str, *, command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    if not api_key:
        raise SetupError("API key cannot be empty")
    command = ["security", "add-generic-password", "-U", "-s", keychain_service(provider_id), "-a", provider_id, "-w", api_key]
    try:
        command_runner(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SetupError(f"Could not store Keychain entry '{keychain_service(provider_id)}'") from exc


def setup_provider(provider: ProviderSetup, toml_path: Path, routing_path: Path, *, api_key: Optional[str] = None, command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    provider = ProviderSetup(
        validate_provider_id(provider.provider_id), provider.label.strip(),
        validate_base_url(provider.base_url), validate_wire_api(provider.wire_api), provider.auth_method,
    )
    if not provider.label:
        raise SetupError("Provider display name cannot be empty")
    routing = upsert_provider_menu_entry(read_provider_routing(routing_path), provider.provider_id, provider.label)
    if provider.auth_method == "keychain":
        store_keychain_api_key(provider.provider_id, api_key or "", command_runner=command_runner)
    contents = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
    atomic_write_text(toml_path, update_provider_toml(contents, provider))
    atomic_write_json(routing_path, routing)
```

- [ ] **Step 4: Run the core tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider -v
```

Expected: PASS with all provider validation, TOML, and Keychain command tests reporting `ok`.

- [ ] **Step 5: Commit the completed task**

```bash
git add setup_custom_provider.py tests/test_setup_custom_provider.py
git commit -m "feat: add custom provider setup core"
```

## Task 3: Add Interactive Prompts and the Standalone CLI

**Files:**
- Modify: `setup_custom_provider.py`
- Modify: `tests/test_setup_custom_provider.py`

**Interfaces:**
- Consumes: `ProviderSetup` and `setup_provider` from Task 2.
- Produces: `prompt_provider_setup`, `parse_args`, and `main`.
- Produces: success output listing configuration paths and Keychain service name only.

- [ ] **Step 1: Write failing prompt and end-to-end tests**

Append this test class to `tests/test_setup_custom_provider.py`:

```python
class InteractiveSetupTests(unittest.TestCase):
    def test_prompt_uses_responses_and_keychain_defaults(self):
        answers = iter(["acme", "Acme", "https://api.acme.example/v1", "", ""])

        provider, api_key = setup.prompt_provider_setup(
            input_func=lambda _: next(answers), getpass_func=lambda _: "test-key"
        )

        self.assertEqual(
            provider,
            setup.ProviderSetup("acme", "Acme", "https://api.acme.example/v1", "responses", "keychain"),
        )
        self.assertEqual(api_key, "test-key")

    def test_prompt_allows_no_auth_without_requesting_key(self):
        answers = iter(["acme", "Acme", "https://api.acme.example/v1", "chat", "none"])
        key_prompt = mock.Mock()

        provider, api_key = setup.prompt_provider_setup(
            input_func=lambda _: next(answers), getpass_func=key_prompt
        )

        self.assertEqual(provider.auth_method, "none")
        self.assertIsNone(api_key)
        key_prompt.assert_not_called()

    def test_setup_updates_config_and_menu_without_changing_model_mappings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            toml_path = root / "config.toml"
            routing_path = root / "desktop-model-providers.json"
            routing_path.write_text(json.dumps({
                "version": 1, "default_provider": "openai",
                "providers": [{"id": "openai", "label": "OpenAI"}],
                "model_providers": {"keep/model": "keep"},
            }), encoding="utf-8")
            runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

            setup.setup_provider(
                setup.ProviderSetup("acme", "Acme", "https://api.acme.example/v1", "responses", "keychain"),
                toml_path, routing_path, api_key="test-key", command_runner=runner,
            )

            self.assertIn('[model_providers.acme.auth]', toml_path.read_text(encoding="utf-8"))
            routing = json.loads(routing_path.read_text(encoding="utf-8"))
            self.assertEqual(routing["model_providers"], {"keep/model": "keep"})
            self.assertEqual(routing["providers"][-1]["id"], "acme")
```

- [ ] **Step 2: Run the interactive tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider.InteractiveSetupTests -v
```

Expected: FAIL with `AttributeError` for `prompt_provider_setup`.

- [ ] **Step 3: Implement prompts and the CLI entrypoint**

Import `argparse`, `getpass`, `sys`, `Optional`, `Sequence`, and `codex_home`. Then add this code to `setup_custom_provider.py`:

```python
def prompt_provider_setup(
    *, input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass.getpass,
) -> tuple[ProviderSetup, Optional[str]]:
    provider_id = validate_provider_id(input_func("Provider ID: "))
    label = input_func("Display name: ").strip()
    if not label:
        raise SetupError("Provider display name cannot be empty")
    base_url = validate_base_url(input_func("Base URL: "))
    wire_api = validate_wire_api(input_func("Wire API [responses]: ") or "responses")
    auth_method = (input_func("Authentication [keychain/none] [keychain]: ") or "keychain").strip().lower()
    if auth_method not in {"keychain", "none"}:
        raise SetupError("Authentication must be 'keychain' or 'none'")
    api_key = getpass_func(f"API key for {keychain_service(provider_id)}: ") if auth_method == "keychain" else None
    return ProviderSetup(provider_id, label, base_url, wire_api, auth_method), api_key


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    home = codex_home()
    parser = argparse.ArgumentParser(description="Add or update one Codex custom provider.")
    parser.add_argument("--config", type=Path, default=home / "config.toml")
    parser.add_argument("--provider-config", type=Path, default=home / "desktop-model-providers.json")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        provider, api_key = prompt_provider_setup()
        config_path = args.config.expanduser().resolve()
        routing_path = args.provider_config.expanduser().resolve()
        setup_provider(provider, config_path, routing_path, api_key=api_key)
    except SetupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Updated Codex configuration: {config_path}")
    print(f"Updated provider routing: {routing_path}")
    if provider.auth_method == "keychain":
        print(f"Stored API key in Keychain service: {keychain_service(provider.provider_id)}")
    print("Restart ChatGPT/Codex before starting a task with this provider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused and full tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider -v
python3 -m unittest discover -s tests -v
```

Expected: both commands PASS; the full suite retains all existing patcher and model-sync tests.

- [ ] **Step 5: Commit the completed task**

```bash
git add setup_custom_provider.py tests/test_setup_custom_provider.py
git commit -m "feat: add interactive custom provider setup"
```

## Task 4: Document the Setup Wizard

**Files:**
- Modify: `README.md`
- Modify: `tests/test_setup_custom_provider.py`

**Interfaces:**
- Consumes: the Task 3 command contract.
- Produces: documented invocation and exact Keychain/model-management expectations.

- [ ] **Step 1: Write the failing documentation contract test**

Add this test:

```python
class DocumentationTests(unittest.TestCase):
    def test_readme_documents_custom_provider_setup_without_a_literal_key(self):
        readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")

        self.assertIn("python3 setup_custom_provider.py", readme)
        self.assertIn("codex-<provider-id>", readme)
        self.assertIn("does not create model catalog entries", readme)
        self.assertNotIn("API_KEY_CUA_BAN", readme)
```

- [ ] **Step 2: Run the documentation test to verify RED**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider.DocumentationTests -v
```

Expected: FAIL because README does not yet document the setup script.

- [ ] **Step 3: Add the README section**

Insert this section after `## Sync Codex models and 9router` in `README.md`:

````markdown
## Add a custom provider

Use the separate setup wizard to add or update one provider without editing
Codex configuration files manually:

```bash
python3 setup_custom_provider.py
```

The wizard asks for the provider ID, display name, base URL, wire API, and
authentication mode. Choose `keychain` to store the API key in macOS Keychain
under `codex-<provider-id>`; choose `none` for endpoints that do not require
authentication. The key is not written to `config.toml` or the provider-routing
JSON file.

The provider is added to the desktop provider menu. This wizard does not create
model catalog entries or model routing; use a model supported by the endpoint,
then select the provider before starting a new task.
````

- [ ] **Step 4: Run final verification**

Run:

```bash
python3 -m unittest tests.test_setup_custom_provider.DocumentationTests -v
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: both test commands PASS and `git diff --check` exits with code 0 and no output.

- [ ] **Step 5: Commit the completed task**

```bash
git add README.md tests/test_setup_custom_provider.py
git commit -m "docs: explain custom provider setup"
```

## Plan Self-Review

- **Spec coverage:** Task 1 retains wizard-created providers during 9router sync. Tasks 2 and 3 cover validation, all required inputs, both auth modes, service naming, Keychain behavior, TOML/menu updates, safe errors, and output. Task 4 documents the command and its no-model boundary.
- **Completeness scan:** Every change lists exact paths, code, and a focused command; no unfinished implementation markers remain.
- **Type consistency:** `ProviderSetup`, `SetupError`, `setup_provider`, `read_provider_routing`, and `upsert_provider_menu_entry` are defined before later tasks use them. `wire_api` and `auth_method` remain constrained to the documented values.
