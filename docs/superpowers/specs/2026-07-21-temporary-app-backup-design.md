# Temporary ChatGPT App Backup Design

## Goal

Stop retaining successful-install backups in `~/Applications/ChatGPT Patch Backups` while preserving the installer safety guarantees.

## Design

Before replacing any files in `ChatGPT.app`, the installer creates a complete backup in its own temporary working directory and verifies that its ASAR exists and has the same header hash as the source app. The backup remains available through ASAR replacement, codesigning, signature verification, and final integrity checks.

If installation fails after app mutation begins, the installer restores that temporary backup and preserves the failed patched copy beside the app, as it does today. If installation succeeds, the temporary directory and backup are removed automatically. The installer will no longer create `~/Applications/ChatGPT Patch Backups` or accept `--backup-dir`.

`--reapply-from` remains unchanged: it is an explicitly supplied original-app backup used to return a patched app to its original state before applying the current patch.

## Verification

Tests cover the temporary-backup destination, ASAR-hash validation, recovery after a post-mutation failure, and removal of the obsolete command-line option. The complete unittest suite and CLI help smoke test run after the change.
