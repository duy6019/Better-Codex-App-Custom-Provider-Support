# Temporary App Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use a verified, ephemeral app backup during patching and stop writing successful-install backups to `~/Applications/ChatGPT Patch Backups`.

**Architecture:** `patch_app` owns the temporary workspace, including the extracted ASAR and original-app recovery copy. `make_backup` writes the copy into that workspace and validates its ASAR header hash against the source. It remains usable by the existing rollback path until installation is fully verified.

**Tech Stack:** Python standard library, `unittest`, macOS `ditto`.

## Global Constraints

- Create and verify a complete app backup before mutating `ChatGPT.app`.
- Abort before mutation when the ASAR structure or integrity is incompatible.
- Restore the exact original app automatically on installation failure.
- Preserve user configuration and credentials.
- Keep `--reapply-from` for an explicitly supplied original backup.

---

### Task 1: Make installation recovery backups ephemeral

**Files:**
- Modify: `patch_chatgpt_providers.py:579-1409`
- Test: `tests/test_sync_codex_models.py:178-211`

**Interfaces:**
- Consumes: `make_backup(app: Path, backup_dir: Path, version: str, build: str) -> Path`
- Produces: `make_backup(app: Path, backup_dir: Path, version: str, build: str) -> Path`, where `backup_dir` is the active temporary workspace.

- [ ] **Step 1: Write the failing test**

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

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_installer_has_no_persistent_backup_directory_option -v`

Expected: FAIL because the CLI still exposes `--backup-dir`.

- [ ] **Step 3: Write minimal implementation**

```python
with tempfile.TemporaryDirectory(prefix="chatgpt-provider-patch-") as temporary:
    work = Path(temporary)
    backup = make_backup(app, work / "original-app", version, build)
    # Retain backup through all mutation and validation steps.
```

Remove `--backup-dir`, remove recovery-backup output from the success summary, and simplify `patch_app` to derive the backup path from its temporary workspace. After copying, verify that the backup ASAR header hash equals the source ASAR header hash before any app file is replaced.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_installer_has_no_persistent_backup_directory_option -v`

Expected: PASS.

- [ ] **Step 5: Commit**

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

- [ ] **Step 1: Run the complete test suite**

Run: `python3 -m unittest discover -v`

Expected: PASS with zero failures and errors.

- [ ] **Step 2: Run the CLI help smoke test**

Run: `python3 patch_chatgpt_providers.py --help`

Expected: exit 0 and no `--backup-dir` option.

- [ ] **Step 3: Check the patch diff**

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.
