# ChatGPT Build 5828 Compatibility

## Problem

ChatGPT updated from `26.721.30844`, build `5813`, to `26.721.31836`,
build `5828`. The patcher still discovers the consolidated
`app-initial-*.js` bundle, but its first embedded hunk matches zero times
because the formatted bundle's minified symbols and picker layout changed.

The failure happens before installation, leaving the official target app and
the clean sibling original unmodified. Merely changing the advertised build
number is insufficient: the host IPC helper also changed from `tp(...)` to
`rp(...)`, so a context-only update would create a runtime failure.

## Goal

Support only ChatGPT `26.721.31836`, build `5828`, while preserving explicit
provider selection and request routing without filtering the model picker or
automatically changing the selected model.

## Scope

- Replace build-5813 bundle targeting with build-5828 targeting.
- Retarget all embedded routing and picker hunks to the formatted build-5828
  `app-initial-C-fROkKo.js` source layout.
- Keep exact `app-initial-*.js` filename discovery and unique-candidate checks.
- Keep the provider menu for new tasks.
- Keep the selected provider on `thread/start` and `thread/fork` requests.
- Keep `thread/list` visible across all providers.
- Keep `model_providers` as generated-config compatibility data only.
- Do not filter catalog models or replace the selected model.
- Do not support build `5813` after this change.
- Do not modify `sync_codex_models.py` or the provider-routing JSON schema.
- Do not install into `/Applications/ChatGPT.app` during automated verification.

## Root cause and source mapping

The build-5828 formatted bundle retains the same routing and picker behavior,
but minification assigned different symbols:

| Responsibility | Build 5813 | Build 5828 |
| --- | --- | --- |
| request-normalization insertion context | `o9t` / `obe` / `s9t` | `p9t` / `fbe` / `m9t` |
| host IPC helper | `tp(...)` | `rp(...)` |
| picker initialization dependencies | `qo`, `ad`, `KD`, `Aa`, `PD`, `LD` | `Ho`, `ed`, `DD`, `Oa`, `hD`, `vD` |
| picker JSX runtime | `wQ` | `TQ` |
| picker menu namespace | `yz` | `KR` |
| selected-item check icon | `Ym` | `Bm` |
| nearby module initializer | `fd()` | `sd()` |

The existing `sendRequest` and `prewarmThreadStart` hunk contexts still match
exactly after formatting. They remain structurally unchanged, with only the
shared injected routing helper updated to call the build-5828 IPC function.

## Design

Rename the build marker constant and related diagnostics/tests from build
5813 to build 5828. Retain the stable consolidated-bundle markers and add
`function p9t(e)`, `function Qjs(e)`, and `async function rp(...e)` as
build-specific markers. Unsupported builds must therefore fail during bundle
discovery rather than reaching a misleading hunk error.

Update `CENTRAL_DIFF` to insert the routing helpers after the new
`p9t`/`fbe` context and before `m9t`. Both config reads use `rp(...)`. The
existing behavior remains unchanged:

- `thread/list` receives an empty `modelProviders` array when none is supplied;
- `thread/start` and `thread/fork` receive the explicitly selected provider;
- no request provider is inferred from a model ID.

Update `PICKER_DIFF` to use the build-5828 initialization context, `rp(...)`
for config reads, `TQ` for JSX, `KR` for menu components, and `Bm` for the
selected-provider icon. Import React using the existing `r(o(), 1)` pattern
beside the build-5828 `TQ` runtime initialization.

Do not add any provider-model assignment, filtered-model hook, revision
listener, canonical-model matching, or replacement effect. Switching the
provider changes persisted routing state only; the model catalog and selected
model remain untouched.

Update README support statements and troubleshooting copy to name only
`26.721.31836`, build `5828`.

## Error handling and safety

- Require exactly one `app-initial-*.js` bundle with the build-5828 markers.
- Require every embedded hunk to match exactly once.
- Preserve marker and provider-picker checks after patching.
- Run Prettier and `node --check` before packing.
- Verify the packed ASAR marker and Electron ASAR integrity hash.
- Build only in a temporary directory from
  `/Applications/ChatGPT-original.backup`.
- Hash the live app and clean original before and after verification and require
  them to remain unchanged.
- Leave installation to an explicit user-run invocation after the verified
  implementation is merged.

## Tests and acceptance criteria

Add or update focused tests proving:

- bundle discovery targets build 5828 and rejects missing, ambiguous, or
  prefixed-impostor candidates;
- embedded diffs contain the build-5828 source symbols and contain none of the
  superseded build-5813 symbols;
- both config-loading paths use `rp(...)`, with no injected `tp(...)` calls;
- the provider selector and explicit `thread/start`/`thread/fork` routing remain;
- `thread/list` remains cross-provider;
- filter and automatic-model-replacement helpers remain absent;
- the help text and README advertise only build 5828.

Apply both embedded diffs to a temporary extraction of the clean build-5828
ASAR. The complete test suite, CLI checks, `git diff --check`, Prettier,
`node --check`, ASAR packing, marker checks, integrity verification, and
protected-file hash comparison must all pass before completion.
