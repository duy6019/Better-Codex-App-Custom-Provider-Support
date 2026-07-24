import json
from pathlib import Path
import subprocess
import tempfile
import unittest

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
