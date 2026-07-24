# Windows Store ChatGPT Provider Patch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Patch Microsoft Store ChatGPT on Windows by creating a separately signed MSIX while retaining the macOS patcher and its transactional recovery behavior.

**Architecture:** A Windows Store adapter discovers the protected Store payload, copies it into a verified local `original`, patches a temporary copy, signs a custom-identity MSIX, and promotes it through `active` and `previous` artifacts. The macOS adapter remains the only macOS code path.

**Tech Stack:** Python 3.9+ standard library, `unittest`, PowerShell Appx/PKI cmdlets, Windows SDK (`MakeAppx.exe`, `SignTool.exe`), Node.js `npx`, Electron ASAR.

## Global Constraints

- Support only the Microsoft Store `OpenAI.ChatGPT` package on Windows; do not change macOS bundle behavior.
- Never write inside `WindowsApps`, change its ACLs, or modify the official Store app.
- Do not require Developer Mode. Use a trusted locally generated package-signing certificate and report policy restrictions clearly.
- Use a custom package identity and a publisher equal to the local certificate subject so Store and patched packages coexist.
- Preserve verified `original`, snapshot `previous` before overwriting `active`, recover automatically, and preserve recovery evidence when rollback fails.
- Reject unsupported bundles before changing a working patched package. Keep current strict JavaScript hunk validation.
- Add no Python dependency and test Windows through injected paths, platform values, and command runners.

---

## File structure

- `patch_chatgpt_providers.py`: Store discovery, SDK/certificate checks, MSIX build/sign/deploy, platform dispatch, and transaction state.
- `tests/test_windows_store_patch.py`: Windows Store unit tests using temporary files and fake command results.
- `tests/test_windows_compatibility.py`: existing Windows import/output coverage remains.
- `README.md`: Store-only prerequisites, manual refresh, recovery, and security boundaries.

### Task 1: Discover and preflight a Windows Store payload

**Files:** Modify `patch_chatgpt_providers.py:31-34, 763-823`; create `tests/test_windows_store_patch.py`.

**Interfaces:** Consumes `PatchError` and an injected runner returning `subprocess.CompletedProcess[str]`. Produces immutable `WindowsStorePackage`, `WindowsToolPaths`, `WindowsPatchPaths`, `discover_windows_store_package`, `find_windows_sdk_tools`, and `windows_patch_paths`.

