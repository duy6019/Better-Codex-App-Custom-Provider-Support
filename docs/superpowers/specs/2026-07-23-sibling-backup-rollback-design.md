# Sibling App Backups and Transactional Rollback

## Goal

Keep the clean app source and the pre-patch rollback snapshot beside the target app, while retaining only the target app as a launchable `.app` bundle. Remove the migrated managed original from the Codex home after the sibling copy is verified.

## Design

For a target such as `/Applications/ChatGPT.app`, derive the managed paths from the target path:

```text
/Applications/ChatGPT.app
/Applications/ChatGPT-original.backup
/Applications/ChatGPT-previous.backup
```

The `.backup` suffix keeps the full app-bundle directory structure available to `ditto` and validation without presenting the copies as additional launchable applications to macOS LaunchServices.

`ChatGPT-original.backup` is the sole clean source used to build every patch. It must contain an unpatched ASAR, valid Electron ASAR integrity metadata, and the same app version/build as the target before it is used. It is never mutated by the patch operation.

`ChatGPT-previous.backup` is a transactional snapshot of the currently installed app immediately before a live patch attempt. It is not a permanent history archive and is not used as the patch source. A new snapshot is atomically prepared and verified for each attempt. A pre-existing snapshot from an interrupted or failed run is not silently overwritten; the installer reports it so recovery data cannot be lost.

## Lifecycle

1. Resolve the target app and derive sibling backup paths from `app.parent` and `app.stem`; do not derive managed backup paths from `CODEX_HOME` or the provider config path.
2. If the sibling original is absent, migrate a valid legacy original from the effective Codex home or the legacy custom-config parent. Copy it through a staging directory, verify its ASAR, integrity metadata, and version/build, then remove the legacy source only after the sibling copy is valid. If migration fails, leave the legacy source untouched and stop before app mutation.
3. If the target is unpatched and the sibling original is absent or belongs to a different app version/build, validate the target as an unpatched original and atomically replace the sibling original with it. If the target is already patched, require a matching clean sibling original. An explicitly supplied `--reapply-from` source is validated, copied into the sibling original path, and then treated as the managed source for that run.
4. Build the patched ASAR and updated `Info.plist` from the clean sibling original in a temporary workspace. A preparation failure does not mutate the installed app or create a persistent previous snapshot.
5. Before the first live file replacement, copy the complete current target app to `ChatGPT-previous.backup` through staging and verify the copy. Preserve the current app unchanged if snapshot creation fails.
6. Atomically replace the target app's patched ASAR and metadata, apply and verify the ad-hoc signature, and run the final ASAR integrity and patch-marker checks.
7. On success, remove `ChatGPT-previous.backup` after all final checks pass.
8. If any failure occurs after live mutation begins, restore the target app from `ChatGPT-previous.backup` through a verified staging copy. Remove the previous snapshot only after rollback succeeds. If rollback fails, retain the previous snapshot and report its exact path for manual recovery.

## Migration and Cleanup

- The managed original moves from `effective_codex_home()/ChatGPT-original.app` to the target sibling `ChatGPT-original.backup`.
- Legacy originals under a custom config parent remain recognized for one-time migration, matching the existing compatibility behavior.
- Existing timestamped `ChatGPT.patch-failed-*.app` bundles are not deleted by the installer via a broad glob. They can be manually removed after the new flow is verified.
- The provider-routing config remains in the effective Codex home; only app backup storage moves beside the target app.

## Failure Semantics

- The clean sibling original is the patch source and the fallback clean state.
- The previous sibling snapshot is the rollback source for a failed patch and restores the exact state that was running before the attempt, including bundle files and installed plugins.
- No live app file is changed until both the clean patch artifacts and the previous snapshot have passed validation.
- A failed migration, invalid source, stale previous snapshot, snapshot failure, or failed rollback stops with an actionable error and preserves the data needed for recovery.

## Testing

Tests must cover:

- deriving sibling `.backup` paths for `/Applications` and custom app locations;
- migration from the effective Codex home and legacy custom-config locations;
- deleting a legacy source only after a verified sibling copy exists;
- refusing to overwrite an invalid or interrupted `ChatGPT-previous.backup`;
- creating/replacing the clean original when an unpatched app update changes version/build;
- building patched artifacts from the clean sibling original rather than the live patched app;
- creating the previous snapshot before live mutation;
- removing the previous snapshot after a successful patch;
- rolling back from the previous snapshot after post-mutation failure;
- retaining the previous snapshot when rollback fails;
- preserving `--reapply-from` as a one-time migration source;
- removing the obsolete `patch-failed` naming from installer output and behavior.

The complete unittest suite and the CLI help smoke test must pass after implementation.

## Scope

This change is limited to app backup placement, naming, migration, and transactional rollback. Provider configuration, provider selection, patch payloads, app target defaults, and plugin preservation behavior remain unchanged except where required to source patch artifacts from the clean sibling original.
