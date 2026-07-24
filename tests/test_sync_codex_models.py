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

    def test_embedded_diffs_target_build_5813_bundle_symbols(self):
        self.assertIn("function Qjs(e)", patcher.PICKER_DIFF)
        self.assertIn("tp(`codex-home`", patcher.CENTRAL_DIFF)
        self.assertIn("tp(`codex-home`", patcher.PICKER_DIFF)
        self.assertIn("wQ.jsx", patcher.PICKER_DIFF)
        self.assertIn("yz.Item", patcher.PICKER_DIFF)
        self.assertIn("Ym : void 0", patcher.PICKER_DIFF)
        self.assertIn(
            "(CodexProviderPatchReact = r(o(), 1))",
            patcher.PICKER_DIFF,
        )
        self.assertNotIn("function MO(e)", patcher.PICKER_DIFF)
        self.assertNotIn("Xe(`codex-home`", patcher.CENTRAL_DIFF)

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

    def test_installer_help_describes_reapply_source_as_original_seed(self):
        output = io.StringIO()
        with (
            mock.patch.object(
                patcher.sys,
                "argv",
                ["patch_chatgpt_providers.py", "--help"],
            ),
            redirect_stdout(output),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            patcher.parse_args()

        help_text = output.getvalue()
        self.assertIn("Seed the sibling original", help_text)
        self.assertNotIn("backup paths", help_text)

    def test_installer_source_has_no_patch_failed_naming(self):
        source = Path(patcher.__file__).read_text(encoding="utf-8")
        self.assertNotIn("patch-failed", source)

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
        )[1].split("function Qjs(e)", 1)[0]
        for component in ("Item", "Title", "Separator"):
            self.assertIn(f"yz.{component}", provider_section)
            self.assertNotIn(f"Ly.{component}", provider_section)

    def test_picker_import_hunk_tolerates_added_upstream_initializers(self):
        hunk = patcher.parse_hunks(patcher.PICKER_DIFF)[2]
        diff = "@@ -1,1 +1,1 @@\n" + "\n".join(hunk) + "\n"
        source = """}
var eMs,
  wQ,
  tMs = e(() => {
    ((eMs = c()),
      fd(),
      id(),
      qcs(),
      nss(),
      rss(),
      OAs(),
      Xm(),
      KX(),
      fD(),
      bz(),
      Tos(),
      hcs(),
      ncs(),
      Sos(),
      Pos(),
      kos(),
      fcs(),
      (wQ = J()));
  }),
"""

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "picker.js"
            bundle.write_text(source, encoding="utf-8")

            patcher.apply_unified_diff(bundle, diff)

            patched = bundle.read_text(encoding="utf-8")

        self.assertIn("(CodexProviderPatchReact = r(o(), 1))", patched)


