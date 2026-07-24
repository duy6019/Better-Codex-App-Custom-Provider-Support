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
        provider = setup.ProviderSetup(
            "acme", "Acme", "https://api.acme.example/v1", "responses", "keychain"
        )

        updated = setup.update_provider_toml(
            '[model_providers.other]\nname = "Other"\n', provider
        )

        self.assertIn('[model_providers.acme]\nname = "Acme"', updated)
        self.assertIn('[model_providers.acme.auth]\ncommand = "security"', updated)
        self.assertIn('"codex-acme"', updated)
        self.assertIn('[model_providers.other]\nname = "Other"', updated)
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