- [ ] **Step 1: Write the failing discovery and tool tests.**

    import json
    from pathlib import Path
    import subprocess
    import tempfile
    import types
    import unittest
    from unittest import mock

    import patch_chatgpt_providers as patcher

    def completed(command, stdout=""):
        return subprocess.CompletedProcess(command, 0, stdout, "")

    def test_discovers_one_store_package_with_manifest_and_asar(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "OpenAI.ChatGPT"
            (install / "resources").mkdir(parents=True)
            (install / "resources" / "app.asar").write_bytes(b"clean")
            (install / "AppxManifest.xml").write_text("<Package />", encoding="utf-8")
            payload = json.dumps({
                "Name": "OpenAI.ChatGPT",
                "PackageFullName": "OpenAI.ChatGPT_1.2.3.4_x64__8wekyb3d8bbwe",
                "PackageFamilyName": "OpenAI.ChatGPT_8wekyb3d8bbwe",
                "Version": "1.2.3.4", "Architecture": "X64",
                "InstallLocation": str(install),
            })
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

- [ ] **Step 2: Run the tests and verify RED.** Run `python -m unittest tests.test_windows_store_patch.WindowsStoreDiscoveryTests -v`. Expected: failures name all three missing interfaces and no test skips on a non-Windows host.

- [ ] **Step 3: Add the smallest discovery/preflight implementation.** Import `dataclasses` and `Sequence` from `typing`, add `WINDOWS_STORE_PACKAGE_NAME = "OpenAI.ChatGPT"`, and add these data types:

    @dataclasses.dataclass(frozen=True)
    class WindowsStorePackage:
        name: str
        package_full_name: str
        package_family_name: str
        version: str
        architecture: str
        install_location: Path
        manifest_path: Path
        asar_path: Path

    @dataclasses.dataclass(frozen=True)
    class WindowsToolPaths:
        makeappx: Path
        signtool: Path

    @dataclasses.dataclass(frozen=True)
    class WindowsPatchPaths:
        root: Path
        original: Path
        active: Path
        previous: Path

    def windows_patch_paths(local_app_data: Path) -> WindowsPatchPaths:
        root = local_app_data / "Codex" / "ChatGPTProviderPatch"
        return WindowsPatchPaths(root, root / "original", root / "active", root / "previous")

`discover_windows_store_package` must invoke `powershell.exe -NoProfile -NonInteractive -Command` with `Get-AppxPackage -Name 'OpenAI.ChatGPT'`, select `Name`, `PackageFullName`, `PackageFamilyName`, `Version`, `Architecture`, and `InstallLocation`, then use `ConvertTo-Json -Compress`. Parse exactly one object. Raise `PatchError` for empty/list output, missing fields, unreadable layout, a missing manifest, or zero/multiple `resources/app.asar` candidates. `find_windows_sdk_tools(search_roots: Sequence[Path])` must find `MakeAppx.exe` and `SignTool.exe` in one directory and name the absent tool before any state mutation.

- [ ] **Step 4: Run GREEN and the Windows regressions.** Run `python -m unittest tests.test_windows_store_patch.WindowsStoreDiscoveryTests tests.test_windows_compatibility -v`. Expected: PASS.

- [ ] **Step 5: Commit the completed unit.** Stage `patch_chatgpt_providers.py` and `tests/test_windows_store_patch.py`, then commit with message `feat: discover Windows Store ChatGPT payload`.

### Task 2: Build and sign a custom-identity MSIX from the verified payload

**Files:** Modify `patch_chatgpt_providers.py:899-1200` and `tests/test_windows_store_patch.py`.

**Interfaces:** Consumes `WindowsStorePackage`, `WindowsToolPaths`, `patch_current_bundle`, `asar_header_hash`, and `contains_marker`. Produces `WindowsPackageIdentity`, `WindowsSigningCertificate`, `windows_signing_certificate`, `rewrite_windows_manifest_identity`, and `build_windows_patched_msix`.

- [ ] **Step 1: Write failing identity, signing, and marker tests.**

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
        self.assertIn("<DisplayName>ChatGPT</DisplayName>", updated)

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
            with mock.patch.object(patcher, "patch_current_bundle"):
                with mock.patch.object(patcher, "contains_marker", return_value=True):
                    patcher.build_windows_patched_msix(
                        package, layout, root / "work", tools, certificate,
                        command_runner=lambda command: commands.append(command),
                    )
        self.assertEqual(commands[-3:], [
            [str(tools.makeappx), "pack", "/d", str(root / "work" / "layout"), "/p", str(root / "work" / "ChatGPT-CodexPatch.msix")],
            [str(tools.signtool), "sign", "/fd", "SHA256", "/sha1", "thumbprint", "/s", "My", str(root / "work" / "ChatGPT-CodexPatch.msix")],
            [str(tools.signtool), "verify", "/pa", "/v", str(root / "work" / "ChatGPT-CodexPatch.msix")],
        ])

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_windows_store_patch.WindowsPackageBuildTests -v`. Expected: missing identity, manifest-rewrite, and package-build interfaces fail.

- [ ] **Step 3: Implement the package pipeline.**

    @dataclasses.dataclass(frozen=True)
    class WindowsPackageIdentity:
        name: str
        publisher: str
        version: str

    @dataclasses.dataclass(frozen=True)
    class WindowsSigningCertificate:
        subject: str
        thumbprint: str

    def windows_package_identity(store_package_name, version, publisher):
        return WindowsPackageIdentity(
            f"{store_package_name}.CodexPatch", publisher, version
        )

Import `xml.etree.ElementTree` and use it in `rewrite_windows_manifest_identity(contents, identity)` to change only `Identity` attributes `Name`, `Publisher`, and `Version`. Reject malformed XML or a missing identity element with `PatchError`; retain application IDs, capabilities, extensions, and resources.

Implement `windows_signing_certificate(command_runner)` to query a reusable current-user Code Signing certificate, create it with `New-SelfSignedCertificate` when absent, export its public certificate, and import that public certificate into `Cert:\\LocalMachine\\TrustedPeople` only if its thumbprint is not trusted. PowerShell must return explicit JSON containing only Subject and Thumbprint. Translate command failures to `PatchError` without exposing private-key material.

`build_windows_patched_msix(package, original_layout, work, tools, certificate, command_runner)` must copy the clean layout to `work / "layout"`, refuse an ASAR containing `PATCH_MARKER`, extract/repack the copied ASAR with the existing ASAR tool, invoke `current_patch_bundle` and `patch_current_bundle`, and confirm the packed result contains the marker. Update an Electron integrity manifest only when the copied Windows payload actually has one. Rewrite `AppxManifest.xml`, package through `MakeAppx`, sign through the current-user `My` certificate store, verify with `SignTool`, and return `work / "ChatGPT-CodexPatch.msix"`. Keep JavaScript mutation exclusively in `patch_current_bundle`.

- [ ] **Step 4: Run GREEN and the patch-context suite.** Run `python -m unittest tests.test_windows_store_patch.WindowsPackageBuildTests tests.test_provider_model_filter_revert -v`. Expected: PASS; command order and pre-package failure paths are asserted.

- [ ] **Step 5: Commit the completed unit.** Stage `patch_chatgpt_providers.py` and `tests/test_windows_store_patch.py`, then commit with message `feat: build signed Windows Store patch package`.

### Task 3: Deploy transactionally with macOS-equivalent backup and rollback

**Files:** Modify `patch_chatgpt_providers.py:780-823, 1200-1575` and `tests/test_windows_store_patch.py`.

**Interfaces:** Consumes `WindowsPatchPaths`, `WindowsStorePackage`, `WindowsPackageIdentity`, and a verified MSIX from `build_windows_patched_msix`. Produces `ensure_windows_original`, `snapshot_windows_active`, `promote_windows_active`, `deploy_windows_msix`, `restore_windows_previous`, and `patch_windows_store_app`.

- [ ] **Step 1: Write failing success and rollback tests using filesystem artifacts.**

    def test_failed_deployment_reinstalls_previous_and_retains_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            paths.active.mkdir(parents=True)
            (paths.active / "ChatGPT-CodexPatch.msix").write_bytes(b"previous")
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"candidate")
            calls = []

            def runner(command):
                calls.append(command)
                if "Add-AppxPackage" in command[-1] and len(calls) == 1:
                    raise patcher.PatchError("deployment failed")
                return completed(command)

            with self.assertRaisesRegex(patcher.PatchError, "deployment failed"):
                patcher.deploy_windows_msix(candidate, paths, command_runner=runner)

            self.assertTrue(paths.previous.exists())
            self.assertTrue(any("Add-AppxPackage" in command[-1] for command in calls[1:]))

    def test_success_promotes_candidate_and_removes_previous(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = patcher.windows_patch_paths(Path(temporary))
            candidate = Path(temporary) / "candidate.msix"
            candidate.write_bytes(b"new")
            patcher.deploy_windows_msix(
                candidate, paths, command_runner=lambda command: completed(command)
            )
            self.assertEqual((paths.active / candidate.name).read_bytes(), b"new")
            self.assertFalse(paths.previous.exists())

Add tests for `ensure_windows_original`: it copies an unmarked Store layout through a staging directory, writes identity metadata only after validation, and leaves the prior `active` artifact untouched when a new Store source is marked or unsupported.

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_windows_store_patch.WindowsRollbackTests -v`. Expected: missing transaction functions fail; success cannot pass before snapshot/promote exists.

- [ ] **Step 3: Implement the artifact state machine.** `ensure_windows_original(package, paths)` must copy `package.install_location` to a sibling staging directory below `paths.root`, validate the manifest, package full name, exactly one unmarked ASAR, and source bundle markers, then atomically replace `paths.original`. Call `atomic_write_json` only after validation to write `original/package.json` with the Store package identity.

Implement `snapshot_windows_active(paths)` to fail when `previous` exists, copy active metadata and the prior MSIX to staging, compare a SHA-256 digest before promotion, then atomically create `previous`. Implement `promote_windows_active(candidate_msix, paths)` through staging rather than deleting `active` first. Its metadata must include custom package full name, Store package full name, source version, and the candidate hash.

`deploy_windows_msix(candidate_msix, paths, command_runner)` must: (1) snapshot active state when present; (2) invoke PowerShell `Add-AppxPackage -Path <candidate> -ForceApplicationShutdown`; (3) query custom package `OpenAI.ChatGPT.CodexPatch`, verify registration and the installed ASAR marker; (4) promote the artifact; and (5) remove `previous` only after all verification passes. Before calling `Add-AppxPackage`, stop only processes whose executable path starts in the custom package's install location; never stop the official Store app process.

On any exception after snapshot, remove the candidate custom package through `Remove-AppxPackage`, reinstall `previous` through `Add-AppxPackage`, verify it, restore on-disk active state, then delete `previous`. If any recovery substep fails, preserve `previous` and raise a message including its absolute path. With no prior active package, recovery removes only the candidate package and leaves no active artifact.

`patch_windows_store_app(config, overwrite_config, allow_running, local_app_data, command_runner)` must complete discovery, SDK, certificate, original-copy, source, ASAR, package, and signing preflight before `deploy_windows_msix`. Call `ensure_provider_config` only after deploy verification succeeds so any Windows failure leaves no new JSON config file.

- [ ] **Step 4: Run GREEN and macOS regression coverage.** Run `python -m unittest tests.test_windows_store_patch -v`, `python -m unittest tests.test_windows_compatibility -v`, then `python -m unittest discover -s tests -v`. Expected: PASS with zero failures and errors.

- [ ] **Step 5: Commit the completed unit.** Stage `patch_chatgpt_providers.py` and `tests/test_windows_store_patch.py`, then commit with message `feat: rollback failed Windows Store patch deployments`.

### Task 4: Route the CLI by platform without changing the macOS flow

**Files:** Modify `patch_chatgpt_providers.py:787-823, 1527-1605`, `tests/test_windows_store_patch.py`, and `tests/test_windows_compatibility.py`.

**Interfaces:** Consumes existing `patch_app` for macOS and `patch_windows_store_app` from Task 3. Produces platform-specific help and a `main()` dispatcher that invokes exactly one adapter.

- [ ] **Step 1: Write failing platform-dispatch tests.**

    def test_win32_dispatches_to_store_adapter_not_macos_bundle(self):
        args = types.SimpleNamespace(
            app=None, config=Path("config.json"), reapply_from=None,
            overwrite_config=False, allow_running=False,
        )
        with mock.patch.object(patcher, "parse_args", return_value=args), \
             mock.patch.object(patcher, "patch_windows_store_app") as windows, \
             mock.patch.object(patcher, "patch_app") as macos, \
             mock.patch.object(patcher.sys, "platform", "win32"), \
             mock.patch.dict(patcher.os.environ, {"LOCALAPPDATA": "C:/Temp"}):
            self.assertEqual(patcher.main(), 0)
        windows.assert_called_once()
        macos.assert_not_called()

    def test_darwin_retains_existing_bundle_adapter(self):
        args = types.SimpleNamespace(
            app=Path("/Applications/ChatGPT.app"), config=Path("config.json"),
            reapply_from=None, overwrite_config=False, allow_running=False,
        )
        with mock.patch.object(patcher, "parse_args", return_value=args), \
             mock.patch.object(patcher, "patch_windows_store_app") as windows, \
             mock.patch.object(patcher, "patch_app") as macos, \
             mock.patch.object(patcher.sys, "platform", "darwin"):
            self.assertEqual(patcher.main(), 0)
        macos.assert_called_once()
        windows.assert_not_called()

Also add a help-output assertion under a patched Windows platform that the copy contains `Microsoft Store`, `Windows SDK`, and `Developer Mode is not required`.

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_windows_store_patch.PlatformDispatchTests -v`. Expected: Windows fails because current `main()` rejects every non-darwin platform.

- [ ] **Step 3: Implement only the boundary refactor.** Make parser description/default guidance platform-aware while retaining `--app` and `--reapply-from` for macOS. On Windows, describe automatic Store discovery and raise `PatchError` when a macOS app/reapply argument is supplied. Extract the present macOS body from `main()` into `patch_macos_app(args)` without changing call ordering. Dispatch as follows:

    if sys.platform == "darwin":
        patch_macos_app(args)
    elif sys.platform == "win32":
        patch_windows_store_app(
            args.config, args.overwrite_config, args.allow_running,
            local_app_data=Path(os.environ["LOCALAPPDATA"]),
        )
    else:
        raise PatchError(
            "This installer supports macOS and Windows Microsoft Store ChatGPT only"
        )

Use `Path.home() / "AppData" / "Local"` only when `LOCALAPPDATA` is missing in a test. Keep `fail`, exit-code handling, and KeyboardInterrupt behavior unchanged.

- [ ] **Step 4: Run GREEN and the complete suite.** Run `python -m unittest tests.test_windows_store_patch.PlatformDispatchTests tests.test_windows_compatibility -v`, then `python -m unittest discover -s tests -v`. Expected: PASS with zero warnings and errors.

- [ ] **Step 5: Commit the completed unit.** Stage `patch_chatgpt_providers.py`, `tests/test_windows_store_patch.py`, and `tests/test_windows_compatibility.py`, then commit with message `feat: route provider patcher to Windows Store installer`.

### Task 5: Document Store-only operation and verify on a real Windows machine

**Files:** Modify `README.md:1-80, 190-245` and `tests/test_windows_store_patch.py`.

**Interfaces:** Consumes the Windows CLI and transaction root from Tasks 1-4. Produces operator instructions distinguishing the untouched Store app from the patched package.

- [ ] **Step 1: Write a failing documentation test.**

    def test_readme_documents_store_only_refresh_without_developer_mode(self):
        readme = Path(patcher.__file__).with_name("README.md").read_text(encoding="utf-8")
        self.assertIn("Microsoft Store", readme)
        self.assertIn("MakeAppx", readme)
        self.assertIn("SignTool", readme)
        self.assertIn("Developer Mode is not required", readme)
        self.assertIn("run the patcher again", readme)
        self.assertIn("official Store app is not modified", readme)

- [ ] **Step 2: Run RED.** Run `python -m unittest tests.test_windows_store_patch.DocumentationTests -v`. Expected: FAIL because the README currently labels the desktop patch macOS-only.

- [ ] **Step 3: Update README requirements, install, updates, and recovery.** Add a separate Windows Store section that says: install ChatGPT from Microsoft Store first; other Windows distributions are unsupported; install the Windows SDK so `MakeAppx.exe` and `SignTool.exe` are available; run elevated once to trust the public certificate and read the Store payload; Developer Mode is not required but policy can block sideloading; the official Store app is not modified; launch the separately installed patched package; after a Store update, run the patcher again; and `original`, `active`, and `previous` are stored in local `ChatGPTProviderPatch` state. Keep all macOS path, signing, backup, and recovery instructions in a separate unchanged section. Do not document an API key or private certificate export.

- [ ] **Step 4: Run GREEN and all automated coverage.** Run `python -m unittest tests.test_windows_store_patch.DocumentationTests -v`, then `python -m unittest discover -s tests -v`. Expected: PASS with zero failures and errors.

- [ ] **Step 5: Perform real Windows acceptance before declaring support.** On Windows 10 version 2004+ or Windows 11 with Microsoft Store ChatGPT and the Windows SDK installed, run `py patch_chatgpt_providers.py`. Confirm: (1) official Store ChatGPT still launches unchanged; (2) custom patched ChatGPT installs, launches, and shows the provider picker; (3) a deliberately blocked Add-AppxPackage call restores the prior patched package; and (4) after a Store update, rerunning the patcher either creates a new patched package or leaves the old package active when strict validation rejects the new payload. Record Windows version, Store package full name, SDK version, and pass/fail only; do not record credentials, certificate thumbprints, or personal paths.

- [ ] **Step 6: Commit the completed unit.** Stage `README.md` and `tests/test_windows_store_patch.py`, then commit with message `docs: explain Windows Store patch lifecycle`.

## Plan self-review

- Spec coverage: Task 1 implements Store-only discovery and preflight; Task 2 implements custom signing and packaging; Task 3 implements the complete `original`/`active`/`previous` recovery model; Task 4 preserves macOS dispatch; Task 5 covers manual operation and device acceptance.
- Placeholder scan: every task names its file, interface, test-first command, expected red/green outcome, required implementation behavior, and commit boundary.
- Type consistency: `WindowsStorePackage`, `WindowsToolPaths`, `WindowsPatchPaths`, `WindowsPackageIdentity`, and deployment functions are defined before later tasks consume them.
