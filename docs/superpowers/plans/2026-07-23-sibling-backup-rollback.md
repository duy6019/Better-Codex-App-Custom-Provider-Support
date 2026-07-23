# Sibling App Backup and Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Store a verified clean original and a transactional previous-state snapshot beside the target app, build every patch from the clean original, and roll back a failed installation to the exact pre-patch app state.

**Architecture:** Derive ChatGPT-original.backup and ChatGPT-previous.backup from the resolved target app path. A verified original manager seeds or migrates the clean source before patch preparation; a separate snapshot/restore layer protects the live app immediately before mutation. The patcher reads source files from the clean original, mutates only the installed app, removes the previous snapshot after success, and restores from it after failure.

**Tech Stack:** Python standard library, unittest/mock, macOS ditto and codesign, Electron ASAR tooling through npx.

## Global Constraints

- Keep ChatGPT-original.backup and ChatGPT-previous.backup beside the resolved target app; do not store managed app backups in CODEX_HOME.
- Keep only ChatGPT.app launchable; managed copies use the .backup suffix.
- Never mutate ChatGPT-original.backup.
- Build every patched ASAR and Info.plist from ChatGPT-original.backup.
- Create and verify ChatGPT-previous.backup after patch preparation and immediately before the first live mutation.
- Roll back from ChatGPT-previous.backup after a post-mutation failure; do not restore from the clean original in that failure path.
- Delete a legacy managed original only after the sibling original has been copied and verified.
- Do not automatically glob-delete existing ChatGPT.patch-failed-*.app bundles.
- Preserve the current uncommitted model-picker namespace changes and plugin-preservation behavior in patch_chatgpt_providers.py and tests/test_sync_codex_models.py.
- Baseline before implementation: python3 -m unittest discover -v passes 25 tests.

---

### Task 1: Derive and manage the clean sibling original

**Files:**
- Modify: patch_chatgpt_providers.py:728-777
- Modify: patch_chatgpt_providers.py:1102-1155
- Modify: patch_chatgpt_providers.py:1210-1243
- Test: tests/test_sync_codex_models.py:276-468
- Test: tests/test_sync_codex_models.py:523-622

**Interfaces:**
- Produces: managed_backup_paths(app: Path) -> tuple[Path, Path]
- Produces: validated_bundle_identity(bundle: Path, label: str) -> tuple[tuple[str, str], str]
- Produces: validate_original_source(app: Path, original: Path) -> Path
- Produces: make_original_backup(source: Path, original: Path) -> Path
- Produces: ensure_original_backup(app: Path, original: Path, *, reapply_from: Path | None, legacy_backups: tuple[Path, ...]) -> Path
- Consumes: contains_marker, load_plist, asar_header_hash, asar_integrity_hash, run

- [ ] **Step 1: Replace the managed-backup tests with failing sibling-path and migration tests**

Add these cases to ManagedBackupTests, replacing expectations that point to .codex/ChatGPT-original.app:

~~~python
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


