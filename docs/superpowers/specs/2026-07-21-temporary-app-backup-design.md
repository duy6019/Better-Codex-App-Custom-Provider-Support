# Temporary ChatGPT App Backup Design

## Goal

Keep exactly one verified original app backup while allowing the installer to reapply the patch without a separate command or backup path.

## Design

The installer stores the sole managed original app backup at `~/.codex/ChatGPT-original.app` by default (or the effective `CODEX_HOME`). This location is independent of `--config`, so a custom provider-routing file cannot fragment the recovery copy. Before replacing any files in an unpatched `ChatGPT.app`, it creates or atomically replaces that backup and verifies that its ASAR exists and has the same header hash as the source app. The backup remains available through ASAR replacement, codesigning, signature verification, and final integrity checks.

When the target app is already patched, the installer validates and restores the managed original backup automatically before applying the current patch. If the app has been updated and is unpatched, the installer replaces the managed backup with the newly verified original first. If installation fails after app mutation begins, the installer restores the managed backup and preserves the failed patched copy beside the app, as it does today. The installer no longer creates timestamped backups in `~/Applications/ChatGPT Patch Backups` or accepts `--backup-dir`.

`--reapply-from` remains as a one-time migration override for an explicitly supplied original-app backup. It is no longer required for normal repeat installations.

## Verification

Tests cover replacement of the managed backup, ASAR-hash validation, automatic restoration before a repeat install, recovery after a post-mutation failure, and removal of the obsolete command-line option. The complete unittest suite and CLI help smoke test run after the change.
