# Revert Provider-Filtered Model Picker

## Problem

The provider-aware model filtering added after the ChatGPT build-5813
compatibility work introduces unwanted model-picker behavior and bugs. The
provider selector and explicit request routing remain useful, but the selected
provider must no longer alter the model catalog or automatically replace the
selected model.

## Goal

Restore the provider behavior that existed at commit `a93b1a5`: retain the
explicit provider selector and routing while removing the complete
provider-model-filter feature.

## Scope

- Revert the six isolated commits from `5e1166b` through `cb6ce84`.
- Keep ChatGPT `26.721.30844`, build `5813`, compatibility intact.
- Keep exact discovery of the consolidated `app-initial-*.js` bundle.
- Keep the provider menu for new tasks.
- Keep the selected provider on `thread/start` and `thread/fork` requests.
- Keep `thread/list` visible across all providers.
- Do not modify `sync_codex_models.py` or the provider-routing JSON schema.
- Do not install or modify `/Applications/ChatGPT.app` during verification.

## Design

Use a non-destructive Git revert of the six commits dedicated to model
filtering. This restores the tested build-5813 patch at `a93b1a5` without
rewriting history or manually reconstructing the previous embedded diff.

The reverted picker patch will continue to load the provider configuration,
read and persist `codex.customProviderSelection.v1`, and display the provider
section. Choosing a provider will affect only subsequent request routing.

Remove the filter-specific behavior introduced by those commits:

- shared listener, revision, and selected-provider publication state;
- provider assignment and model-array filtering helpers;
- the React hook that substitutes the raw catalog model array;
- canonical `cx/` model matching and replacement helpers;
- the effect that changes model and reasoning effort after provider changes;
- tests and documentation that promise provider-filtered model lists.

Restore the `model_providers` description to compatibility-only behavior.
Model IDs must not select a provider, filter the picker, or change the current
model. Explicit provider selection remains the sole request-routing input.

## Error handling and safety

- Preserve exact embedded-diff matching and fail-closed patch behavior.
- Preserve existing invalid-config fallback and visible config-error handling.
- Perform the implementation on an isolated `codex/` worktree branch.
- Use Git revert rather than reset so the feature removal remains auditable.
- Build and inspect only temporary artifacts derived from the clean original
  application backup.

## Tests and acceptance criteria

The implementation is accepted when:

- the full Python test suite passes;
- the provider selector and explicit `thread/start`/`thread/fork` routing tests
  remain present and pass;
- filter helpers, filter hook injection, and model-replacement effect are absent;
- README and completion output no longer claim model-picker filtering;
- `git diff --check` passes;
- applying the embedded diffs to a temporary extraction of the clean build-5813
  ASAR succeeds;
- Prettier, `node --check`, ASAR packing, patch-marker checks, and ASAR integrity
  verification pass;
- hashes of the live app and clean original are unchanged by verification.