def test_ensure_original_backup_migrates_codex_home_then_removes_legacy(self):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        app = root / "Applications" / "ChatGPT.app"
        original = app.with_name("ChatGPT-original.backup")
        legacy = root / ".codex" / "ChatGPT-original.app"
        app.mkdir(parents=True)
        legacy.mkdir(parents=True)

        with (
            mock.patch.object(
                patcher, "validate_original_source", return_value=legacy
            ) as validate,
            mock.patch.object(
                patcher, "make_original_backup", return_value=original
            ) as make_original,
            mock.patch.object(patcher.shutil, "rmtree") as remove,
            mock.patch.object(patcher, "contains_marker", return_value=True),
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
            [mock.call(app, legacy), mock.call(app, original)],
        )
        make_original.assert_called_once_with(legacy, original)
        remove.assert_called_once_with(legacy)


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
            mock.patch.object(
                patcher, "validate_original_source", return_value=legacy
            ),
            mock.patch.object(
                patcher, "make_original_backup", side_effect=create_original
            ),
            mock.patch.object(patcher, "contains_marker", return_value=True),
            mock.patch.object(
                patcher.shutil, "rmtree", side_effect=OSError("permission denied")
            ),
        ):
            with self.assertRaisesRegex(
                patcher.PatchError, "legacy original backup could not be removed"
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
~~~

Retain the existing atomic replacement test, rename it to test_make_original_backup_replaces_verified_sibling_original, change its destination to root / "ChatGPT-original.backup", call make_original_backup(app, original), and assert no hidden staging directories remain.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

~~~bash
python3 -m unittest tests.test_sync_codex_models.ManagedBackupTests -v
~~~

Expected: FAIL because managed_backup_paths, validated_bundle_identity, validate_original_source, make_original_backup, and ensure_original_backup do not yet exist, and current tests still expect the Codex-home backup.

- [ ] **Step 3: Add sibling path and bundle identity helpers**

Add managed_backup_paths after effective_codex_home:

~~~python
def managed_backup_paths(app: Path) -> tuple[Path, Path]:
    return (
        app.with_name(f"{app.stem}-original.backup"),
        app.with_name(f"{app.stem}-previous.backup"),
    )


~~~

Add validated_bundle_identity immediately after asar_integrity_hash:

~~~python
def validated_bundle_identity(
    bundle: Path, label: str
) -> tuple[tuple[str, str], str]:
    info_path = bundle / "Contents" / "Info.plist"
    asar_path = bundle / "Contents" / "Resources" / "app.asar"
    if not bundle.is_dir() or not info_path.is_file() or not asar_path.is_file():
        raise PatchError(f"Not a supported {label}: {bundle}")

    info, _ = load_plist(info_path)
    header_hash = asar_header_hash(asar_path)
    if header_hash != asar_integrity_hash(info):
        raise PatchError(f"The {label} ASAR integrity verification failed")

    version = (
        str(info.get("CFBundleShortVersionString", "unknown")),
        str(info.get("CFBundleVersion", "unknown")),
    )
    return version, header_hash
~~~

- [ ] **Step 4: Generalize original validation and atomic original creation**

Replace validate_reapply_source and make_backup with:

~~~python
def validate_original_source(app: Path, original: Path) -> Path:
    app_version, _ = validated_bundle_identity(app, "target app")
    original_version, _ = validated_bundle_identity(
        original, "clean original backup"
    )
    original_asar = original / "Contents" / "Resources" / "app.asar"
    if contains_marker(original_asar):
        raise PatchError("The clean original backup is already patched")
    if app_version != original_version:
        raise PatchError(
            "The clean original backup does not match the target app version and build"
        )
    return original


def make_original_backup(source: Path, original: Path) -> Path:
    if source.resolve() == original.resolve():
        validate_original_source(source, original)
        return original

    validate_original_source(source, source)
    original.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{original.stem}.", dir=original.parent)
    )
    candidate = staging / original.name
    displaced = staging / "displaced.backup"
    try:
        run(
            ["/usr/bin/ditto", str(source), str(candidate)],
            label="Creating the clean sibling original",
        )
        validate_original_source(source, candidate)
        if original.exists():
            os.replace(original, displaced)
        try:
            os.replace(candidate, original)
        except Exception:
            if displaced.exists():
                os.replace(displaced, original)
            raise
        return original
    finally:
        shutil.rmtree(staging, ignore_errors=True)
~~~

The self-validation call intentionally rejects patched input and verifies the source ASAR against its own Info.plist before copying.

- [ ] **Step 5: Implement original selection, migration, and cleanup**

Add:

~~~python
def ensure_original_backup(
    app: Path,
    original: Path,
    *,
    reapply_from: Path | None,
    legacy_backups: tuple[Path, ...],
) -> Path:
    app_asar = app / "Contents" / "Resources" / "app.asar"
    app_is_patched = contains_marker(app_asar)
    distinct_legacy = tuple(
        dict.fromkeys(
            path.resolve()
            for path in legacy_backups
            if path.resolve() != original.resolve()
        )
    )

    if reapply_from is not None:
        source = reapply_from.expanduser().resolve()
        validate_original_source(app, source)
        make_original_backup(source, original)
    elif original.exists():
        try:
            validate_original_source(app, original)
        except PatchError:
            if app_is_patched:
                raise
            make_original_backup(app, original)
    elif app_is_patched:
        source = None
        last_error = None
        for candidate in distinct_legacy:
            if not candidate.exists():
                continue
            try:
                validate_original_source(app, candidate)
            except PatchError as exc:
                last_error = exc
                continue
            source = candidate
            break
        if source is None and last_error is not None:
            raise PatchError(
                "No legacy original backup matches the patched target app"
            ) from last_error
        if source is None:
            raise PatchError(
                f"Missing clean original backup beside the patched app: {original}"
            )
        make_original_backup(source, original)
    else:
        make_original_backup(app, original)

    validate_original_source(app, original)
    for legacy in distinct_legacy:
        if not legacy.exists():
            continue
        try:
            shutil.rmtree(legacy)
        except OSError as exc:
            raise PatchError(
                "The sibling original is verified, but the legacy original backup "
                f"could not be removed: {legacy}"
            ) from exc
    return original
