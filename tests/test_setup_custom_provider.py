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

    def test_windows_default_auth_method_is_credential_manager(self):
        self.assertEqual(
            setup.default_auth_method(platform_name="win32"), "credential-manager"
        )

    def test_rejects_platform_incompatible_secure_store(self):
        with self.assertRaisesRegex(setup.SetupError, "Windows Credential Manager"):
            setup.validate_auth_method("keychain", platform_name="win32")
        with self.assertRaisesRegex(setup.SetupError, "macOS Keychain"):
            setup.validate_auth_method("credential-manager", platform_name="darwin")


class ProviderConfigurationTests(unittest.TestCase):
    def test_keychain_auth_toml_contains_lookup_command_but_not_key(self):
        provider = setup.ProviderSetup(
            "acme", "Acme", "https://api.acme.example/v1", "responses", "keychain"
        )

        updated = setup.update_provider_toml(
            '[model_providers.other]\nname = "Other"\n', provider, platform_name="darwin"
        )

        self.assertIn('[model_providers.acme]\nname = "Acme"', updated)
        self.assertIn('[model_providers.acme.auth]\ncommand = "security"', updated)
        self.assertIn('"codex-acme"', updated)
        self.assertIn('[model_providers.other]\nname = "Other"', updated)
        self.assertNotIn("test-key", updated)

    def test_windows_credential_manager_auth_toml_uses_powershell_lookup(self):
        provider = setup.ProviderSetup(
            "acme", "Acme", "https://api.acme.example/v1", "responses", "credential-manager"
        )

        updated = setup.update_provider_toml("", provider, platform_name="win32")

        self.assertIn('[model_providers.acme.auth]\ncommand = "powershell.exe"', updated)
        self.assertIn("CredRead", updated)
        self.assertIn('"& {\\n', updated)
        self.assertIn("codex-acme", updated)
        self.assertNotIn('", "codex-acme"]', updated)
        self.assertNotIn("test-key", updated)

    def test_no_auth_removes_existing_auth_table(self):
        contents = """[model_providers.acme]
name = "Old"

[model_providers.acme.auth]
command = "security"
args = ["find-generic-password"]
"""
        provider = setup.ProviderSetup(
            "acme", "Acme", "https://api.acme.example/v1", "chat", "none"
        )

        updated = setup.update_provider_toml(contents, provider)

        self.assertIn('wire_api = "chat"', updated)
        self.assertNotIn("[model_providers.acme.auth]", updated)

    def test_store_keychain_api_key_uses_provider_specific_service(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

        setup.store_keychain_api_key("acme", "test-key", command_runner=runner)

        self.assertEqual(
            runner.call_args.args[0],
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                "codex-acme",
                "-a",
                "acme",
                "-w",
                "test-key",
            ],
        )

    def test_store_windows_api_key_calls_powershell_credential_write(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

        setup.store_api_key(
            "acme", "test-key", "credential-manager",
            command_runner=runner, platform_name="win32",
        )

        command = runner.call_args.args[0]
        self.assertEqual(command[:4], ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"])
        self.assertIn("CredWrite", command[4])
        self.assertTrue(command[4].startswith("& {\n"))
        self.assertTrue(command[4].endswith("\n}"))
        self.assertEqual(command[5:], [])

    def test_store_windows_api_key_encodes_special_key_inside_command(self):
        api_key = "test key & value"
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

        setup.store_api_key(
            "acme", api_key, "credential-manager",
            command_runner=runner, platform_name="win32",
        )

        command = runner.call_args.args[0]
        self.assertNotIn(api_key, command[4])
        self.assertIn("FromBase64String", command[4])
        self.assertIn("Text.Encoding]::Unicode.GetString", command[4])

    def test_setup_provider_does_not_store_key_for_no_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = mock.Mock()
            provider = setup.ProviderSetup(
                "acme", "Acme", "https://api.acme.example/v1", "responses", "none"
            )

            setup.setup_provider(
                provider,
                root / "config.toml",
                root / "desktop-model-providers.json",
                command_runner=runner,
            )

            runner.assert_not_called()

    def test_setup_provider_rejects_project_local_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "project" / ".codex" / "config.toml"
            runner = mock.Mock()
            provider = setup.ProviderSetup(
                "acme", "Acme", "https://api.acme.example/v1", "responses", "keychain"
            )

            with self.assertRaisesRegex(setup.SetupError, "user-level"):
                setup.setup_provider(
                    provider,
                    config_path,
                    root / "desktop-model-providers.json",
                    api_key="test-key",
                    command_runner=runner,
                )

            runner.assert_not_called()


class InteractiveSetupTests(unittest.TestCase):
    def test_prompt_uses_responses_and_keychain_defaults(self):
        answers = iter(["acme", "Acme", "https://api.acme.example/v1", "", ""])

        provider, api_key = setup.prompt_provider_setup(
            input_func=lambda _: next(answers),
            getpass_func=lambda _: "test-key",
            platform_name="darwin",
        )

        self.assertEqual(
            provider,
            setup.ProviderSetup(
                "acme",
                "Acme",
                "https://api.acme.example/v1",
                "responses",
                "keychain",
            ),
        )
        self.assertEqual(api_key, "test-key")

    def test_prompt_uses_credential_manager_default_on_windows(self):
        answers = iter(["acme", "Acme", "https://api.acme.example/v1", "", ""])

        provider, api_key = setup.prompt_provider_setup(
            input_func=lambda _: next(answers),
            getpass_func=lambda _: "test-key",
            platform_name="win32",
        )

        self.assertEqual(provider.auth_method, "credential-manager")
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

    def test_prompt_allows_no_auth_on_unsupported_platform(self):
        answers = iter(["acme", "Acme", "https://api.acme.example/v1", "chat", "none"])
        key_prompt = mock.Mock()

        provider, api_key = setup.prompt_provider_setup(
            input_func=lambda _: next(answers),
            getpass_func=key_prompt,
            platform_name="linux",
        )

        self.assertEqual(provider.auth_method, "none")
        self.assertIsNone(api_key)
        key_prompt.assert_not_called()

    def test_setup_updates_config_and_menu_without_changing_model_mappings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            toml_path = root / "config.toml"
            routing_path = root / "desktop-model-providers.json"
            routing_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "default_provider": "openai",
                        "providers": [{"id": "openai", "label": "OpenAI"}],
                        "model_providers": {"keep/model": "keep"},
                    }
                ),
                encoding="utf-8",
            )
            runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

            setup.setup_provider(
                setup.ProviderSetup(
                    "acme",
                    "Acme",
                    "https://api.acme.example/v1",
                    "responses",
                    "keychain",
                ),
                toml_path,
                routing_path,
                api_key="test-key",
                command_runner=runner,
                platform_name="darwin",
            )

            self.assertIn(
                "[model_providers.acme.auth]", toml_path.read_text(encoding="utf-8")
            )
            routing = json.loads(routing_path.read_text(encoding="utf-8"))
            self.assertEqual(routing["model_providers"], {"keep/model": "keep"})
            self.assertEqual(routing["providers"][-1]["id"], "acme")


class DocumentationTests(unittest.TestCase):
    def test_readme_documents_custom_provider_setup_without_a_literal_key(self):
        readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())

        self.assertIn("python3 setup_custom_provider.py", readme)
        self.assertIn("codex-<provider-id>", readme)
        self.assertIn("does not create model catalog entries", normalized_readme)
        self.assertNotIn("API_KEY_CUA_BAN", readme)
