# Model Picker Namespace Fix Design

## Problem

The provider picker patch installs successfully into Codex 26.715.72359, but opening the model-selection menu triggers the app's generic React error boundary. The generated picker component renders `zy.Item`, `zy.Title`, and `zy.Separator`. In this app build, `zy` is the dropdown root component and does not expose those properties. The menu subcomponents are available on the existing `Ly` namespace, which the unmodified model picker already uses for native menu items.

## Decision

Keep the current patch structure and make the smallest compatibility correction: render the custom provider rows, heading, and separator through `Ly`, while continuing to use `zy` only as the dropdown root. Do not add imports, alter provider-selection behavior, change application backup handling, or modify the installed app as part of this repair.

This approach has the smallest patch surface and follows the app bundle's own model-picker implementation. Adding a new import would create another version-sensitive hunk, while removing the custom provider section would eliminate the feature being patched.

## Code Changes

Update `PICKER_DIFF` in `patch_chatgpt_providers.py` so `CodexCustomProviderPickerSection` uses:

- `Ly.Item` for provider and configuration-error rows.
- `Ly.Title` for the provider section label.
- `Ly.Separator` between provider and model choices.

No other generated JavaScript or Python behavior changes.

## Error Handling and Data Flow

Provider configuration loading, fallback behavior, local-storage selection, and request routing remain unchanged. The correction only ensures React receives valid component types when the model menu renders. Invalid provider configuration continues to show the existing disabled fallback row.

## Verification

Add a focused regression test that inspects the embedded picker patch and proves menu subcomponents use `Ly`, not `zy`. Run that test first against the current code to confirm it fails for the diagnosed defect, then apply the minimal correction and run the complete unit-test suite.

Also apply the corrected embedded diff to a temporary extraction of the matching original Codex ASAR, format the generated JavaScript, and run JavaScript syntax validation. This verification must not modify `/Applications/ChatGPT.app`; the user will run the patcher afterward to reapply the corrected patch.

## Success Criteria

- The regression test catches any return to `zy.Item`, `zy.Title`, or `zy.Separator`.
- All repository tests pass.
- The corrected patch applies cleanly to the backed-up Codex 26.715.72359 bundle.
- The generated picker bundle passes JavaScript syntax validation.
- The installed Codex application is left untouched during implementation.
