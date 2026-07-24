import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

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
