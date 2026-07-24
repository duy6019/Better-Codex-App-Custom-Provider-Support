# Provider-Filtered Model Picker for ChatGPT Build 5813

## Problem

The build-5813 compatibility patch restored the provider selector, but the
`model_providers` mapping in `desktop-model-providers.json` is no longer used
by the model picker. Selecting `9router` therefore leaves every catalog model
visible instead of showing the mapped `cx/...` models.

## Goal

For ChatGPT `26.721.30844`, build `5813`, make the model picker show only the
models assigned to the explicitly selected provider while preserving the
existing explicit request routing.

## Scope

- Modify only the picker-side embedded patch in `patch_chatgpt_providers.py`.
- Keep the current consolidated `app-initial-*.js` bundle discovery.
- Keep the provider-routing JSON schema and `sync_codex_models.py` unchanged.
- Keep `thread/start` and `thread/fork` routed by the selected provider.
- Keep `thread/list` visible across all providers.
- Do not infer a provider from the selected model.
- Do not add an Automatic or All providers option.

## Design

The picker-side state at `window.__codexDesktopModelProvidersPatchV2` gains a
small listener/revision mechanism. Loading the config or selecting a provider
normalizes the saved provider, updates the shared state, and publishes a
revision so the composer picker rerenders immediately.

The provider assignment rule is deterministic:

1. If a model slug exists in `model_providers`, use that provider.
2. Otherwise use `default_provider`.

The patch adds a React hook that receives the raw catalog model array, loads
the provider config, and filters the array before the existing model lookup,
reasoning, advanced-picker, and power-selection calculations. An undefined
raw array remains undefined; a provider with no assigned models produces an
empty array and never falls back to another provider's models.

If the current selected model is removed by the filter, a React effect selects
a deterministic replacement: first the counterpart with one leading `cx/`
prefix removed or added, then the first available model. The current reasoning
effort is retained only when supported by the replacement; otherwise the
replacement's default effort is used.

The existing provider menu continues to persist
`codex.customProviderSelection.v1`, now also publishing the shared state so
the model list changes without reopening the menu. Existing config-error and
fallback behavior remains intact.

## Error handling and safety

- Invalid or unreadable provider config uses the existing normalized fallback
  and keeps the existing visible config-error row.
- An invalid saved provider resolves to `default_provider`.
- The patch remains fail-closed: embedded diff hunks must match exactly, the
  patched bundle must contain the patch marker and provider picker, and
  Prettier plus `node --check` must pass before packing.
- Automated verification must not modify `/Applications/ChatGPT.app` or the
  clean sibling original backup.

## Tests and acceptance criteria

Add focused tests that prove:

- mapped and unmapped models resolve to the expected provider;
- provider state publishes revisions and the picker subscribes to them;
- filtering happens before existing model-picker derivations;
- switching providers updates the model list;
- an incompatible selected model chooses its canonical counterpart or first
  available replacement;
- explicit `thread/start` and `thread/fork` routing remains unchanged.

Apply the complete embedded diffs to a temporary extraction of the clean
build-5813 ASAR, run Prettier and `node --check`, then run the full Python
unit-test suite and `git diff --check`. The live and clean app bundles must
remain byte-for-byte unchanged during verification.