~~~

Keep --reapply-from as a copy source only; do not delete an explicitly supplied external path. Pass only managed legacy locations in legacy_backups.

- [ ] **Step 6: Update original-source validation tests**

Rename the old validate_reapply_source tests to validate_original_source tests. Keep the corrupt-ASAR and version/build mismatch cases. In the accepted-source case, verify that a patched or unpatched target can use a matching clean source, because the validator no longer requires the target itself to carry the patch marker.

Use these assertion changes in all three cases:

~~~python
self.assertEqual(
    patcher.validate_original_source(app, original),
    original,
)

with self.assertRaisesRegex(patcher.PatchError, "ASAR integrity"):
    patcher.validate_original_source(app, original)

with self.assertRaisesRegex(patcher.PatchError, "does not match"):
    patcher.validate_original_source(app, original)
~~~

- [ ] **Step 7: Run the focused tests and verify they pass**

Run:

~~~bash
python3 -m unittest \
  tests.test_sync_codex_models.ManagedBackupTests \
  tests.test_sync_codex_models.ReapplyTests \
  -v
~~~

Expected: PASS for the new path, migration, cleanup-failure, update, and original-validation cases.

- [ ] **Step 8: Commit the original-management unit**

~~~bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "refactor: manage clean backup beside app"
~~~

---

### Task 2: Add the transactional previous-state snapshot

**Files:**
- Modify: patch_chatgpt_providers.py:1158-1207
- Test: tests/test_sync_codex_models.py:469-520

**Interfaces:**
- Consumes: validated_bundle_identity(bundle: Path, label: str)
- Produces: make_previous_snapshot(app: Path, previous: Path) -> Path
- Produces: restore_previous_snapshot(app: Path, previous: Path) -> Path
- Produces: remove_previous_snapshot(previous: Path) -> None

- [ ] **Step 1: Replace restore-backup tests with failing snapshot and rollback tests**

Add a RollbackSnapshotTests class:

~~~python
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
                patcher.restore_previous_snapshot(app, previous)

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
                    patcher, "run", side_effect=patcher.PatchError("copy failed")
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
~~~

- [ ] **Step 2: Run the snapshot tests and verify they fail**

Run:

~~~bash
python3 -m unittest tests.test_sync_codex_models.RollbackSnapshotTests -v
~~~

Expected: FAIL because the three snapshot functions do not exist and restore_backup still creates timestamped patch-failed app bundles.

- [ ] **Step 3: Replace restore_backup with explicit snapshot functions**

Implement:

~~~python
def make_previous_snapshot(app: Path, previous: Path) -> Path:
    if previous.exists():
        raise PatchError(
            f"A previous app snapshot already exists; recover or remove it first: {previous}"
        )

    source_identity = validated_bundle_identity(app, "target app")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{previous.stem}.", dir=previous.parent)
    )
    candidate = staging / previous.name
    try:
        run(
            ["/usr/bin/ditto", str(app), str(candidate)],
            label="Creating the previous app snapshot",
        )
        if validated_bundle_identity(candidate, "previous app snapshot") != source_identity:
            raise PatchError("The previous app snapshot does not match the target app")
        os.replace(candidate, previous)
        return previous
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore_previous_snapshot(app: Path, previous: Path) -> Path:
    previous_identity = validated_bundle_identity(
        previous, "previous app snapshot"
    )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{app.stem}.rollback-", dir=app.parent)
    )
    restored = staging / app.name
    displaced = staging / "mutated.app"
    rejected = staging / "rejected.app"
    try:
        run(
            ["/usr/bin/ditto", str(previous), str(restored)],
            label="Restoring the previous app snapshot",
        )
        if validated_bundle_identity(restored, "rollback candidate") != previous_identity:
            raise PatchError("The rollback candidate does not match the previous snapshot")

        os.replace(app, displaced)
        try:
            os.replace(restored, app)
            if validated_bundle_identity(app, "restored app") != previous_identity:
                raise PatchError("The restored app does not match the previous snapshot")
        except Exception:
            if app.exists():
                os.replace(app, rejected)
            os.replace(displaced, app)
            raise
        return app
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def remove_previous_snapshot(previous: Path) -> None:
    try:
        shutil.rmtree(previous)
    except OSError as exc:
        raise PatchError(
            f"Could not remove the previous app snapshot: {previous}"
        ) from exc