class CurrentBundleTests(unittest.TestCase):
    def write_bundle(self, assets: Path, name: str, markers=()) -> Path:
        bundle = assets / name
        bundle.write_text("\n".join(markers), encoding="utf-8")
        return bundle

    def test_current_patch_bundle_finds_build_5813_app_initial(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            expected = self.write_bundle(
                assets,
                "app-initial-BTphDPeq.js",
                patcher.BUILD_5813_BUNDLE_MARKERS,
            )
            self.write_bundle(
                assets,
                "en-US-localization.js",
                ("composer.intelligenceDropdown.tooltip",),
            )

            self.assertEqual(patcher.current_patch_bundle(assets), expected)

    def test_current_patch_bundle_rejects_missing_build_5813_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            self.write_bundle(
                assets,
                "app-initial-old.js",
                patcher.BUILD_5813_BUNDLE_MARKERS[:-1],
            )

            with self.assertRaisesRegex(
                patcher.PatchError,
                "found 0 out of 1 filename matches",
            ):
                patcher.current_patch_bundle(assets)

    def test_current_patch_bundle_rejects_ambiguous_build_5813_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            for suffix in ("one", "two"):
                self.write_bundle(
                    assets,
                    f"app-initial-{suffix}.js",
                    patcher.BUILD_5813_BUNDLE_MARKERS,
                )

            with self.assertRaisesRegex(
                patcher.PatchError,
                "found 2 out of 2 filename matches",
            ):
                patcher.current_patch_bundle(assets)

    def test_current_patch_bundle_rejects_prefixed_impostor(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            self.write_bundle(
                assets,
                "legacy-app-initial-unexpected.js",
                patcher.BUILD_5813_BUNDLE_MARKERS,
            )

            with self.assertRaisesRegex(
                patcher.PatchError,
                "found 0 out of 0 filename matches",
            ):
                patcher.current_patch_bundle(assets)

    def test_patch_current_bundle_applies_both_diffs_to_one_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "app-initial-current.js"
            bundle.write_text("original\n", encoding="utf-8")

            def apply_marker(path, unified_diff):
                marker = (
                    patcher.PATCH_MARKER.decode()
                    if unified_diff is patcher.CENTRAL_DIFF
                    else "CodexCustomProviderPickerSection"
                )
                path.write_text(
                    path.read_text(encoding="utf-8") + marker + "\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(patcher, "run") as run,
                mock.patch.object(
                    patcher,
                    "apply_unified_diff",
                    side_effect=apply_marker,
                ) as apply,
            ):
                patcher.patch_current_bundle(bundle)

            self.assertEqual(
                apply.call_args_list,
                [
                    mock.call(bundle, patcher.CENTRAL_DIFF),
                    mock.call(bundle, patcher.PICKER_DIFF),
                ],
            )
            self.assertEqual(
                run.call_args_list,
                [
                    mock.call(
                        [
                            "npx",
                            "--yes",
                            patcher.PRETTIER_PACKAGE,
                            "--write",
                            str(bundle),
                        ],
                        label="Preparing the JavaScript bundle",
                    ),
                    mock.call(
                        [
                            "npx",
                            "--yes",
                            patcher.PRETTIER_PACKAGE,
                            "--write",
                            str(bundle),
                        ],
                        label="Formatting the patched JavaScript",
                    ),
                    mock.call(
                        ["node", "--check", str(bundle)],
                        label="Validating the patched JavaScript",
                    ),
                ],
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
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "Applications" / "ChatGPT.app"
            original = root / "Applications" / "ChatGPT-original.backup"
            external = root / ".codex" / "ChatGPT-original.app"
            external.mkdir(parents=True)

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
                    legacy_backups=(external,),
                )

            self.assertEqual(result, original)
            self.assertEqual(validate.call_args_list[-1], mock.call(app, original))
            make_original.assert_called_once_with(external.resolve(), original)
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


class RollbackSnapshotTests(unittest.TestCase):
    def test_previous_snapshot_copies_exact_current_app_and_plugins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            previous = root / "ChatGPT-previous.backup"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            (resources / "app.asar").write_bytes(b"patched")
            plugin = resources / "plugins" / "my-plugin" / "plugin.json"
            plugin.parent.mkdir(parents=True)
            plugin.write_text('{"name":"my-plugin"}', encoding="utf-8")

            def copy_bundle(command, **_kwargs):
                shutil.copytree(Path(command[1]), Path(command[2]))
                return subprocess.CompletedProcess(command, 0, "")

            with (
                mock.patch.object(patcher, "run", side_effect=copy_bundle),
                mock.patch.object(
                    patcher,
                    "validated_bundle_identity",
                    return_value=(("26.715.72359", "5718"), "hash"),
                ),
            ):
                result = patcher.make_previous_snapshot(app, previous)

            self.assertEqual(result, previous)
            self.assertEqual(
                (
                    previous
                    / "Contents"
                    / "Resources"
                    / "plugins"
                    / "my-plugin"
                    / "plugin.json"
                ).read_text(encoding="utf-8"),
                '{"name":"my-plugin"}',
            )

    def test_previous_snapshot_refuses_to_overwrite_recovery_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            previous = root / "ChatGPT-previous.backup"
            app.mkdir()
            previous.mkdir()

            with self.assertRaisesRegex(
                patcher.PatchError, "previous app snapshot already exists"
            ):
                patcher.make_previous_snapshot(app, previous)

    def test_restore_previous_snapshot_reinstalls_exact_previous_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            previous = root / "ChatGPT-previous.backup"
            for bundle, payload in ((app, b"partial"), (previous, b"working")):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(payload)

            def copy_bundle(command, **_kwargs):
                shutil.copytree(Path(command[1]), Path(command[2]))
                return subprocess.CompletedProcess(command, 0, "")

            with (
                mock.patch.object(patcher, "run", side_effect=copy_bundle),
                mock.patch.object(
                    patcher,
                    "validated_bundle_identity",
                    return_value=(("26.715.72359", "5718"), "hash"),
                ),
            ):
                result = patcher.restore_previous_snapshot(app, previous)

            self.assertEqual(result, app)
            self.assertEqual(
                (app / "Contents" / "Resources" / "app.asar").read_bytes(),
                b"working",
            )
            self.assertTrue(previous.exists())

    def test_incomplete_restore_preserves_current_app_and_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            previous = root / "ChatGPT-previous.backup"
            app.mkdir()
            previous.mkdir()

            with (
                mock.patch.object(
                    patcher,
                    "run",
                    side_effect=patcher.PatchError("copy failed"),
                ),
                mock.patch.object(
                    patcher,
                    "validated_bundle_identity",
                    return_value=(("26.715.72359", "5718"), "hash"),
                ),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "copy failed"):
                    patcher.restore_previous_snapshot(app, previous)

            self.assertTrue(app.exists())
            self.assertTrue(previous.exists())

    def test_remove_previous_snapshot_deletes_only_the_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            previous = root / "ChatGPT-previous.backup"
            app.mkdir()
            previous.mkdir()

            patcher.remove_previous_snapshot(previous)

            self.assertTrue(app.exists())
            self.assertFalse(previous.exists())


class PatchTransactionTests(unittest.TestCase):
    def test_main_uses_sibling_original_and_previous_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            config = root / ".codex" / "desktop-model-providers.json"
            app.mkdir()
            args = mock.Mock(
                app=app,
                config=config,
                reapply_from=None,
                overwrite_config=False,
                allow_running=False,
            )
            resolved_app = app.resolve()
            resolved_config = config.resolve()
            original, previous = patcher.managed_backup_paths(resolved_app)

            with (
                mock.patch.object(patcher, "parse_args", return_value=args),
                mock.patch.object(patcher, "stop_target_app_processes"),
                mock.patch.object(
                    patcher,
                    "ensure_original_backup",
                    return_value=original,
                ) as ensure_original,
                mock.patch.object(patcher, "patch_app") as patch_app,
            ):
                self.assertEqual(patcher.main(), 0)

            self.assertEqual(
                ensure_original.call_args.args[:2],
                (resolved_app, original),
            )
            self.assertIsNone(ensure_original.call_args.kwargs["reapply_from"])
            patch_app.assert_called_once_with(
                resolved_app,
                resolved_config,
                original,
                previous,
                False,
            )

    def test_main_stops_before_migration_when_previous_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            config = root / ".codex" / "desktop-model-providers.json"
            previous = app.with_name("ChatGPT-previous.backup")
            app.mkdir()
            previous.mkdir()
            args = mock.Mock(
                app=app,
                config=config,
                reapply_from=None,
                overwrite_config=False,
                allow_running=False,
            )

            with (
                mock.patch.object(patcher, "parse_args", return_value=args),
                mock.patch.object(patcher, "ensure_original_backup") as ensure_original,
                mock.patch.object(patcher, "patch_app"),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                patcher.main()

            ensure_original.assert_not_called()

    def test_build_patched_artifacts_extracts_from_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "ChatGPT-original.backup"
            work = root / "work"
            resources = original / "Contents" / "Resources"
            resources.mkdir(parents=True)
            (resources / "app.asar").write_bytes(b"asar")
            with (original / "Contents" / "Info.plist").open("wb") as handle:
                plistlib.dump(
                    {
                        "ElectronAsarIntegrity": {
                            "Resources/app.asar": {"hash": "hash"}
                        }
                    },
                    handle,
                )
            work.mkdir()
            commands = []

            def stop_after_extract(command, **_kwargs):
                commands.append(command)
                raise patcher.PatchError("stop after extract")

            with mock.patch.object(patcher, "run", side_effect=stop_after_extract):
                with self.assertRaisesRegex(patcher.PatchError, "stop after extract"):
                    patcher.build_patched_artifacts(original, work)

            self.assertEqual(
                commands[0],
                [
                    "npx",
                    "--yes",
                    patcher.ASAR_PACKAGE,
                    "extract",
                    str(resources / "app.asar"),
                    str(work / "app"),
                ],
            )

    def test_patch_app_builds_from_original_before_installing_live_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            previous = root / "ChatGPT-previous.backup"
            config = root / "desktop-model-providers.json"
            for bundle in (app, original):
                resources = bundle / "Contents" / "Resources"
                resources.mkdir(parents=True)
                (resources / "app.asar").write_bytes(b"asar")
                (resources / "app.asar.unpacked").mkdir()
                with (bundle / "Contents" / "Info.plist").open("wb") as handle:
                    plistlib.dump({}, handle)
            patched_asar = root / "patched.asar"
            patched_plist = root / "patched.plist"

            with (
                mock.patch.object(patcher.sys, "platform", "darwin"),
                mock.patch.object(patcher.shutil, "which", return_value="/usr/bin/npx"),
                mock.patch.object(
                    patcher, "ensure_provider_config", return_value="kept"
                ),
                mock.patch.object(
                    patcher, "validate_original_source", return_value=original
                ),
                mock.patch.object(
                    patcher,
                    "validated_bundle_identity",
                    return_value=(("26.715.72359", "5718"), "hash"),
                ),
                mock.patch.object(
                    patcher,
                    "build_patched_artifacts",
                    return_value=(patched_asar, patched_plist),
                ) as build,
                mock.patch.object(patcher, "install_patched_artifacts") as install,
            ):
                patcher.patch_app(app, config, original, previous, False)

            self.assertEqual(build.call_args.args[0], original)
            install.assert_called_once_with(app, previous, patched_asar, patched_plist)

    def test_install_failure_rolls_back_from_previous_not_original(self):
        app = Path("/Applications/ChatGPT.app")
        previous = Path("/Applications/ChatGPT-previous.backup")
        patched_asar = Path("/tmp/patched.asar")
        patched_plist = Path("/tmp/Info.plist")

        with (
            mock.patch.object(patcher, "make_previous_snapshot") as snapshot,
            mock.patch.object(
                patcher,
                "atomic_replace_file",
                side_effect=[None, patcher.PatchError("plist replacement failed")],
            ),
            mock.patch.object(patcher, "restore_previous_snapshot") as restore,
            mock.patch.object(patcher, "remove_previous_snapshot") as remove,
        ):
            with self.assertRaisesRegex(
                patcher.PatchError, "plist replacement failed"
            ):
                patcher.install_patched_artifacts(
                    app, previous, patched_asar, patched_plist
                )

        snapshot.assert_called_once_with(app, previous)
        restore.assert_called_once_with(app, previous)
        remove.assert_called_once_with(previous)

    def test_install_success_removes_previous_after_final_verification(self):
        events = []
        app = Path("/Applications/ChatGPT.app")
        previous = Path("/Applications/ChatGPT-previous.backup")
        patched_asar = Path("/tmp/patched.asar")
        patched_plist = Path("/tmp/Info.plist")

        with (
            mock.patch.object(
                patcher,
                "make_previous_snapshot",
                side_effect=lambda *_args: events.append("snapshot"),
            ),
            mock.patch.object(
                patcher,
                "atomic_replace_file",
                side_effect=lambda *_args: events.append("replace"),
            ),
            mock.patch.object(
                patcher,
                "run",
                side_effect=lambda *_args, **_kwargs: events.append("codesign"),
            ),
            mock.patch.object(patcher, "load_plist", return_value=({}, None)),
            mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
            mock.patch.object(patcher, "asar_integrity_hash", return_value="hash"),
            mock.patch.object(patcher, "contains_marker", return_value=True),
            mock.patch.object(
                patcher,
                "remove_previous_snapshot",
                side_effect=lambda *_args: events.append("remove"),
            ),
        ):
            patcher.install_patched_artifacts(
                app, previous, patched_asar, patched_plist
            )

        self.assertEqual(events[0], "snapshot")
        self.assertEqual(events[-1], "remove")

    def test_install_rollback_failure_retains_previous_snapshot(self):
        app = Path("/Applications/ChatGPT.app")
        previous = Path("/Applications/ChatGPT-previous.backup")
        patched_asar = Path("/tmp/patched.asar")
        patched_plist = Path("/tmp/Info.plist")

        with (
            mock.patch.object(patcher, "make_previous_snapshot"),
            mock.patch.object(
                patcher,
                "atomic_replace_file",
                side_effect=patcher.PatchError("replacement failed"),
            ),
            mock.patch.object(
                patcher,
                "restore_previous_snapshot",
                side_effect=patcher.PatchError("rollback failed"),
            ),
            mock.patch.object(patcher, "remove_previous_snapshot") as remove,
        ):
            with self.assertRaisesRegex(patcher.PatchError, "replacement failed"):
                patcher.install_patched_artifacts(
                    app, previous, patched_asar, patched_plist
                )

        remove.assert_not_called()


class ReapplyTests(unittest.TestCase):
    def test_reapply_source_accepts_matching_clean_original(self):
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
                            "CFBundleShortVersionString": "26.715.31925",
                            "CFBundleVersion": "5551",
                        },
                        handle,
                    )

            with (
                mock.patch.object(patcher, "contains_marker", return_value=False),
                mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
                mock.patch.object(patcher, "asar_integrity_hash", return_value="hash"),
            ):
                self.assertEqual(
                    patcher.validate_original_source(app, original), original
                )

    def test_reapply_source_rejects_original_from_another_app_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "ChatGPT.app"
            original = root / "ChatGPT-original.backup"
            for bundle, build in ((app, "5551"), (original, "5552")):
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

            with (
                mock.patch.object(patcher, "contains_marker", return_value=False),
                mock.patch.object(patcher, "asar_header_hash", return_value="hash"),
                mock.patch.object(patcher, "asar_integrity_hash", return_value="hash"),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "does not match"):
                    patcher.validate_original_source(app, original)


if __name__ == "__main__":
    unittest.main()
