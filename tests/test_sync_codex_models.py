from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import plistlib
import shutil
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

    def test_installer_has_no_persistent_backup_directory_option(self):
        output = io.StringIO()

        with (
            mock.patch.object(
                patcher.sys, "argv", ["patch_chatgpt_providers.py", "--help"]
            ),
            redirect_stdout(output),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            patcher.parse_args()

        self.assertNotIn("--backup-dir", output.getvalue())

    def test_provider_picker_renders_subcomponents_from_menu_namespace(self):
        hunk = patcher.parse_hunks(patcher.PICKER_DIFF)[0]
        diff = "@@ -1,1 +1,1 @@\n" + "\n".join(hunk) + "\n"
        source = "\n".join(line[1:] for line in hunk if line[0] in " -") + "\n"

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "picker.js"
            bundle.write_text(source, encoding="utf-8")

            patcher.apply_unified_diff(bundle, diff)

            patched = bundle.read_text(encoding="utf-8")

        provider_section = patched.split(
            "function CodexCustomProviderPickerSection()", 1
        )[1].split("function MO(e)", 1)[0]
        for component in ("Item", "Title", "Separator"):
            self.assertIn(f"Ly.{component}", provider_section)
            self.assertNotIn(f"zy.{component}", provider_section)

    def test_picker_import_hunk_tolerates_added_upstream_initializers(self):
        hunk = patcher.parse_hunks(patcher.PICKER_DIFF)[2]
        diff = "@@ -1,1 +1,1 @@\n" + "\n".join(hunk) + "\n"
        source = """}
var PO,
  FO,
  IO = e(() => {
    ((PO = w()),
      T(),
      Q(),
      Mg(),
      wg(),
      Pg(),
      (FO = k()));
  }),
"""

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "picker.js"
            bundle.write_text(source, encoding="utf-8")

            patcher.apply_unified_diff(bundle, diff)

            patched = bundle.read_text(encoding="utf-8")

        self.assertIn("CodexProviderPatchReact", patched)
        self.assertIn("(CodexProviderPatchReact = t(m(), 1))", patched)


class ManagedBackupTests(unittest.TestCase):
    def test_make_backup_replaces_the_single_managed_original_after_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            backup = root / ".codex" / "ChatGPT-original.app"
            for bundle, contents in ((app, b"new"), (backup, b"old")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(contents)

            def copy_app(command, **_kwargs):
                patcher.shutil.copytree(Path(command[1]), Path(command[2]))
                return subprocess.CompletedProcess(command, 0, "")

            with (
                mock.patch.object(patcher, "run", side_effect=copy_app),
                mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
                mock.patch.object(patcher, "contains_marker", return_value=False),
            ):
                self.assertEqual(patcher.make_backup(app, backup), backup)

            self.assertEqual(
                (backup / "Contents" / "Resources" / "app.asar").read_bytes(), b"new"
            )
            self.assertEqual(
                list(backup.parent.glob(".ChatGPT-original.app.*")), []
            )

    def test_main_restores_managed_backup_before_reapplying(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            config = root / "custom" / "desktop-model-providers.json"
            managed_home = root / ".codex"
            app_asar = app / "Contents" / "Resources" / "app.asar"
            app_asar.parent.mkdir(parents=True)
            app_asar.write_bytes(b"patched")
            resolved_app = app.resolve()
            resolved_config = config.resolve()
            resolved_backup = managed_home.resolve() / "ChatGPT-original.app"
            args = mock.Mock(
                app=app,
                config=config,
                reapply_from=None,
                overwrite_config=False,
                allow_running=False,
            )

            with (
                mock.patch.object(patcher, "parse_args", return_value=args),
                mock.patch.dict(
                    patcher.os.environ, {"CODEX_HOME": str(managed_home)}
                ),
                mock.patch.object(patcher, "stop_target_app_processes"),
                mock.patch.object(patcher, "contains_marker", return_value=True),
                mock.patch.object(
                    patcher, "validate_reapply_source", return_value=resolved_backup
                ) as validate,
                mock.patch.object(patcher, "restore_backup") as restore,
                mock.patch.object(patcher, "patch_app") as patch_app,
            ):
                self.assertEqual(patcher.main(), 0)

            validate.assert_called_once_with(resolved_app, resolved_backup)
            restore.assert_called_once_with(resolved_app, resolved_backup)
            patch_app.assert_called_once_with(
                resolved_app,
                resolved_config,
                resolved_backup,
                False,
                legacy_backup=None,
            )

    def test_main_migrates_legacy_custom_config_backup_after_reapplying(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            config = root / "custom" / "desktop-model-providers.json"
            legacy_backup = config.parent / "ChatGPT-original.app"
            managed_home = root / ".codex"
            app_asar = app / "Contents" / "Resources" / "app.asar"
            app_asar.parent.mkdir(parents=True)
            app_asar.write_bytes(b"patched")
            legacy_backup.mkdir(parents=True)
            args = mock.Mock(
                app=app,
                config=config,
                reapply_from=None,
                overwrite_config=False,
                allow_running=False,
            )

            with (
                mock.patch.object(patcher, "parse_args", return_value=args),
                mock.patch.dict(
                    patcher.os.environ, {"CODEX_HOME": str(managed_home)}
                ),
                mock.patch.object(patcher, "stop_target_app_processes"),
                mock.patch.object(patcher, "contains_marker", return_value=True),
                mock.patch.object(
                    patcher, "validate_reapply_source", return_value=legacy_backup
                ) as validate,
                mock.patch.object(patcher, "restore_backup"),
                mock.patch.object(patcher, "patch_app") as patch_app,
            ):
                self.assertEqual(patcher.main(), 0)

            self.assertEqual(validate.call_args.args[1], legacy_backup.resolve())
            patch_app.assert_called_once_with(
                app.resolve(),
                config.resolve(),
                managed_home.resolve() / "ChatGPT-original.app",
                False,
                legacy_backup=legacy_backup.resolve(),
            )

    def test_main_consolidates_legacy_backup_for_an_unpatched_app_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            config = root / "custom" / "desktop-model-providers.json"
            legacy_backup = config.parent / "ChatGPT-original.app"
            managed_home = root / ".codex"
            app_asar = app / "Contents" / "Resources" / "app.asar"
            app_asar.parent.mkdir(parents=True)
            app_asar.write_bytes(b"original-update")
            legacy_backup.mkdir(parents=True)
            args = mock.Mock(
                app=app,
                config=config,
                reapply_from=None,
                overwrite_config=False,
                allow_running=False,
            )

            with (
                mock.patch.object(patcher, "parse_args", return_value=args),
                mock.patch.dict(
                    patcher.os.environ, {"CODEX_HOME": str(managed_home)}
                ),
                mock.patch.object(patcher, "stop_target_app_processes"),
                mock.patch.object(patcher, "contains_marker", return_value=False),
                mock.patch.object(patcher, "patch_app") as patch_app,
            ):
                self.assertEqual(patcher.main(), 0)

            patch_app.assert_called_once_with(
                app.resolve(),
                config.resolve(),
                managed_home.resolve() / "ChatGPT-original.app",
                False,
                legacy_backup=legacy_backup.resolve(),
            )

    def test_consolidate_legacy_backup_keeps_only_the_canonical_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = root / ".codex" / "ChatGPT-original.app"
            legacy = root / "custom" / "ChatGPT-original.app"
            canonical.mkdir(parents=True)
            legacy.mkdir(parents=True)

            patcher.consolidate_legacy_backup(canonical, legacy)

            self.assertTrue(canonical.exists())
            self.assertFalse(legacy.exists())

    def test_consolidate_legacy_backup_removes_canonical_copy_if_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = root / ".codex" / "ChatGPT-original.app"
            legacy = root / "custom" / "ChatGPT-original.app"
            canonical.mkdir(parents=True)
            legacy.mkdir(parents=True)
            remove_tree = patcher.shutil.rmtree

            def fail_legacy_cleanup(path, **kwargs):
                if path == legacy:
                    raise OSError("simulated legacy cleanup failure")
                return remove_tree(path, **kwargs)

            with mock.patch.object(
                patcher.shutil, "rmtree", side_effect=fail_legacy_cleanup
            ):
                with self.assertRaisesRegex(
                    patcher.PatchError, "canonical copy was removed"
                ):
                    patcher.consolidate_legacy_backup(canonical, legacy)

            self.assertFalse(canonical.exists())
            self.assertTrue(legacy.exists())

    def test_restore_backup_preserves_the_app_when_restore_copy_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            backup = root / "ChatGPT-original.app"
            for bundle, contents in ((app, b"patched"), (backup, b"original")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(contents)

            def incomplete_copy(command, **_kwargs):
                target = Path(command[2])
                target.mkdir(parents=True)
                (target / "partial-copy").write_text("incomplete", encoding="utf-8")
                raise patcher.PatchError("simulated restore failure")

            with mock.patch.object(patcher, "run", side_effect=incomplete_copy):
                with self.assertRaisesRegex(patcher.PatchError, "simulated"):
                    patcher.restore_backup(app, backup)

            self.assertEqual(
                (app / "Contents" / "Resources" / "app.asar").read_bytes(), b"patched"
            )

    def test_restore_backup_preserves_plugins_added_after_the_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            backup = root / "ChatGPT-original.app"
            for bundle, contents in ((app, b"patched"), (backup, b"original")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(contents)
            plugin = app / "Contents" / "Resources" / "plugins" / "my-plugin"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text('{"name":"my-plugin"}', encoding="utf-8")

            def copy_with_ditto_semantics(command, **_kwargs):
                source = Path(command[1])
                destination = Path(command[2])
                shutil.copytree(source, destination, dirs_exist_ok=True)
                return subprocess.CompletedProcess(command, 0, "")

            with mock.patch.object(patcher, "run", side_effect=copy_with_ditto_semantics):
                patcher.restore_backup(app, backup)

            self.assertEqual(
                (app / "Contents" / "Resources" / "plugins" / "my-plugin" / "plugin.json").read_text(
                    encoding="utf-8"
                ),
                '{"name":"my-plugin"}',
            )


class SiblingOriginalTests(unittest.TestCase):
    def test_managed_backup_paths_are_siblings_with_non_app_suffixes(self):
        app = Path("/Applications/ChatGPT.app")

        original, previous = patcher.managed_backup_paths(app)

        self.assertEqual(original, Path("/Applications/ChatGPT-original.backup"))
        self.assertEqual(previous, Path("/Applications/ChatGPT-previous.backup"))

        custom = Path("/Users/test/Applications/Codex Preview.app")
        custom_original, custom_previous = patcher.managed_backup_paths(custom)
        self.assertEqual(
            custom_original,
            Path("/Users/test/Applications/Codex Preview-original.backup"),
        )
        self.assertEqual(
            custom_previous,
            Path("/Users/test/Applications/Codex Preview-previous.backup"),
        )

    def test_make_original_backup_replaces_verified_sibling_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            for bundle, contents in ((app, b"new"), (original, b"old")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(contents)
                with (bundle / "Contents" / "Info.plist").open("wb") as handle:
                    plistlib.dump(
                        {
                            "CFBundleShortVersionString": "26.715.72359",
                            "CFBundleVersion": "5718",
                        },
                        handle,
                    )

            def copy_bundle(command, **_kwargs):
                shutil.copytree(Path(command[1]), Path(command[2]))
                return subprocess.CompletedProcess(command, 0, "")

            with (
                mock.patch.object(patcher, "run", side_effect=copy_bundle),
                mock.patch.object(patcher, "contains_marker", return_value=False),
                mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
                mock.patch.object(patcher, "asar_integrity_hash", return_value="hash"),
            ):
                result = patcher.make_original_backup(app, original)

            self.assertEqual(result, original)
            self.assertEqual(
                (original / "Contents" / "Resources" / "app.asar").read_bytes(),
                b"new",
            )
            self.assertEqual(list(root.glob(".ChatGPT-original.*")), [])

    def test_ensure_original_backup_migrates_codex_home_then_removes_legacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "Applications" / "ChatGPT.app"
            original = app.with_name("ChatGPT-original.backup")
            legacy = root / ".codex" / "ChatGPT-original.app"
            app.mkdir(parents=True)
            legacy.mkdir(parents=True)

            def create_original(_source, destination):
                destination.mkdir()
                return destination

            with (
                mock.patch.object(
                    patcher, "contains_marker", return_value=True
                ),
                mock.patch.object(
                    patcher, "validate_original_source", return_value=legacy
                ) as validate,
                mock.patch.object(
                    patcher, "make_original_backup", side_effect=create_original
                ) as make_original,
            ):
                result = patcher.ensure_original_backup(
                    app,
                    original,
                    reapply_from=None,
                    legacy_backups=(legacy,),
                )

            self.assertEqual(result, original)
            self.assertEqual(
                validate.call_args_list,
                [mock.call(app, legacy.resolve()), mock.call(app, original)],
            )
            make_original.assert_called_once_with(legacy.resolve(), original)
            self.assertFalse(legacy.exists())
            self.assertTrue(original.exists())

    def test_legacy_cleanup_failure_keeps_verified_sibling_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            legacy = root / ".codex" / "ChatGPT-original.app"
            app.mkdir()
            legacy.mkdir(parents=True)

            def create_original(_source, destination):
                destination.mkdir()
                return destination

            with (
                mock.patch.object(patcher, "contains_marker", return_value=True),
                mock.patch.object(
                    patcher, "validate_original_source", return_value=legacy
                ),
                mock.patch.object(
                    patcher, "make_original_backup", side_effect=create_original
                ),
                mock.patch.object(
                    patcher.shutil,
                    "rmtree",
                    side_effect=OSError("permission denied"),
                ),
            ):
                with self.assertRaisesRegex(
                    patcher.PatchError,
                    "legacy original backup could not be removed",
                ):
                    patcher.ensure_original_backup(
                        app,
                        original,
                        reapply_from=None,
                        legacy_backups=(legacy,),
                    )

            self.assertTrue(original.exists())
            self.assertTrue(legacy.exists())

    def test_unpatched_update_replaces_stale_original_from_live_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            app.mkdir()
            original.mkdir()

            with (
                mock.patch.object(patcher, "contains_marker", return_value=False),
                mock.patch.object(
                    patcher,
                    "validate_original_source",
                    side_effect=[patcher.PatchError("does not match"), original],
                ),
                mock.patch.object(
                    patcher, "make_original_backup", return_value=original
                ) as make_original,
            ):
                result = patcher.ensure_original_backup(
                    app,
                    original,
                    reapply_from=None,
                    legacy_backups=(),
                )

            self.assertEqual(result, original)
            make_original.assert_called_once_with(app, original)

    def test_reapply_from_seeds_sibling_without_deleting_external_source(self):
        app = Path("/Applications/ChatGPT.app")
        original = Path("/Applications/ChatGPT-original.backup")
        external = Path("/Volumes/Recovery/ChatGPT-clean.app")

        with (
            mock.patch.object(patcher, "contains_marker", return_value=True),
            mock.patch.object(
                patcher, "validate_original_source", return_value=external
            ) as validate,
            mock.patch.object(
                patcher, "make_original_backup", return_value=original
            ) as make_original,
            mock.patch.object(patcher.shutil, "rmtree") as remove,
        ):
            result = patcher.ensure_original_backup(
                app,
                original,
                reapply_from=external,
                legacy_backups=(),
            )

        self.assertEqual(result, original)
        self.assertEqual(validate.call_args_list[-1], mock.call(app, original))
        make_original.assert_called_once_with(external, original)
        remove.assert_not_called()

    def test_original_source_accepts_matching_patched_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            for bundle in (app, original):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(b"asar")
                with (bundle / "Contents" / "Info.plist").open("wb") as handle:
                    plistlib.dump(
                        {
                            "CFBundleShortVersionString": "26.715.72359",
                            "CFBundleVersion": "5718",
                        },
                        handle,
                    )

            with (
                mock.patch.object(
                    patcher,
                    "contains_marker",
                    side_effect=lambda path: path
                    == app / "Contents" / "Resources" / "app.asar",
                ),
                mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
                mock.patch.object(patcher, "asar_integrity_hash", return_value="hash"),
            ):
                self.assertEqual(
                    patcher.validate_original_source(app, original),
                    original,
                )


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
            ), mock.patch.object(patcher, "asar_header_hash", return_value="hash"), mock.patch.object(
                patcher, "asar_integrity_hash", return_value="hash"
            ):
                self.assertEqual(patcher.validate_reapply_source(app, backup), backup)

    def test_reapply_source_rejects_corrupt_original_backup(self):
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
                            "ElectronAsarIntegrity": {
                                "Resources/app.asar": {"hash": "expected"}
                            },
                        },
                        handle,
                    )

            with (
                mock.patch.object(
                    patcher,
                    "contains_marker",
                    side_effect=lambda path: path
                    == app / "Contents" / "Resources" / "app.asar",
                ),
                mock.patch.object(
                    patcher,
                    "asar_header_hash",
                    side_effect=lambda path: (
                        "expected"
                        if path == app / "Contents" / "Resources" / "app.asar"
                        else "corrupted"
                    ),
                ),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "backup ASAR"):
                    patcher.validate_reapply_source(app, backup)

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
            ), mock.patch.object(patcher, "asar_header_hash", return_value="hash"), mock.patch.object(
                patcher, "asar_integrity_hash", return_value="hash"
            ):
                with self.assertRaisesRegex(patcher.PatchError, "does not match"):
                    patcher.validate_reapply_source(app, backup)


if __name__ == "__main__":
    unittest.main()