~~~

restore_previous_snapshot intentionally leaves the source snapshot in place. The caller removes it only after rollback verification succeeds.

- [ ] **Step 4: Run the snapshot tests and verify they pass**

Run:

~~~bash
python3 -m unittest tests.test_sync_codex_models.RollbackSnapshotTests -v
~~~

Expected: PASS, including plugin preservation through a full pre-patch snapshot.

- [ ] **Step 5: Commit the snapshot unit**

~~~bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "feat: add transactional app rollback snapshot"
~~~

---

### Task 3: Patch from the clean original and transact against the live app

**Files:**
- Modify: patch_chatgpt_providers.py:1246-1488
- Test: tests/test_sync_codex_models.py:276-625

**Interfaces:**
- Consumes: ensure_original_backup, managed_backup_paths
- Consumes: make_previous_snapshot, restore_previous_snapshot, remove_previous_snapshot
- Produces: build_patched_artifacts(original: Path, work: Path) -> tuple[Path, Path]
- Produces: install_patched_artifacts(app: Path, previous: Path, patched_asar: Path, patched_plist: Path) -> None
- Changes: patch_app(app: Path, config: Path, original: Path, previous: Path, overwrite_config: bool) -> None
- Changes: main() -> int

- [ ] **Step 1: Add failing orchestration tests**

Replace the old main-restores-original tests and add transaction tests:

~~~python
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
        original = app.with_name("ChatGPT-original.backup").resolve()
        previous = app.with_name("ChatGPT-previous.backup").resolve()

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

        self.assertEqual(ensure_original.call_args.args[:2], (app.resolve(), original))
        patch_app.assert_called_once_with(
            app.resolve(),
            config.resolve(),
            original,
            previous,
            False,
        )


def test_main_stops_before_migration_when_previous_snapshot_exists(self):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        app = root / "ChatGPT.app"
        previous = root / "ChatGPT-previous.backup"
        config = root / ".codex" / "desktop-model-providers.json"
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
            self.assertRaisesRegex(SystemExit, "1"),
        ):
            patcher.main()

        ensure_original.assert_not_called()


def test_patch_app_builds_from_original_before_snapshotting_live_app(self):
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
            mock.patch.object(patcher, "ensure_provider_config", return_value="kept"),
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
            mock.patch.object(
                patcher,
                "install_patched_artifacts",
            ) as install,
        ):
            patcher.patch_app(app, config, original, previous, False)

        build.assert_called_once()
        self.assertEqual(build.call_args.args[0], original)
        install.assert_called_once_with(
            app, previous, patched_asar, patched_plist
        )


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
        with self.assertRaisesRegex(patcher.PatchError, "plist replacement failed"):
            patcher.install_patched_artifacts(
                app, previous, patched_asar, patched_plist
            )

    snapshot.assert_called_once_with(app, previous)
    restore.assert_called_once_with(app, previous)
    remove.assert_called_once_with(previous)
~~~

Add this success case to assert cleanup follows final verification:

~~~python
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
        mock.patch.object(
            patcher,
            "load_plist",
            return_value=({}, None),
        ),
        mock.patch.object(
            patcher,
            "asar_header_hash",
            side_effect=lambda *_args: "hash",
        ),
        mock.patch.object(
            patcher,
            "asar_integrity_hash",
            return_value="hash",
        ),
        mock.patch.object(
            patcher,
            "contains_marker",
            side_effect=lambda *_args: True,
        ),
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
~~~

