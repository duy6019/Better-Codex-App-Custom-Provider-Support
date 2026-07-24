# ChatGPT Build 5813 Patch Compatibility Design

## Problem

The official ChatGPT macOS update to version `26.721.30844`, build `5813`,
changed the webview bundle layout used by `patch_chatgpt_providers.py`. The
previously supported build stored the App Server client and model picker in two
long-named split chunks. Build 5813 consolidates both targets into one
`app-initial-*.js` bundle and changes the surrounding generated source.

The installer currently finds zero files matching its old filename fragments
and stops before replacing or signing the installed application. Updating only
the filename fragments would not be sufficient because neither embedded patch
matches the new formatted source.

## Scope

This change supports only the current official macOS application:

- ChatGPT version: `26.721.30844`
- Bundle build: `5813`
- Platform: macOS

Support for build `5718` and its split-chunk layout will be removed. The change
will not attempt to create a release-independent JavaScript rewriter. A future
official update that changes the required source markers or patch contexts must
continue to fail closed before the installed app is modified.

The separate provider-model filtering plan already documented on `main` is not
part of this compatibility update. Provider selection and routing behavior
remain unchanged.

## Bundle Discovery

After extracting `app.asar`, the installer will select exactly one JavaScript
asset whose filename matches `app-initial-*.js` and whose source contains all
of the build-5813 markers needed by both patch areas:

- `async prewarmThreadStart(`
- `async sendConfigReadRequest(`
- `composer.intelligenceDropdown.tooltip`
- `data-model-picker-model-row`
- `vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto`

Discovery succeeds only when exactly one file matches both the filename shape
and every content marker. Zero or multiple matches produce a `PatchError` with
the number of filename and content matches.

Because build 5813 stores both patch targets in the same file, the installer
will format that file once, apply both embedded diffs sequentially, and format
it once more before packing.

## Routing Patch

The build-5813 routing diff will insert the existing provider configuration
loader and routing state into the consolidated bundle. It will use the host
bridge symbol present in build 5813 to read
`desktop-model-providers.json` from the local Codex home.

The request interception behavior remains:

- `thread/list` supplies an empty `modelProviders` array when the caller does
  not already provide one, keeping tasks from all providers visible.
- `thread/start` and `thread/fork` receive the explicitly selected
  `modelProvider`.
- the prewarmed `thread/start` path receives the same selected provider before
  the request is enqueued.
- invalid or unreadable configuration falls back to the built-in OpenAI and
  9router configuration without preventing the app from opening.

The diff will use exact build-5813 source context around `sendRequest` and
`prewarmThreadStart`; it will not use broad regular-expression replacement.

## Provider Picker Patch

The build-5813 picker diff will recreate the existing provider menu section
using the JSX runtime, menu component namespace, selected-item icon, host
bridge, and React import symbols present in the consolidated bundle.

The section will be inserted before the native model list title in the Codex
model picker. Opening the menu reloads the provider configuration. Selecting a
provider writes `codex.customProviderSelection.v1` to local storage, and the
selected entry displays the native check icon. Configuration errors are shown
inside the menu while the fallback configuration remains usable.

The picker component will retain the existing labels and behavior. It will not
filter or rewrite the model catalog.

## Safety and Error Handling

The installer will preserve its current transactional flow:

1. Build patched artifacts from `/Applications/ChatGPT-original.backup` in a
   temporary directory.
2. Require the routing marker and picker component marker after patching.
3. Require JavaScript parsing or syntax validation before packing.
4. Pack the temporary ASAR and verify that it contains the patch marker.
5. Update the temporary plist's ASAR integrity hash.
6. Modify `/Applications/ChatGPT.app` only after all preparation succeeds and a
   verified previous-state snapshot exists.

Any discovery, hunk, formatting, syntax, packing, or integrity failure aborts
before live app replacement. Development verification will not modify
`/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup`.

## Testing and Verification

Automated regression tests will cover:

- discovering a single current-layout `app-initial-*.js` fixture;
- rejecting an absent current-layout bundle;
- rejecting ambiguous current-layout bundles;
- treating the routing and picker targets as one file so formatting and
  patching are not duplicated;
- preserving descriptive errors for unsupported source structures.

Integration verification will use a temporary extraction of the clean build
5813 ASAR to prove that:

- every discovery marker resolves to exactly one bundle;
- both complete embedded diffs apply to the formatted bundle;
- the patched JavaScript passes syntax validation;
- the packed temporary ASAR contains the patch marker;
- the generated plist integrity hash matches the packed ASAR.

The full Python test suite, `git diff --check`, and both scripts' `--help`
commands must also pass.

## Success Criteria

Running `python3 patch_chatgpt_providers.py` against the official ChatGPT
`26.721.30844` build `5813` completes discovery and artifact preparation
without the reported zero-filename-match error. The resulting temporary patch
contains the routing hook and provider picker, while unsupported future builds
still stop safely before modifying the installed application.
