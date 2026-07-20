# Temporary App Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep one verified original backup for automatic repeat patching and stop writing timestamped backups to `~/Applications/ChatGPT Patch Backups`.

**Architecture:** `patch_app` uses the managed original backup at `~/.codex/ChatGPT-original.app` (or the effective `CODEX_HOME`), independently of `--config`. `make_backup` atomically replaces that single copy after validating its ASAR header hash against the source. `main` validates and restores it automatically if the target app is already patched, then runs the normal installation flow.

**Tech Stack:** Python standard library, `unittest`, macOS `ditto`.

## Global Constraints

- Create and verify a complete app backup before mutating `ChatGPT.app`.
- Abort before mutation when the ASAR structure or integrity is incompatible.
- Restore the exact original app automatically on installation failure.
- Preserve user configuration and credentials.
- Keep `--reapply-from` for an explicitly supplied original backup.

---

### Task 1: Maintain one managed original backup and reapply automatically

**Files:**
- Modify: `patch_chatgpt_providers.py:579-1409`
- Test: `tests/test_sync_codex_models.py:178-211`

**Interfaces:**
- Consumes: `make_backup(app: Path, backup_dir: Path, version: str, build: str) -> Path`
- Produces: `make_backup(app: Path, backup: Path) -> Path`, which atomically replaces a verified managed original backup.

- [x] **Step 1: Write the failing test**

```python
def test_installer_has_no_persistent_backup_directory_option(self):
    output = io.StringIO()
    with (
        mock.patch.object(patcher.sys, "argv", ["patch_chatgpt_providers.py", "--help"]),
        redirect_stdout(output),
        self.assertRaisesRegex(SystemExit, "0"),
    ):
        patcher.parse_args()
    self.assertNotIn("--backup-dir", output.getvalue())
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_installer_has_no_persistent_backup_directory_option -v`

Expected: FAIL because the CLI still exposes `--backup-dir`.

- [x] **Step 3: Write minimal implementation**

```python
managed_backup = effective_codex_home() / "ChatGPT-original.app"
if contains_marker(app_asar):
    restore_backup(app, validate_reapply_source(app, managed_backup))
make_backup(app, managed_backup)
```

Remove `--backup-dir`. After copying, verify that the backup ASAR header hash equals the source ASAR header hash before any app file is replaced; replace an older managed backup only after the new copy verifies. Restore that backup automatically before processing an already patched app.

When the canonical backup is absent, recognize a legacy backup at the custom `--config` parent for both patched reapply and unpatched-update flows. For a patched app, validate it before restoring. Remove it immediately after the new canonical backup has been created and verified, before app mutation. If the legacy cleanup fails, remove the new canonical backup and stop.

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_installer_has_no_persistent_backup_directory_option -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add patch_chatgpt_providers.py tests/test_patcher_safety.py
git commit -m "fix: use temporary app recovery backups"
```

### Task 2: Run regression verification

**Files:**
- Modify: none

**Interfaces:**
- Consumes: completed installer and unit tests.
- Produces: verified test suite and CLI help output.

- [x] **Step 1: Run the complete test suite**

Run: `python3 -m unittest discover -v`

Expected: PASS with zero failures and errors.

- [x] **Step 2: Run the CLI help smoke test**

Run: `python3 patch_chatgpt_providers.py --help`

Expected: exit 0 and no `--backup-dir` option.

- [x] **Step 3: Check the patch diff**

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.