- [ ] **Step 2: Run the focused orchestration tests and verify they fail**

Run:

~~~bash
python3 -m unittest tests.test_sync_codex_models.ManagedBackupTests -v
~~~

Expected: FAIL in the new main, source-selection, success-cleanup, rollback, and stale-snapshot cases because main still restores from the Codex-home original, patch_app reads from the live app, and install_patched_artifacts does not exist.

- [ ] **Step 3: Extract patch preparation so its source is explicit**

Move the current temporary-workspace patch preparation from patch_app lines 1278-1379 into:

~~~python
def build_patched_artifacts(
    original: Path, work: Path
) -> tuple[Path, Path]:
    info_path = original / "Contents" / "Info.plist"
    asar_path = original / "Contents" / "Resources" / "app.asar"
    info, plist_format = load_plist(info_path)
    extracted = work / "app"
    patched_asar = work / "app.asar"
    patched_plist = work / "Info.plist"

    run(
        ["npx", "--yes", ASAR_PACKAGE, "extract", str(asar_path), str(extracted)],
        label="Extracting application resources",
    )

    assets = extracted / "webview" / "assets"
    if not assets.is_dir():
        raise PatchError("Extracted app has no webview/assets directory")

    central = unique_candidate(
        assets,
        "artifact-tab-content.electron~notebook-preview-panel~app-main~business-checkout",
        ("async prewarmThreadStart(", "async sendConfigReadRequest("),
        "App Server client",
    )
    picker = unique_candidate(
        assets,
        "settings-command-menu-section-items~new-thread-panel-page~settings-pag",
        ("composer.intelligenceDropdown.tooltip",),
        "model picker",
    )

    run(
        [
            "npx",
            "--yes",
            PRETTIER_PACKAGE,
            "--write",
            str(central),
            str(picker),
        ],
        label="Preparing the JavaScript bundles",
    )
    apply_unified_diff(central, CENTRAL_DIFF)
    apply_unified_diff(picker, PICKER_DIFF)

    if PATCH_MARKER.decode() not in central.read_text(encoding="utf-8"):
        raise PatchError("Routing marker missing after patch")
    if "CodexCustomProviderPickerSection" not in picker.read_text(encoding="utf-8"):
        raise PatchError("Provider picker missing after patch")

    run(
        [
            "npx",
            "--yes",
            PRETTIER_PACKAGE,
            "--write",
            str(central),
            str(picker),
        ],
        label="Formatting and validating the patched JavaScript",
    )
    run(
        ["npx", "--yes", ASAR_PACKAGE, "pack", str(extracted), str(patched_asar)],
        label="Packing patched application resources",
    )

    if not contains_marker(patched_asar):
        raise PatchError("Packed ASAR does not contain the patch marker")
    patched_header_hash = asar_header_hash(patched_asar)
    info["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"] = patched_header_hash
    with patched_plist.open("wb") as handle:
        plistlib.dump(info, handle, fmt=plist_format, sort_keys=False)

    return patched_asar, patched_plist
~~~

The moved body must keep the exact current unique_candidate calls, Prettier commands, apply_unified_diff calls, marker checks, pack command, ElectronAsarIntegrity update, and plistlib.dump behavior. The only source-path change is reading Info.plist and app.asar from original.

- [ ] **Step 4: Isolate live installation and rollback**

Add install_patched_artifacts by moving the current atomic replacements, codesign calls, and final verification into this transaction:

