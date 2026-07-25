# ChatGPT Build 5848 Compatibility

## Problem

The installed macOS ChatGPT application is `26.721.41059`, build `5848`. Its
single application bundle is `app-initial-BHB6SClA.js`. The patcher recognises
the filename but rejects the bundle because it matches none of the supported
complete source-marker sets. It therefore stops before changing either the app
or its clean sibling backup.

## Goal

Support only the currently installed official ChatGPT release:

- Version: `26.721.41059`
- Build: `5848`
- Bundle: `app-initial-BHB6SClA.js`

All other application builds must continue to be rejected before patching.

## Design

Add one new `BundlePatchVariant` for build 5848. Its marker set will combine
the stable app-server and provider-picker markers with source contexts unique
to the formatted build-5848 bundle. `current_patch_bundle(...)` will continue
to select exactly one `app-initial-*.js` candidate that matches exactly one
known variant; it will not accept a partial marker set or an unrecognised
version.

Rebase the variant's `central_diff` and `picker_diff` against the formatted
`app-initial-BHB6SClA.js` source. Preserve existing behavior exactly:

- Load the provider-routing JSON from the Codex home directory.
- Route `thread/start` and `thread/fork` with the explicitly selected
  provider.
- Keep `thread/list` visible across providers.
- Insert the provider selector in the new-task model picker.
- Do not filter models, infer a provider from a model, or replace a selected
  model.

The pre-patch formatting, exact-once hunk matching, patch-marker validation,
post-patch formatting, JavaScript syntax check, ASAR integrity verification,
and transactional app backup/rollback flow remain unchanged.

## Error handling

If the build-5848 marker set is incomplete, appears in more than one bundle,
or any patch hunk matches zero or multiple locations, installation fails before
the target application is modified. A future ChatGPT update is intentionally
unsupported until it receives its own verified variant.

## Verification

- Add unit coverage for selecting the build-5848 marker set and rejecting
  missing, ambiguous, and mixed-variant candidates.
- Assert that the build-5848 diffs contain the verified source contexts and
  retain routing and picker behavior without model filtering.
- Build a patched ASAR in a temporary directory from the clean build-5848
  sibling backup; run Prettier, `node --check`, marker checks, and integrity
  checks.
- Hash both `/Applications/ChatGPT.app` and its clean sibling backup before
  and after the temporary build; require them to remain unchanged.
- Update the CLI help and README to advertise only `26.721.41059`, build
  `5848`.

## Out of scope

- Generic or permissive discovery for future ChatGPT releases.
- Support for prior macOS builds through this variant.
- Changes to the provider-routing JSON schema, model catalog synchronization,
  or Windows Store patch variants.
