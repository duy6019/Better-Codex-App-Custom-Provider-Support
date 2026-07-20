from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest import mock

import patch_chatgpt_providers as patcher
import sync_codex_models as sync


FIXTURE_CATALOG = {
    "models": [
        {
            "slug": "gpt-5.6-sol",
            "display_name": "GPT-5.6-Sol",
            "context_window": 272000,
            "supported_reasoning_levels": [{"effort": "low"}],
        },
        {
            "slug": "codex-auto-review",
            "display_name": "Codex Auto Review",
            "visibility": "hide",
        },
    ]
}


class CatalogTests(unittest.TestCase):
    def test_build_catalog_and_routing_clones_every_bundled_model(self):
        catalog, routing = sync.build_catalog_and_routing(FIXTURE_CATALOG)

        self.assertEqual(
            [model["slug"] for model in catalog["models"]],
            [
                "gpt-5.6-sol",
                "codex-auto-review",
                "cx/gpt-5.6-sol",
                "cx/codex-auto-review",
            ],
        )
        self.assertEqual(catalog["models"][2]["display_name"], "GPT-5.6-Sol (9router)")
        self.assertEqual(catalog["models"][2]["context_window"], 272000)
        self.assertEqual(FIXTURE_CATALOG["models"][0]["slug"], "gpt-5.6-sol")
        self.assertEqual(routing["default_provider"], "openai")
        self.assertEqual(
            routing["model_providers"],
            {
                "cx/gpt-5.6-sol": "9router",
                "cx/codex-auto-review": "9router",
            },
        )

    def test_build_catalog_rejects_duplicate_model_slugs(self):
        catalog = {"models": [FIXTURE_CATALOG["models"][0], FIXTURE_CATALOG["models"][0]]}

        with self.assertRaisesRegex(sync.SyncError, "duplicate"):
            sync.build_catalog_and_routing(catalog)


class TomlTests(unittest.TestCase):
    def test_update_codex_toml_replaces_only_managed_entries(self):
        existing = """service_tier = \"default\"
model_catalog_json = \"/old/custom.json\"

[model_providers.9router]
name = \"Old Router\"
base_url = \"http://old.example/v1\"
wire_api = \"chat\"

[model_providers.9router.auth]
env_key = \"NINE_ROUTER_API_KEY\"

[model_providers.other]
name = \"Other\"

[projects.\"/work\"]
trust_level = \"trusted\"
"""

        updated = sync.update_codex_toml(
            existing, Path("/tmp/custom.json"), "https://router.example/v1"
        )

        self.assertIn('model_catalog_json = "/tmp/custom.json"', updated)
        self.assertIn('[model_providers.9router]\nname = "9Router"', updated)
        self.assertIn('base_url = "https://router.example/v1"', updated)
        self.assertIn('wire_api = "responses"', updated)
        self.assertIn('[model_providers.9router.auth]\nenv_key = "NINE_ROUTER_API_KEY"', updated)
        self.assertIn('[model_providers.other]\nname = "Other"', updated)
        self.assertIn('[projects."/work"]\ntrust_level = "trusted"', updated)
        self.assertNotIn('Old Router', updated)

    def test_update_codex_toml_adds_managed_entries_to_empty_file(self):
        updated = sync.update_codex_toml(
            "", Path("/tmp/custom.json"), "http://127.0.0.1:20128/v1"
        )

        self.assertEqual(
            updated,
            """model_catalog_json = \"/tmp/custom.json\"

[model_providers.9router]
name = \"9Router\"
base_url = \"http://127.0.0.1:20128/v1\"
wire_api = \"responses\"
""",
        )