~~~python
def install_patched_artifacts(
    app: Path,
    previous: Path,
    patched_asar: Path,
    patched_plist: Path,
) -> None:
    info_path = app / "Contents" / "Info.plist"
    asar_path = app / "Contents" / "Resources" / "app.asar"
    make_previous_snapshot(app, previous)
    try:
        atomic_replace_file(patched_asar, asar_path)
        atomic_replace_file(patched_plist, info_path)
        run(
            ["/usr/bin/codesign", "--deep", "--force", "--sign", "-", str(app)],
            label="Applying the ad-hoc app signature",
        )
        run(
            [
                "/usr/bin/codesign",
                "--verify",
                "--deep",
                "--strict",
                "--verbose=2",
                str(app),
            ],
            label="Verifying the app signature",
        )
        final_info, _ = load_plist(info_path)
        if asar_header_hash(asar_path) != asar_integrity_hash(final_info):
            raise PatchError("Installed ASAR integrity verification failed")
        if not contains_marker(asar_path):
            raise PatchError("Installed ASAR is missing the patch marker")
    except Exception as exc:
        terminal_status(
            "RECOVERY",
            "Installation failed after app files changed. Restoring the previous app.",
            "33",
            stream=sys.stderr,
        )
        try:
            restore_previous_snapshot(app, previous)
        except Exception as restore_exc:
            terminal_panel(
                "Recovery failed",
                f"Automatic rollback failed: {restore_exc}\n"
                f"The previous app snapshot remains at: {previous}",
                "31",
                stream=sys.stderr,
            )
        else:
            try:
                remove_previous_snapshot(previous)
            except PatchError as cleanup_exc:
                terminal_status(
                    "CLEANUP",
                    "The previous app was restored, but its snapshot remains.",
                    "33",
                    detail=f"{previous}: {cleanup_exc}",
                    stream=sys.stderr,
                )
            terminal_status(
                "RESTORED",
                "The previous app state was restored.",
                "32",
                detail=app,
                stream=sys.stderr,
            )
        raise exc

    remove_previous_snapshot(previous)
~~~

Do not include original in this function; the transaction rollback source is always previous.

- [ ] **Step 5: Rewrite patch_app as source preparation plus live transaction**

Change its signature and orchestration to:

~~~python
def patch_app(
    app: Path,
    config: Path,
    original: Path,
    previous: Path,
    overwrite_config: bool,
) -> None:
    info_path = app / "Contents" / "Info.plist"
    asar_path = app / "Contents" / "Resources" / "app.asar"
    unpacked_path = app / "Contents" / "Resources" / "app.asar.unpacked"

    if sys.platform != "darwin":
        raise PatchError("This installer only supports macOS")
    if not app.is_dir() or not info_path.is_file() or not asar_path.is_file():
        raise PatchError(f"Not a supported ChatGPT app bundle: {app}")
    if not unpacked_path.is_dir():
        raise PatchError(f"Missing ASAR companion directory: {unpacked_path}")
    if shutil.which("npx") is None:
        raise PatchError("npx is required. Install Node.js, then run this installer again")

    config_action = ensure_provider_config(config, overwrite_config)
    terminal_status(
        "CONFIG",
        "Provider-routing config created."
        if config_action == "written"
        else "Existing provider-routing config validated.",
        "36",
        detail=config,
    )
    validate_original_source(app, original)
    version, _ = validated_bundle_identity(original, "clean original backup")
    terminal_heading("Installation", "35")
    terminal_status(
        "APP",
        f"Preparing ChatGPT {version[0]}, build {version[1]}.",
        "34",
        detail=app,
    )

    with tempfile.TemporaryDirectory(prefix="chatgpt-provider-patch-") as temporary:
        patched_asar, patched_plist = build_patched_artifacts(
            original, Path(temporary)
        )
        install_patched_artifacts(
            app, previous, patched_asar, patched_plist
        )

    print_completion_summary(config, backup=original)
~~~

- [ ] **Step 6: Rewrite main to seed the sibling original without restoring it over the live app**

Use:

~~~python
def main() -> int:
    args = parse_args()
    try:
        app = args.app.expanduser().resolve()
        config = args.config.expanduser().resolve()
        original, previous = managed_backup_paths(app)
        legacy_backups = tuple(
            dict.fromkeys(
                (
                    effective_codex_home().resolve() / "ChatGPT-original.app",
                    config.parent / "ChatGPT-original.app",
                )
            )
        )
        if previous.exists():
            raise PatchError(
                f"A previous app snapshot requires recovery or removal: {previous}"
            )

        stop_target_app_processes(app, args.allow_running)
        original = ensure_original_backup(
            app,
            original,
            reapply_from=args.reapply_from,
            legacy_backups=legacy_backups,
        )
        patch_app(
            app,
            config,
            original,
            previous,
            args.overwrite_config,
        )
    except PatchError as exc:
        fail(str(exc))
    except PermissionError as exc:
        fail(f"Permission denied: {exc}")
    except KeyboardInterrupt:
        fail("Interrupted", 130)
    return 0
