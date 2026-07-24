import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock
import zipfile

import patch_chatgpt_providers as patcher


def completed(command, stdout=""):
    return subprocess.CompletedProcess(command, 0, stdout, "")


class WindowsStoreDiscoveryTests(unittest.TestCase):
    def test_builds_immutable_windows_patch_paths(self):
        paths = patcher.windows_patch_paths(Path("C:/Users/test/AppData/Local"))

        self.assertEqual(
            paths.active,
            Path("C:/Users/test/AppData/Local/Codex/ChatGPTProviderPatch/active"),
        )
        with self.assertRaises(AttributeError):
            paths.root = Path("C:/different")

    def test_discovers_one_store_package_with_manifest_and_asar(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "OpenAI.ChatGPT"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(b"clean")
            (install / "AppxManifest.xml").write_text("<Package />", encoding="utf-8")
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT",
                    "PackageFullName": "OpenAI.ChatGPT_1.2.3.4_x64__8wekyb3d8bbwe",
                    "PackageFamilyName": "OpenAI.ChatGPT_8wekyb3d8bbwe",
                    "Version": "1.2.3.4",
                    "Architecture": "X64",
                    "InstallLocation": str(install),
                }
            )
            result = patcher.discover_windows_store_package(
                command_runner=lambda command: completed(command, payload)
            )
        self.assertEqual(result.asar_path, install / "resources" / "app.asar")

    def test_rejects_zero_or_multiple_store_packages(self):
        for stdout in ("", json.dumps([{"Name": "OpenAI.ChatGPT"}] * 2)):
            with self.subTest(stdout=stdout):
                with self.assertRaisesRegex(patcher.PatchError, "exactly one"):
                    patcher.discover_windows_store_package(
                        command_runner=lambda command, value=stdout: completed(command, value)
                    )

    def test_sdk_preflight_requires_both_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "MakeAppx.exe").write_bytes(b"")
            with self.assertRaisesRegex(patcher.PatchError, "SignTool"):
                patcher.find_windows_sdk_tools(search_roots=(root,))

    def test_sdk_preflight_rejects_directory_named_makeappx(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "MakeAppx.exe").mkdir()
            (root / "SignTool.exe").write_bytes(b"")

            with self.assertRaisesRegex(patcher.PatchError, "MakeAppx"):
                patcher.find_windows_sdk_tools(search_roots=(root,))

    def test_sdk_preflight_scans_later_roots_for_a_complete_tool_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            incomplete_root = base / "incomplete"
            complete_root = base / "complete"
            incomplete_root.mkdir()
            complete_root.mkdir()
            (incomplete_root / "MakeAppx.exe").write_bytes(b"")
            (complete_root / "MakeAppx.exe").write_bytes(b"")
            (complete_root / "SignTool.exe").write_bytes(b"")

            tools = patcher.find_windows_sdk_tools(
                search_roots=(incomplete_root, complete_root)
            )

            self.assertEqual(tools.makeappx, complete_root / "MakeAppx.exe")
            self.assertEqual(tools.signtool, complete_root / "SignTool.exe")