class SynchronizeTests(unittest.TestCase):
    def test_synchronize_rebuilds_all_generated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "model-catalogs" / "custom.json"
            routing_path = root / "desktop-model-providers.json"
            toml_path = root / "config.toml"
            toml_path.write_text('model = "cx/gpt-5.6-sol"\n', encoding="utf-8")
            result = subprocess.CompletedProcess(
                ["codex", "debug", "models", "--bundled"],
                0,
                stdout=json.dumps(FIXTURE_CATALOG),
                stderr="",
            )

            sync.synchronize(
                "codex",
                catalog_path,
                routing_path,
                toml_path,
                "http://127.0.0.1:20128/v1",
                command_runner=mock.Mock(return_value=result),
            )

            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            routing = json.loads(routing_path.read_text(encoding="utf-8"))
            self.assertEqual(len(catalog["models"]), 4)
            self.assertEqual(routing["model_providers"]["cx/gpt-5.6-sol"], "9router")
            self.assertIn('model = "cx/gpt-5.6-sol"', toml_path.read_text(encoding="utf-8"))

    def test_prompted_base_url_uses_default_for_empty_answer(self):
        self.assertEqual(
            sync.prompt_base_url(input_func=lambda _: ""),
            "http://127.0.0.1:20128/v1",
        )

    def test_invalid_base_url_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "custom.json"
            routing_path = root / "routing.json"
            toml_path = root / "config.toml"
            result = subprocess.CompletedProcess(
                ["codex", "debug", "models", "--bundled"],
                0,
                stdout=json.dumps(FIXTURE_CATALOG),
                stderr="",
            )

            with self.assertRaisesRegex(sync.SyncError, "http"):
                sync.synchronize(
                    "codex",
                    catalog_path,
                    routing_path,
                    toml_path,
                    "not-a-url",
                    command_runner=mock.Mock(return_value=result),
                )

            self.assertFalse(catalog_path.exists())
            self.assertFalse(routing_path.exists())
            self.assertFalse(toml_path.exists())


class PatcherTemplateTests(unittest.TestCase):
    def test_patcher_default_template_uses_9router(self):
        self.assertEqual(patcher.DEFAULT_PROVIDER_CONFIG["providers"][1]["id"], "9router")
        self.assertNotIn("openrouter", patcher.CENTRAL_DIFF)
        self.assertNotIn("openrouter", patcher.PICKER_DIFF)
        self.assertNotIn("\n++", patcher.CENTRAL_DIFF)
        self.assertNotIn("\n++", patcher.PICKER_DIFF)

    def test_provider_picker_defaults_legacy_auto_to_openai_without_showing_auto(self):
        self.assertEqual(patcher.DEFAULT_PROVIDER_CONFIG["default_provider"], "openai")
        self.assertNotIn("Automatic", patcher.PICKER_DIFF)
        self.assertNotIn("modelProviders[e?.model]", patcher.CENTRAL_DIFF)
        self.assertIn("e.defaultProvider", patcher.PICKER_DIFF)

    def test_start_and_fork_use_the_explicit_picker_provider(self):
        self.assertIn("thread/start", patcher.CENTRAL_DIFF)
        self.assertIn("thread/fork", patcher.CENTRAL_DIFF)
        self.assertIn(
            "modelProvider: await codexSelectedProvider()", patcher.CENTRAL_DIFF
        )

    def test_patcher_help_describes_explicit_provider_selection(self):
        output = io.StringIO()

        with (
            mock.patch.object(patcher.sys, "argv", ["patch_chatgpt_providers.py", "--help"]),
            redirect_stdout(output),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            patcher.parse_args()

        self.assertIn("explicit provider selector", output.getvalue())
        self.assertNotIn("per-model provider routing", output.getvalue())


class ReapplyTests(unittest.TestCase):
    def test_reapply_source_accepts_matching_original_app_backup(self):
        self.assertTrue(hasattr(patcher, "validate_reapply_source"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            backup = root / "ChatGPT-original.app"
            for bundle in (app, backup):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(b"asar")
                with (bundle / "Contents" / "Info.plist").open("wb") as handle:
                    plistlib.dump(
                        {
                            "CFBundleShortVersionString": "26.715.31925",
                            "CFBundleVersion": "5551",
                        },
                        handle,
                    )

            with mock.patch.object(
                patcher,
                "contains_marker",
                side_effect=lambda path: path == app / "Contents" / "Resources" / "app.asar",
            ):
                self.assertEqual(patcher.validate_reapply_source(app, backup), backup)

    def test_reapply_source_rejects_backup_from_another_app_build(self):
        self.assertTrue(hasattr(patcher, "validate_reapply_source"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            backup = root / "ChatGPT-original.app"
            for bundle, build in ((app, "5551"), (backup, "5552")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(b"asar")
                with (bundle / "Contents" / "Info.plist").open("wb") as handle:
                    plistlib.dump(
                        {
                            "CFBundleShortVersionString": "26.715.31925",
                            "CFBundleVersion": build,
                        },
                        handle,
                    )

            with mock.patch.object(
                patcher,
                "contains_marker",
                side_effect=lambda path: path == app / "Contents" / "Resources" / "app.asar",
            ):
                with self.assertRaisesRegex(patcher.PatchError, "does not match"):
                    patcher.validate_reapply_source(app, backup)


if __name__ == "__main__":
    unittest.main()