~~~

Remove the pre-patch restore_backup call, migrated_backup branching, timestamped archived-patch status, and the datetime import if it has no remaining use.

- [ ] **Step 7: Run the orchestration tests and full backup-related test groups**

Run:

~~~bash
python3 -m unittest \
  tests.test_sync_codex_models.ManagedBackupTests \
  tests.test_sync_codex_models.RollbackSnapshotTests \
  tests.test_sync_codex_models.ReapplyTests \
  -v
~~~

Expected: PASS with no test or output expectation referring to patch-failed or a managed original under .codex.

- [ ] **Step 8: Commit the transaction orchestration**

~~~bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "refactor: patch from clean sibling backup"
~~~

---

### Task 4: Update recovery documentation and run regression verification

**Files:**
- Modify: README.md:53-55
- Modify: README.md:132-142
- Modify: patch_chatgpt_providers.py:628-630
- Modify: patch_chatgpt_providers.py:762-766
- Test: tests/test_sync_codex_models.py:200-225

**Interfaces:**
- Consumes: final sibling-backup and rollback behavior from Tasks 1-3
- Produces: accurate CLI help and recovery documentation

- [ ] **Step 1: Add failing user-facing wording tests**

Add:

~~~python
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
~~~

- [ ] **Step 2: Run the wording tests and verify they fail**

Run:

~~~bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_installer_help_describes_reapply_source_as_original_seed \
  tests.test_sync_codex_models.PatcherTemplateTests.test_installer_source_has_no_patch_failed_naming \
  -v
~~~

Expected: FAIL because the old --reapply-from help and patch-failed implementation text remain.

- [ ] **Step 3: Update terminal labels and CLI help**

Make these exact wording changes:

~~~python
terminal_status(
    "BACKUP",
    "Clean original app backup:",
    "34",
    detail=backup,
)
~~~

And:

~~~python
parser.add_argument(
    "--reapply-from",
    type=Path,
    help="Seed the sibling original from this matching clean app backup",
)
~~~

- [ ] **Step 4: Correct README installation and recovery text**

Replace the obsolete backup-path wording with:

~~~~markdown
The installer closes processes belonging to the target app, maintains a verified clean original beside it, creates a transactional snapshot before mutation, patches app.asar, updates Electron's ASAR integrity metadata, and applies an ad-hoc signature.

For the default app path, recovery files are:

~~~text
/Applications/ChatGPT-original.backup
/Applications/ChatGPT-previous.backup
~~~

ChatGPT-original.backup is the clean source for every patch. ChatGPT-previous.backup exists only during an installation attempt and is used to restore the exact pre-patch state if installation fails. A successfully verified patch or rollback removes the previous snapshot.

The installer migrates a valid legacy ~/.codex/ChatGPT-original.app into the sibling original and deletes the legacy copy only after the new copy verifies. Existing ChatGPT.patch-failed-*.app bundles are not removed automatically.
~~~~

Also change README line 55 so --help is described as showing alternate app and config paths, not alternate backup paths.

- [ ] **Step 5: Run the complete verification suite**

Run:

~~~bash
python3 -m unittest discover -v
python3 patch_chatgpt_providers.py --help
git diff --check
~~~

Expected:

- unittest reports all tests passing with zero failures and errors;
- CLI help exits 0, describes --reapply-from as seeding the sibling original, and exposes no persistent backup-directory option;
- git diff --check exits 0 with no whitespace errors.

- [ ] **Step 6: Review the final diff for scope and preserved user changes**

Run:

~~~bash
git diff -- patch_chatgpt_providers.py tests/test_sync_codex_models.py README.md
~~~

Confirm:

- PICKER_DIFF still uses Ly.Item, Ly.Title, and Ly.Separator;
- the upstream-initializer-tolerant picker hunk remains unchanged;
- plugins remain preserved because the complete live app is captured in ChatGPT-previous.backup;
- no implementation path deletes ChatGPT.patch-failed-*.app through a glob;
- no managed original remains under CODEX_HOME after successful migration;
- the provider-routing config path remains under the effective Codex home.

- [ ] **Step 7: Commit documentation and final verification changes**

~~~bash
git add README.md patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "docs: explain sibling backup recovery"
~~~