class WindowsPackageBuildTests(unittest.TestCase):
    def test_custom_identity_uses_the_local_certificate_subject(self):
        identity = patcher.windows_package_identity(
            "OpenAI.ChatGPT", "1.2.3.4", "CN=Codex Provider Patch"
        )

        self.assertEqual(identity.name, "OpenAI.ChatGPT.CodexPatch")
        self.assertEqual(identity.publisher, "CN=Codex Provider Patch")
        self.assertEqual(identity.version, "1.2.3.4")

    def test_manifest_rewrite_changes_only_identity_fields(self):
        source = (
            '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
            '<Identity Name="OpenAI.ChatGPT" Publisher="CN=Store" Version="1.2.3.4" />'
            '<Properties><DisplayName>ChatGPT</DisplayName></Properties></Package>'
        )

        updated = patcher.rewrite_windows_manifest_identity(
            source,
            patcher.WindowsPackageIdentity(
                "OpenAI.ChatGPT.CodexPatch", "CN=Codex Provider Patch", "1.2.3.4"
            ),
        )

        self.assertIn('Name="OpenAI.ChatGPT.CodexPatch"', updated)
        self.assertIn('Publisher="CN=Codex Provider Patch"', updated)
        self.assertIn('<DisplayName>ChatGPT</DisplayName>', updated)

    def test_certificate_setup_uses_only_public_certificate_material(self):
        commands = []
        certificate = patcher.windows_signing_certificate(
            lambda command: commands.append(command)
            or completed(command, '{"Subject":"CN=Codex Provider Patch","Thumbprint":"ABC"}')
        )

        self.assertEqual(
            certificate,
            patcher.WindowsSigningCertificate("CN=Codex Provider Patch", "ABC"),
        )
        script = commands[0][-1]
        self.assertIn("New-SelfSignedCertificate", script)
        self.assertIn("Export-Certificate", script)
        self.assertIn("Cert:\\LocalMachine\\TrustedPeople", script)
        self.assertNotIn("Export-PfxCertificate", script)

    def test_certificate_setup_rejects_failed_powershell_with_stale_json(self):
        command = ["powershell.exe", "-NoProfile"]

        with self.assertRaisesRegex(
            patcher.PatchError, "Could not create or trust"
        ):
            patcher.windows_signing_certificate(
                lambda _: subprocess.CompletedProcess(
                    command,
                    1,
                    '{"Subject":"CN=Codex Provider Patch","Thumbprint":"ABC"}',
                    "certificate import failed",
                )
            )

    def test_marked_original_stops_before_makeappx(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            (original / "resources").mkdir(parents=True)
            (original / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            (original / "AppxManifest.xml").write_text("<Package />", encoding="utf-8")
            package = patcher.WindowsStorePackage(
                "OpenAI.ChatGPT", "full", "family", "1.2.3.4", "X64",
                original, original / "AppxManifest.xml", original / "resources" / "app.asar",
            )
            tools = patcher.WindowsToolPaths(root / "MakeAppx.exe", root / "SignTool.exe")
            certificate = patcher.WindowsSigningCertificate("CN=Patch", "thumbprint")
            commands = []

            with self.assertRaisesRegex(patcher.PatchError, "already patched"):
                patcher.build_windows_patched_msix(
                    package, original, root / "work", tools, certificate,
                    command_runner=lambda command: commands.append(command),
                )

        self.assertEqual(commands, [])

    def test_build_packages_signs_and_verifies_after_asar_patch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout = root / "original"
            (layout / "resources").mkdir(parents=True)
            (layout / "resources" / "app.asar").write_bytes(b"clean")
            (layout / "AppxManifest.xml").write_text(
                '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                '<Identity Name="OpenAI.ChatGPT" Publisher="CN=Store" Version="1.2.3.4" />'
                '</Package>', encoding="utf-8"
            )
            package = patcher.WindowsStorePackage(
                "OpenAI.ChatGPT", "full", "family", "1.2.3.4", "X64",
                layout, layout / "AppxManifest.xml", layout / "resources" / "app.asar",
            )
            tools = patcher.WindowsToolPaths(root / "MakeAppx.exe", root / "SignTool.exe")
            certificate = patcher.WindowsSigningCertificate("CN=Patch", "thumbprint")
            commands = []

            def command_runner(command):
                commands.append(command)
                if command[1:3] == ["--yes", patcher.ASAR_PACKAGE] and command[3] == "extract":
                    assets = Path(command[5]) / "webview" / "assets"
                    assets.mkdir(parents=True)
                    (assets / "app-initial-test.js").write_text("clean", encoding="utf-8")
                elif command[1:3] == ["--yes", patcher.ASAR_PACKAGE] and command[3] == "pack":
                    bundle = Path(command[4]) / "webview" / "assets" / "app-initial-test.js"
                    self.assertIn(patcher.PATCH_MARKER.decode(), bundle.read_text(encoding="utf-8"))
                    Path(command[5]).write_bytes(b"packed" + patcher.PATCH_MARKER)
                return completed(command)

            def mark_bundle(bundle):
                bundle.write_text(patcher.PATCH_MARKER.decode(), encoding="utf-8")

            with mock.patch.object(patcher, "current_patch_bundle", side_effect=lambda assets: assets / "app-initial-test.js"):
                with mock.patch.object(patcher, "patch_current_bundle", side_effect=mark_bundle):
                    result = patcher.build_windows_patched_msix(
                        package, layout, root / "work", tools, certificate,
                        command_runner=command_runner,
                    )

        self.assertEqual(result, root / "work" / "ChatGPT-CodexPatch.msix")
        self.assertEqual(commands[-3:], [
            [str(tools.makeappx), "pack", "/d", str(root / "work" / "layout"), "/p", str(root / "work" / "ChatGPT-CodexPatch.msix")],
            [str(tools.signtool), "sign", "/fd", "SHA256", "/sha1", "thumbprint", "/s", "My", str(root / "work" / "ChatGPT-CodexPatch.msix")],
            [str(tools.signtool), "verify", "/pa", "/v", str(root / "work" / "ChatGPT-CodexPatch.msix")],
        ])


class WindowsRollbackTests(unittest.TestCase):
    def _store_package(self, root, *, asar=b"clean", package_full_name=None):
        install = root / "store"
        (install / "resources").mkdir(parents=True)
        (install / "resources" / "app.asar").write_bytes(asar)
        (install / "AppxManifest.xml").write_text(
            '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
            '<Identity Name="OpenAI.ChatGPT" Publisher="CN=Store" Version="1.2.3.4" />'
            "</Package>",
            encoding="utf-8",
        )
        return patcher.WindowsStorePackage(
            "OpenAI.ChatGPT",
            package_full_name
            or "OpenAI.ChatGPT_1.2.3.4_x64__8wekyb3d8bbwe",
            "OpenAI.ChatGPT_8wekyb3d8bbwe",
            "1.2.3.4",
            "X64",
            install,
            install / "AppxManifest.xml",
            install / "resources" / "app.asar",
        )

    def _installed_payload(self, root, *, version="1.2.3.4"):
        install = root / f"installed-{version}"
        (install / "resources").mkdir(parents=True)
        (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
        return json.dumps(
            {
                "Name": "OpenAI.ChatGPT.CodexPatch",
                "PackageFullName": (
                    f"OpenAI.ChatGPT.CodexPatch_{version}_x64__8wekyb3d8bbwe"
                ),
                "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
                "Publisher": "CN=Codex Provider Patch",
                "Version": version,
                "InstallLocation": str(install),
            }
        )

    def test_ensure_windows_original_replaces_only_after_clean_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._store_package(root)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "sentinel").write_text("old", encoding="utf-8")
            (paths.active / "ChatGPT-CodexPatch.msix").parent.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"active")
            with mock.patch.object(
                patcher, "current_patch_bundle", return_value=Path("bundle.js")
            ):
                result = patcher.ensure_windows_original(
                    package,
                    paths,
                    command_runner=lambda command: completed(command),
                )
            self.assertEqual(result, paths.original)
            self.assertFalse((paths.original / "sentinel").exists())
            original_metadata = json.loads(
                (paths.original / "package.json").read_text()
            )
            self.assertEqual(
                original_metadata["store_package_full_name"],
                package.package_full_name,
            )
            self.assertEqual(original_metadata["source_version"], package.version)
            self.assertEqual(
                (paths.active / "ChatGPT-CodexPatch.msix").read_bytes(), b"active"
            )

    def test_ensure_windows_original_rejects_marked_source_without_touching_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._store_package(root, asar=patcher.PATCH_MARKER)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "sentinel").write_text("old", encoding="utf-8")
            (paths.active / "ChatGPT-CodexPatch.msix").parent.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"active")
            with self.assertRaisesRegex(patcher.PatchError, "already patched"):
                patcher.ensure_windows_original(package, paths)
            self.assertEqual(
                (paths.original / "sentinel").read_text(encoding="utf-8"), "old"
            )
            self.assertEqual(
                (paths.active / "ChatGPT-CodexPatch.msix").read_bytes(), b"active"
            )

    def test_ensure_windows_original_rejects_unsupported_extracted_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._store_package(root)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "sentinel").write_text("old", encoding="utf-8")
            (paths.active / "ChatGPT-CodexPatch.msix").parent.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"active")

            def runner(command):
                extracted = Path(command[-1])
                assets = extracted / "webview" / "assets"
                assets.mkdir(parents=True)
                (assets / "app-initial-unsupported.js").write_text(
                    "unsupported", encoding="utf-8"
                )
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "Expected exactly one"):
                patcher.ensure_windows_original(
                    package, paths, command_runner=runner
                )
            self.assertTrue((paths.original / "sentinel").exists())
            self.assertEqual(
                (paths.active / "ChatGPT-CodexPatch.msix").read_bytes(), b"active"
            )

    def test_success_promotes_candidate_and_removes_previous(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"new")
            payload = self._installed_payload(root)
            patcher.deploy_windows_msix(
                candidate,
                paths,
                command_runner=lambda command: completed(
                    command,
                    "[]" if "Select-Object -ExpandProperty PackageFullName" in command[-1]
                    else payload if "ConvertTo-Json" in command[-1] else "",
                ),
            )
            self.assertEqual((paths.active / candidate.name).read_bytes(), b"new")
            self.assertFalse(paths.previous.exists())

    def test_empty_registration_verification_never_promotes_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")

            with self.assertRaisesRegex(patcher.PatchError, "registration was not found"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=lambda command: completed(command),
                )

            self.assertFalse(paths.active.exists())

    def test_deployment_filters_custom_processes_and_verifies_installed_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"new")
            calls = []
            payload = self._installed_payload(Path(temporary))

            patcher.deploy_windows_msix(
                candidate,
                paths,
                command_runner=lambda command: calls.append(command)
                or completed(
                    command,
                    "[]" if "Select-Object -ExpandProperty PackageFullName" in command[-1]
                    else payload if "ConvertTo-Json" in command[-1] else "",
                ),
            )

            install_script = next(command[-1] for command in calls if "Add-AppxPackage" in command[-1])
            self.assertIn("OpenAI.ChatGPT.CodexPatch", install_script)
            self.assertLess(
                install_script.index("ExecutablePath.StartsWith"),
                install_script.index("Add-AppxPackage"),
            )
            verification_script = next(
                command[-1]
                for command in calls
                if "ConvertTo-Json" in command[-1]
                and patcher.PATCH_MARKER.decode() in command[-1]
            )
            self.assertIn("Get-AppxPackage", verification_script)
            self.assertIn("if ($packages.Count -ne 1)", verification_script)
            self.assertIn(patcher.PATCH_MARKER.decode(), verification_script)

    def test_unverified_failed_deployment_retains_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            paths.active.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "Add-AppxPackage" in command[-1]:
                    raise patcher.PatchError("deployment failed")
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "deployment failed"):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertTrue(paths.previous.exists())
            self.assertTrue(any("Add-AppxPackage" in command[-1] for command in calls[1:]))

    def test_ambiguous_add_failure_preserves_snapshot_without_removing_package(self):
        """A registration that appears after the baseline is not ours to remove."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            previous_full_name = (
                "OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe"
            )
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": previous_full_name,
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Previous",
                        "source_version": "1.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=Candidate" Version="2.0.0.0" />'
                    "</Package>",
                )
            calls = []

            def runner(command):
                script = command[-1]
                calls.append(script)
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "Add-AppxPackage" in script and "previous.msix" not in script:
                    # This models a same-name registration appearing after the
                    # baseline but before PowerShell reaches Add-AppxPackage.
                    raise patcher.PatchError("unmanaged package is already registered")
                return completed(command)

            with self.assertRaisesRegex(
                patcher.PatchError, "candidate registration is ambiguous"
            ):
                patcher.deploy_windows_msix(
                    candidate, paths, command_runner=runner
                )

            self.assertFalse(any("Remove-AppxPackage" in script for script in calls))
            self.assertFalse(
                any(
                    "Add-AppxPackage" in script and "previous.msix" in script
                    for script in calls
                )
            )
            self.assertTrue(paths.previous.exists())

    def test_unusable_rollback_artifact_reports_and_preserves_previous_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            paths.active.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "Add-AppxPackage" in command[-1]:
                    (paths.previous / "ChatGPT-CodexPatch.msix").unlink()
                    raise patcher.PatchError("deployment failed")
                return completed(command)

            with self.assertRaisesRegex(
                patcher.PatchError, re.escape(str(paths.previous.resolve()))
            ):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertTrue(paths.previous.exists())

    def test_missing_snapshot_during_recovery_does_not_delete_prior_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            paths.active.mkdir(parents=True)
            active_msix = paths.active / "ChatGPT-CodexPatch.msix"
            active_msix.write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "Add-AppxPackage" in command[-1]:
                    shutil.rmtree(paths.previous)
                    raise patcher.PatchError("deployment failed")
                return completed(command)

            with self.assertRaisesRegex(
                patcher.PatchError, re.escape(str(paths.previous.resolve()))
            ):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertEqual(active_msix.read_bytes(), b"previous")

    def test_failed_first_promotion_removes_registered_custom_full_name_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            install = root / "installed-custom"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                    ),
                    "PackageFamilyName": (
                        "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                    ),
                    "Publisher": "CN=Codex Provider Patch",
                    "Version": "1.2.3.4",
                    "InstallLocation": str(install),
                }
            )
            calls = []

            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "ConvertTo-Json" in command[-1]:
                    return completed(command, payload)
                return completed(command)

            with mock.patch.object(
                patcher,
                "promote_windows_active",
                side_effect=patcher.PatchError("promotion failed"),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "promotion failed"):
                    patcher.deploy_windows_msix(
                        candidate, paths, command_runner=runner
                    )

            remove_script = next(
                command[-1]
                for command in calls
                if "Remove-AppxPackage" in command[-1]
            )
            self.assertIn("PackageFullName -eq", remove_script)
            self.assertNotIn("Get-AppxPackage -Package", remove_script)
            self.assertFalse(paths.active.exists())

    def test_snapshot_and_promotion_preserve_identity_and_digest_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "package.json").write_text(
                json.dumps(
                    {
                        "name": "OpenAI.ChatGPT",
                        "store_package_full_name": "store-full-name",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            paths.active.mkdir()
            old_msix = paths.active / "old.msix"
            old_msix.write_bytes(b"old")

            self.assertEqual(patcher.snapshot_windows_active(paths), paths.previous)
            self.assertEqual((paths.previous / old_msix.name).read_bytes(), b"old")

            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            patcher.promote_windows_active(
                candidate,
                paths,
                metadata={"custom_package_full_name": "custom-full-name"},
            )

            metadata = json.loads((paths.active / "package.json").read_text())
            self.assertEqual(metadata["custom_package_full_name"], "custom-full-name")
            self.assertEqual(metadata["store_package_full_name"], "store-full-name")
            self.assertEqual(metadata["source_version"], "1.2.3.4")
            self.assertEqual(
                metadata["candidate_sha256"],
                hashlib.sha256(b"candidate").hexdigest(),
            )

    def test_verified_recovery_restores_active_then_removes_previous(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            installed = root / "installed-custom"
            (installed / "resources").mkdir(parents=True)
            (installed / "resources" / "app.asar").write_bytes(
                patcher.PATCH_MARKER
            )
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                    ),
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
                    "Publisher": "CN=Codex Provider Patch",
                    "Version": "1.2.3.4",
                    "InstallLocation": str(installed),
                }
            )
            calls = []

            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "ConvertTo-Json" in command[-1]:
                    return completed(command, payload)
                return completed(command)

            with mock.patch.object(
                patcher,
                "promote_windows_active",
                side_effect=patcher.PatchError("deployment failed"),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "deployment failed"):
                    patcher.deploy_windows_msix(
                        candidate, paths, command_runner=runner
                    )

            self.assertEqual(
                (paths.active / "previous.msix").read_bytes(), b"previous"
            )
            self.assertFalse(paths.previous.exists())
            rollback_verification = next(
                command[-1]
                for command in reversed(calls)
                if "ConvertTo-Json" in command[-1]
            )
            self.assertIn(
                "PackageFullName -eq "
                "'OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe'",
                rollback_verification,
            )

    def test_recovery_add_requires_empty_custom_registration_not_removed_previous(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            old_full_name = (
                "OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe"
            )
            old_family_name = "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
            paths.active.mkdir(parents=True)
            previous_msix = paths.active / "previous.msix"
            previous_msix.write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": old_full_name,
                        "custom_package_family_name": old_family_name,
                        "custom_package_publisher": "CN=Previous",
                        "source_version": "1.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=Candidate" Version="2.0.0.0" />'
                    "</Package>",
                )
            candidate_full_name = (
                "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate"
            )
            candidate_family_name = "OpenAI.ChatGPT.CodexPatch_candidate"
            old_install = root / "installed-previous"
            candidate_install = root / "installed-candidate"
            for install in (old_install, candidate_install):
                (install / "resources").mkdir(parents=True)
                (install / "resources" / "app.asar").write_bytes(
                    patcher.PATCH_MARKER
                )
            registrations = {old_full_name}
            add_scripts = []

            def payload(
                full_name, family_name, publisher, version, install_location
            ):
                return json.dumps(
                    {
                        "Name": "OpenAI.ChatGPT.CodexPatch",
                        "PackageFullName": full_name,
                        "PackageFamilyName": family_name,
                        "Publisher": publisher,
                        "Version": version,
                        "InstallLocation": str(install_location),
                    }
                )

            def runner(command):
                script = command[-1]
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    matching = (
                        [candidate_full_name]
                        if candidate_full_name in registrations
                        else []
                    )
                    return completed(command, json.dumps(matching))
                if "Remove-AppxPackage" in script:
                    self.assertIn(candidate_full_name, script)
                    registrations.discard(candidate_full_name)
                    return completed(command)
                if "Add-AppxPackage" in script:
                    add_scripts.append(script)
                    is_rollback = "previous.msix" in script
                    if "$customMatches.Count -ne 1" in script:
                        required = old_full_name if is_rollback else old_full_name
                        if required not in registrations:
                            raise patcher.PatchError(
                                "PowerShell exact-existing precondition failed"
                            )
                    if "$existing.Count -ne 0" in script and registrations:
                        raise patcher.PatchError(
                            "PowerShell empty-registration precondition failed"
                        )
                    if is_rollback:
                        registrations.add(old_full_name)
                        return completed(command)
                    registrations.discard(old_full_name)
                    registrations.add(candidate_full_name)
                    return completed(command)
                if "ConvertTo-Json" in script:
                    if "Version.ToString() -eq '2.0.0.0'" in script:
                        if candidate_full_name not in registrations:
                            raise patcher.PatchError("candidate is not registered")
                        return completed(
                            command,
                            payload(
                                candidate_full_name,
                                candidate_family_name,
                                "CN=Candidate",
                                "2.0.0.0",
                                candidate_install,
                            ),
                        )
                    if old_full_name not in registrations:
                        raise patcher.PatchError("previous is not registered")
                    return completed(
                        command,
                        payload(
                            old_full_name,
                            old_family_name,
                            "CN=Previous",
                            "1.0.0.0",
                            old_install,
                        ),
                    )
                return completed(command)

            with mock.patch.object(
                patcher,
                "promote_windows_active",
                side_effect=patcher.PatchError("deployment failed"),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "^deployment failed$"):
                    patcher.deploy_windows_msix(
                        candidate,
                        paths,
                        command_runner=runner,
                    )

            rollback_script = next(
                script for script in add_scripts if "previous.msix" in script
            )
            self.assertIn("$existing.Count -ne 0", rollback_script)
            self.assertNotIn("$customMatches.Count -ne 1", rollback_script)
            self.assertEqual(registrations, {old_full_name})
            self.assertFalse(paths.previous.exists())

    def test_recovery_add_fails_when_candidate_removal_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            previous_full_name = (
                "OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe"
            )
            candidate_full_name = (
                "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__8wekyb3d8bbwe"
            )
            family_name = "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
            candidate_family_name = "OpenAI.ChatGPT.CodexPatch_candidate"
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": previous_full_name,
                        "custom_package_family_name": family_name,
                        "custom_package_publisher": "CN=Previous",
                        "source_version": "1.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=Candidate" Version="2.0.0.0" />'
                    "</Package>",
                )
            installed = root / "installed-candidate"
            (installed / "resources").mkdir(parents=True)
            (installed / "resources" / "app.asar").write_bytes(
                patcher.PATCH_MARKER
            )
            candidate_payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": candidate_full_name,
                    "PackageFamilyName": candidate_family_name,
                    "Publisher": "CN=Candidate",
                    "Version": "2.0.0.0",
                    "InstallLocation": str(installed),
                }
            )
            registrations = {previous_full_name}
            rollback_scripts = []

            def runner(command):
                script = command[-1]
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "Remove-AppxPackage" in script:
                    self.assertIn(candidate_full_name, script)
                    return completed(command)
                if "Add-AppxPackage" in script:
                    if "previous.msix" in script:
                        rollback_scripts.append(script)
                        if "$existing.Count -ne 0" in script and registrations:
                            raise patcher.PatchError(
                                "PowerShell empty-registration precondition failed"
                            )
                        return completed(command)
                    registrations.discard(previous_full_name)
                    registrations.add(candidate_full_name)
                    return completed(command)
                if "ConvertTo-Json" in script:
                    return completed(command, candidate_payload)
                return completed(command)

            with mock.patch.object(
                patcher,
                "promote_windows_active",
                side_effect=patcher.PatchError("promotion failed"),
            ):
                with self.assertRaisesRegex(
                    patcher.PatchError,
                    re.escape(str(paths.previous.resolve())),
                ):
                    patcher.deploy_windows_msix(
                        candidate,
                        paths,
                        command_runner=runner,
                    )

            self.assertEqual(registrations, {candidate_full_name})
            self.assertEqual(len(rollback_scripts), 1)
            self.assertIn("$existing.Count -ne 0", rollback_scripts[0])
            self.assertTrue(paths.previous.exists())

    def test_recovery_verifies_against_previous_not_new_store_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "package.json").write_text(
                json.dumps(
                    {
                        "name": "OpenAI.ChatGPT",
                        "source_version": "2.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            paths.active.mkdir()
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            payload = self._installed_payload(root, version="1.0.0.0")
            calls = []
            def runner(command):
                calls.append(command)
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "ConvertTo-Json" in command[-1]:
                    return completed(command, payload)
                return completed(command)

            with mock.patch.object(
                patcher,
                "promote_windows_active",
                side_effect=patcher.PatchError("deployment failed"),
            ):
                with self.assertRaisesRegex(patcher.PatchError, "^deployment failed$"):
                    patcher.deploy_windows_msix(
                        candidate, paths, command_runner=runner
                    )

            self.assertFalse(paths.previous.exists())
            self.assertEqual(
                (paths.active / "previous.msix").read_bytes(), b"previous"
            )

    def test_original_validation_uses_default_injected_command_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self._store_package(root)
            paths = patcher.windows_patch_paths(root)

            def runner(command):
                extracted = Path(command[-1])
                assets = extracted / "webview" / "assets"
                assets.mkdir(parents=True)
                (assets / "app-initial-supported.js").write_text(
                    "\n".join(patcher.BUILD_5828_BUNDLE_MARKERS),
                    encoding="utf-8",
                )
                return completed(command)

            with mock.patch.object(
                patcher, "run_windows_command", side_effect=runner
            ) as default_runner:
                patcher.ensure_windows_original(package, paths)

            default_runner.assert_called_once()

    def test_failed_promotion_preserves_displaced_active_if_restore_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "old.msix").write_bytes(b"old")
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            real_replace = patcher.os.replace
            replace_calls = 0

            def replace(source, target):
                nonlocal replace_calls
                if not Path(source).is_dir():
                    return real_replace(source, target)
                replace_calls += 1
                if replace_calls == 1:
                    return real_replace(source, target)
                raise OSError("simulated replace failure")

            with mock.patch.object(patcher.os, "replace", side_effect=replace):
                with self.assertRaisesRegex(patcher.PatchError, "displaced-active"):
                    patcher.promote_windows_active(candidate, paths)

            displaced = list(paths.root.glob(".active-*/displaced-active"))
            self.assertEqual(len(displaced), 1)
            self.assertEqual((displaced[0] / "old.msix").read_bytes(), b"old")

    def test_windows_adapter_writes_config_only_after_verified_deploy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "desktop-model-providers.json"
            package = self._store_package(root)
            tools = patcher.WindowsToolPaths(
                root / "MakeAppx.exe", root / "SignTool.exe"
            )
            certificate = patcher.WindowsSigningCertificate("CN=Patch", "ABC")
            events = []

            def build(_package, _original, work, _tools, _certificate, _runner):
                candidate = work / "candidate.msix"
                candidate.write_bytes(b"candidate")
                events.append("build")
                return candidate

            with (
                mock.patch.object(
                    patcher,
                    "discover_windows_store_package",
                    return_value=package,
                ),
                mock.patch.object(
                    patcher, "find_windows_sdk_tools", return_value=tools
                ),
                mock.patch.object(
                    patcher,
                    "windows_signing_certificate",
                    return_value=certificate,
                ),
                mock.patch.object(patcher, "ensure_windows_original"),
                mock.patch.object(
                    patcher, "build_windows_patched_msix", side_effect=build
                ),
                mock.patch.object(
                    patcher,
                    "deploy_windows_msix",
                    side_effect=lambda *args, **kwargs: events.append("deploy"),
                ),
                mock.patch.object(
                    patcher,
                    "ensure_provider_config",
                    side_effect=lambda *args: events.append("config"),
                ),
            ):
                patcher.patch_windows_store_app(
                    config,
                    False,
                    False,
                    root,
                    command_runner=lambda command: completed(command),
                )

            self.assertEqual(events, ["build", "deploy", "config"])

    def test_default_windows_runner_captures_text_output(self):
        command = ["powershell.exe", "-NoProfile"]
        with mock.patch.object(
            patcher.subprocess,
            "run",
            return_value=completed(command, "{}"),
        ) as subprocess_run:
            result = patcher.run_windows_command(command)

        self.assertEqual(result.stdout, "{}")
        subprocess_run.assert_called_once_with(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_marker_verification_failure_still_removes_exact_registered_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            install = root / "installed-custom"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(b"unmarked")
            package_full_name = (
                "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
            )
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": package_full_name,
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
                    "Publisher": "CN=Codex Provider Patch",
                    "Version": "1.2.3.4",
                    "InstallLocation": str(install),
                }
            )
            calls = []

            def runner(command):
                script = command[-1]
                calls.append(script)
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "Add-AppxPackage" in script:
                    return completed(command)
                if "ConvertTo-Json" in script:
                    if patcher.PATCH_MARKER.decode() in script:
                        raise patcher.PatchError("marker verification failed")
                    return completed(command, payload)
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "marker verification failed"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=runner,
                )

            remove_scripts = [script for script in calls if "Remove-AppxPackage" in script]
            self.assertEqual(len(remove_scripts), 1)
            self.assertIn(f"PackageFullName -eq '{package_full_name}'", remove_scripts[0])

    def test_deployment_refuses_stale_previous_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.previous.mkdir(parents=True)
            (paths.previous / "recovery-evidence").write_text(
                "retain", encoding="utf-8"
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            with self.assertRaisesRegex(patcher.PatchError, "previous"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=lambda command: calls.append(command)
                    or completed(command),
                )

            self.assertEqual(calls, [])
            self.assertTrue((paths.previous / "recovery-evidence").exists())
            self.assertFalse(paths.active.exists())

    def test_pre_add_registration_snapshot_failure_discards_new_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            def runner(command):
                calls.append(command)
                raise patcher.PatchError("candidate snapshot failed")

            with self.assertRaisesRegex(
                patcher.PatchError, "^candidate snapshot failed$"
            ):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=runner,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(
                (paths.active / "previous.msix").read_bytes(), b"previous"
            )
            self.assertFalse(paths.previous.exists())

    def test_update_add_requires_the_known_registration_to_be_the_only_one(self):
        script = patcher._windows_add_script(
            Path("candidate.msix"),
            "OpenAI.ChatGPT.CodexPatch",
            allow_running=False,
            allow_existing=True,
            expected_full_name=(
                "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
            ),
            expected_family_name="OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
            expected_publisher="CN=Codex Provider Patch",
            expected_version="1.2.3.4",
        )

        self.assertIn("$packages.Count -ne 1", script)
        self.assertLess(
            script.index("$packages.Count -ne 1"),
            script.index("ExecutablePath.StartsWith"),
        )
        self.assertLess(
            script.index("$packages.Count -ne 1"),
            script.index("Add-AppxPackage"),
        )

    def test_update_binds_process_and_verification_to_active_custom_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            install = root / "installed-custom"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
                    ),
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
                    "Publisher": "CN=Codex Provider Patch",
                    "Version": "1.2.3.4",
                    "InstallLocation": str(install),
                }
            )
            calls = []

            def runner(command):
                calls.append(command[-1])
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "ConvertTo-Json" in command[-1]:
                    return completed(command, payload)
                return completed(command)

            patcher.deploy_windows_msix(
                candidate,
                paths,
                command_runner=runner,
            )

            install_script = next(script for script in calls if "Add-AppxPackage" in script)
            verification_script = next(
                script
                for script in calls
                if "ConvertTo-Json" in script and patcher.PATCH_MARKER.decode() in script
            )
            self.assertNotIn("Select-Object -First 1", install_script)
            self.assertIn(
                "PackageFullName -eq "
                "'OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe'",
                install_script,
            )
            self.assertNotIn("Select-Object -First 1", verification_script)
            self.assertIn(
                "PackageFullName -eq "
                "'OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe'",
                verification_script,
            )

    def test_update_uses_candidate_version_for_verification_and_active_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.original.mkdir(parents=True)
            (paths.original / "package.json").write_text(
                json.dumps(
                    {
                        "name": "OpenAI.ChatGPT",
                        "store_package_full_name": "store_2.0.0.0",
                        "source_version": "2.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe"
                        ),
                        "custom_package_publisher": "CN=Old Patch",
                        "source_version": "1.0.0.0",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=New Patch" Version="2.0.0.0" />'
                    "</Package>",
                )
            install = root / "installed-candidate"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate"
                    ),
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_candidate",
                    "Publisher": "CN=New Patch",
                    "Version": "2.0.0.0",
                    "InstallLocation": str(install),
                }
            )
            scripts = []

            def runner(command):
                script = command[-1]
                scripts.append(script)
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "ConvertTo-Json" in script:
                    return completed(command, payload)
                return completed(command)

            patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            add_script = next(script for script in scripts if "Add-AppxPackage" in script)
            query_script = next(
                script
                for script in scripts
                if "ConvertTo-Json" in script and patcher.PATCH_MARKER.decode() in script
            )
            self.assertIn(
                "PackageFullName -eq "
                "'OpenAI.ChatGPT.CodexPatch_1.0.0.0_x64__8wekyb3d8bbwe'",
                add_script,
            )
            self.assertIn("Version.ToString() -eq '2.0.0.0'", query_script)
            self.assertIn("Publisher -eq 'CN=New Patch'", query_script)
            self.assertNotIn("Version.ToString() -eq '1.0.0.0'", query_script)
            metadata = json.loads((paths.active / "package.json").read_text())
            self.assertEqual(
                metadata["custom_package_full_name"],
                "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate",
            )
            self.assertEqual(
                metadata["custom_package_family_name"],
                "OpenAI.ChatGPT.CodexPatch_candidate",
            )
            self.assertEqual(metadata["custom_package_publisher"], "CN=New Patch")
            self.assertEqual(metadata["source_version"], "2.0.0.0")

    def test_unverified_add_failure_never_removes_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=Candidate" Version="2.0.0.0" />'
                    "</Package>",
                )
            install = root / "installed-candidate"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(b"unmarked")
            package_full_name = (
                "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate"
            )
            payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": package_full_name,
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_candidate",
                    "Publisher": "CN=Candidate",
                    "Version": "2.0.0.0",
                    "InstallLocation": str(install),
                }
            )
            scripts = []

            def runner(command):
                script = command[-1]
                scripts.append(script)
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "Add-AppxPackage" in script:
                    raise patcher.PatchError("Add-AppxPackage failed after registration")
                if "ConvertTo-Json" in script:
                    return completed(command, payload)
                return completed(command)

            with self.assertRaisesRegex(
                patcher.PatchError, "Add-AppxPackage failed after registration"
            ):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            remove_scripts = [script for script in scripts if "Remove-AppxPackage" in script]
            self.assertEqual(remove_scripts, [])
            self.assertFalse(paths.active.exists())

    def test_registration_verification_rejects_missing_identity_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            install = root / "installed-candidate"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            malformed_payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate"
                    ),
                    "InstallLocation": str(install),
                }
            )

            def runner(command):
                script = command[-1]
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, "[]")
                if "ConvertTo-Json" in script:
                    return completed(command, malformed_payload)
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "PackageFamilyName"):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertFalse(paths.active.exists())

    def test_first_install_rejection_never_removes_preexisting_matching_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            with zipfile.ZipFile(candidate, "w") as package:
                package.writestr(
                    "AppxManifest.xml",
                    '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
                    '<Identity Name="OpenAI.ChatGPT.CodexPatch" '
                    'Publisher="CN=Unmanaged" Version="2.0.0.0" />'
                    "</Package>",
                )
            unmanaged_full_name = (
                "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__unmanaged"
            )
            registration = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": unmanaged_full_name,
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_unmanaged",
                    "Publisher": "CN=Unmanaged",
                    "Version": "2.0.0.0",
                    "InstallLocation": str(root / "unmanaged"),
                }
            )
            scripts = []

            def runner(command):
                script = command[-1]
                scripts.append(script)
                if "Add-AppxPackage" in script:
                    raise patcher.PatchError("unmanaged package is already registered")
                if "Select-Object -ExpandProperty PackageFullName" in script:
                    return completed(command, json.dumps([unmanaged_full_name]))
                if "ConvertTo-Json" in script:
                    return completed(command, registration)
                return completed(command)

            with self.assertRaisesRegex(
                patcher.PatchError, "unmanaged package is already registered"
            ):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertTrue(any("ConvertTo-Json" in script for script in scripts))
            self.assertFalse(
                any("Remove-AppxPackage" in script for script in scripts),
                "recovery must retain a registration that predates Add-AppxPackage",
            )

    def test_registration_verification_rejects_missing_publisher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            install = root / "installed-candidate"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(patcher.PATCH_MARKER)
            malformed_payload = json.dumps(
                {
                    "Name": "OpenAI.ChatGPT.CodexPatch",
                    "PackageFullName": (
                        "OpenAI.ChatGPT.CodexPatch_2.0.0.0_x64__candidate"
                    ),
                    "PackageFamilyName": "OpenAI.ChatGPT.CodexPatch_candidate",
                    "Version": "2.0.0.0",
                    "InstallLocation": str(install),
                }
            )

            def runner(command):
                if "Select-Object -ExpandProperty PackageFullName" in command[-1]:
                    return completed(command, "[]")
                if "ConvertTo-Json" in command[-1]:
                    return completed(command, malformed_payload)
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "Publisher"):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertFalse(paths.active.exists())

    def test_upgrade_rejects_active_metadata_without_package_full_name_before_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps({"custom_package_name": "OpenAI.ChatGPT.CodexPatch"}),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            with self.assertRaisesRegex(patcher.PatchError, "PackageFullName"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=lambda command: calls.append(command)
                    or completed(command),
                )

            self.assertEqual(calls, [])
            self.assertTrue((paths.active / "previous.msix").exists())
            self.assertFalse(paths.previous.exists())

    def test_upgrade_rejects_partial_active_package_full_name_before_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": "OpenAI.ChatGPT.CodexPatch",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            with self.assertRaisesRegex(patcher.PatchError, "PackageFullName"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=lambda command: calls.append(command)
                    or completed(command),
                )

            self.assertEqual(calls, [])
            self.assertTrue((paths.active / "previous.msix").exists())
            self.assertFalse(paths.previous.exists())

    def test_upgrade_rejects_truncated_active_package_full_name_before_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = patcher.windows_patch_paths(root)
            paths.active.mkdir(parents=True)
            (paths.active / "previous.msix").write_bytes(b"previous")
            (paths.active / "package.json").write_text(
                json.dumps(
                    {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        "custom_package_full_name": (
                            "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbw"
                        ),
                        "custom_package_family_name": (
                            "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbw"
                        ),
                        "custom_package_publisher": "CN=Codex Provider Patch",
                        "source_version": "1.2.3.4",
                    }
                ),
                encoding="utf-8",
            )
            candidate = root / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            with self.assertRaisesRegex(patcher.PatchError, "PackageFullName"):
                patcher.deploy_windows_msix(
                    candidate,
                    paths,
                    command_runner=lambda command: calls.append(command)
                    or completed(command),
                )

            self.assertEqual(calls, [])
            self.assertTrue((paths.active / "previous.msix").exists())
            self.assertFalse(paths.previous.exists())

    def test_upgrade_rejects_missing_active_identity_selectors_before_commands(self):
        required = {
            "custom_package_full_name": (
                "OpenAI.ChatGPT.CodexPatch_1.2.3.4_x64__8wekyb3d8bbwe"
            ),
            "custom_package_family_name": "OpenAI.ChatGPT.CodexPatch_8wekyb3d8bbwe",
            "custom_package_publisher": "CN=Codex Provider Patch",
            "source_version": "1.2.3.4",
        }
        for missing_field in required:
            with self.subTest(missing_field=missing_field):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    paths = patcher.windows_patch_paths(root)
                    paths.active.mkdir(parents=True)
                    (paths.active / "previous.msix").write_bytes(b"previous")
                    metadata = {
                        "custom_package_name": "OpenAI.ChatGPT.CodexPatch",
                        **required,
                    }
                    metadata.pop(missing_field)
                    (paths.active / "package.json").write_text(
                        json.dumps(metadata),
                        encoding="utf-8",
                    )
                    candidate = root / "candidate.msix"
                    candidate.write_bytes(b"candidate")
                    calls = []

                    with self.assertRaises(patcher.PatchError):
                        patcher.deploy_windows_msix(
                            candidate,
                            paths,
                            command_runner=lambda command: calls.append(command)
                            or completed(command),
                        )

                    self.assertEqual(calls, [])
                    self.assertTrue((paths.active / "previous.msix").exists())
                    self.assertFalse(paths.previous.exists())


class PlatformDispatchTests(unittest.TestCase):
    def test_win32_dispatches_to_store_adapter_not_macos_bundle(self):
        args = types.SimpleNamespace(
            app=None,
            config=Path("config.json"),
            reapply_from=None,
            overwrite_config=False,
            allow_running=False,
        )
        with (
            mock.patch.object(patcher, "parse_args", return_value=args),
            mock.patch.object(patcher, "patch_windows_store_app") as windows,
            mock.patch.object(patcher, "patch_macos_app") as macos,
            mock.patch.object(patcher.sys, "platform", "win32"),
            mock.patch.dict(patcher.os.environ, {"LOCALAPPDATA": "C:/Temp"}),
        ):
            self.assertEqual(patcher.main(), 0)

        windows.assert_called_once()
        macos.assert_not_called()

    def test_darwin_retains_existing_bundle_adapter(self):
        args = types.SimpleNamespace(
            app=Path("/Applications/ChatGPT.app"),
            config=Path("config.json"),
            reapply_from=None,
            overwrite_config=False,
            allow_running=False,
        )
        with (
            mock.patch.object(patcher, "parse_args", return_value=args),
            mock.patch.object(patcher, "patch_windows_store_app") as windows,
            mock.patch.object(patcher, "patch_macos_app") as macos,
            mock.patch.object(patcher.sys, "platform", "darwin"),
        ):
            self.assertEqual(patcher.main(), 0)

        macos.assert_called_once_with(args)
        windows.assert_not_called()

    def test_win32_rejects_macos_only_path_arguments(self):
        args = types.SimpleNamespace(
            app=Path("C:/ChatGPT.app"),
            config=Path("config.json"),
            reapply_from=None,
            overwrite_config=False,
            allow_running=False,
        )
        with (
            mock.patch.object(patcher, "parse_args", return_value=args),
            mock.patch.object(patcher, "patch_windows_store_app") as windows,
            mock.patch.object(patcher, "patch_macos_app") as macos,
            mock.patch.object(patcher, "fail") as fail,
            mock.patch.object(patcher.sys, "platform", "win32"),
        ):
            self.assertEqual(patcher.main(), 0)

        fail.assert_called_once()
        self.assertIn("macOS", fail.call_args.args[0])
        windows.assert_not_called()
        macos.assert_not_called()

    def test_windows_help_explains_store_sdk_and_no_developer_mode(self):
        stdout = io.StringIO()
        with (
            mock.patch.object(patcher.sys, "platform", "win32"),
            mock.patch.object(patcher.sys, "argv", ["patcher", "--help"]),
            mock.patch("sys.stdout", stdout),
            self.assertRaises(SystemExit),
        ):
            patcher.parse_args()

        help_text = stdout.getvalue()
        self.assertIn("Microsoft Store", help_text)
        self.assertIn("Windows SDK", help_text)
        self.assertIn("Developer Mode is not required", help_text)


class DocumentationTests(unittest.TestCase):
    def test_readme_documents_store_only_refresh_without_developer_mode(self):
        readme = Path(patcher.__file__).with_name("README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Microsoft Store", readme)
        self.assertIn("MakeAppx", readme)
        self.assertIn("SignTool", readme)
        self.assertIn("Developer Mode is not required", readme)
        self.assertIn("run the patcher again", readme)
        self.assertIn("official Store app is not modified", readme)
