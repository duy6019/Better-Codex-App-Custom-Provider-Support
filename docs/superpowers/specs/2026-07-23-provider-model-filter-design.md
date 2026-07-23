# Provider-Filtered Model Picker Design

## Problem

The patched Codex model menu lets the user choose a provider, but the model
list still shows every model from the catalog. The generated catalog contains
both native OpenAI model slugs and provider-specific clones such as `cx/...`,
so the user must manually keep the provider and model choices aligned.

The provider selection applies to `thread/start` and `thread/fork`. This
feature intentionally does not preserve compatibility with a model selection
from an older provider or with an already-running conversation. Every model
picker should reflect the provider currently selected by the patch.

## Decision

Filter the model data before the app derives model rows, advanced selections,
reasoning controls, or power selections. This makes the selected provider the
single input to every model-list presentation rather than hiding only the
final rendered rows.

Keep provider routing explicit. The selected provider continues to be sent to
`thread/start` and `thread/fork`; the selected model must not automatically
choose or override the provider.

## Alternatives Considered

### Filter the source model array

This is the selected approach. A shared provider state causes the component
that receives the catalog model array to rerender and derive a filtered array
before the app performs its existing model calculations. It covers the normal
list and advanced picker paths with one rule.

### Filter rendered model rows

Filtering after the app maps models to JSX would require a smaller-looking
patch, but upstream calculations would still use models from every provider.
The selected model, reasoning effort, power selections, focus behavior, and
empty-state behavior could then disagree with the visible list.

### Hide rows through the DOM or CSS

DOM hiding would depend on unstable markup and would leave hidden items in the
component's data and keyboard-navigation behavior. It is rejected because it
would be inaccessible and more version-sensitive than filtering model data.

## Provider Assignment

For each available model option:

1. If its model slug is present in `model_providers`, it belongs to the mapped
   provider.
2. Otherwise it belongs to `default_provider`.

With the current generated configuration, `cx/...` clones map to `9router`
and original, unmapped model slugs belong to `openai`. The rule remains generic
for additional configured providers.

The existing `desktop-model-providers.json` version and shape remain valid.
`model_providers` becomes an active UI-filtering input, but it is still not
used to infer request routing.

## Architecture

### Shared provider state

Extend the picker-side state stored under
`window.__codexDesktopModelProvidersPatchV2` with a small subscription
mechanism. The state continues to own the normalized provider configuration,
load status, load error, and pending load promise. It additionally exposes a
revision or listener notification whenever the loaded configuration or saved
provider selection changes.

The shared state must initialize missing picker-specific fields when the
central routing bundle created the global object first. This preserves the
existing cross-bundle state sharing.

### Filtering hook

Add a picker-side React hook that:

- subscribes to shared provider-state changes;
- loads the provider configuration through the existing promise-deduplicated
  loader;
- normalizes the saved provider to a configured provider or
  `default_provider`;
- returns only the catalog model options assigned to that provider; and
- memoizes the filtered array while its inputs are unchanged.

Apply the hook in the parent composer model-picker component immediately after
it reads the raw catalog model list. The filtered array then replaces the raw
array for existing model lookup, reasoning-effort derivation, power-selection
derivation, accessibility focus targets, and the `models` prop passed to the
model menu.

### Provider picker integration

Selecting a provider continues to write
`codex.customProviderSelection.v1` in local storage. It must also update the
shared picker state and notify subscribers so the model list changes without
closing or reopening the menu.

Config reloads use the same notification path. If the stored provider no
longer exists, the state saves and publishes `default_provider`.

## Model Selection Reconciliation

After filtering, check whether the selected model remains available. If not,
select a deterministic replacement:

1. Prefer the provider-specific counterpart with the same canonical slug. For
   the generated catalog, `gpt-5.6-sol` and `cx/gpt-5.6-sol` are counterparts.
2. Otherwise select the first model in the filtered catalog order.

For this feature, canonical-slug comparison removes one leading `cx/` prefix
and otherwise leaves the slug unchanged. Supporting additional clone
namespaces requires an explicit future design rather than guessing from an
arbitrary slash in a model ID.

When changing to the replacement model, preserve the current reasoning effort
if the replacement supports it. Otherwise use the replacement model's default
reasoning effort.

The reconciliation runs from an unconditional React effect so it does not
update model state during render. It applies to every model-picker context;
the feature does not preserve the prior model choice for existing
conversations.

## Empty and Error States

If the selected provider has no available models, render a disabled model-menu
row stating that no models are available for the selected provider. Do not
fall back to models owned by another provider. Leave the underlying selected
model unchanged until the user chooses a provider that has an available model.

If provider configuration loading or validation fails, retain the current
fallback configuration behavior and display the existing configuration-error
row. Filtering then uses the fallback configuration. A missing or invalid
saved provider resolves to `default_provider`.

## Routing Behavior

The central request patch remains unchanged in purpose:

- `thread/start` and `thread/fork` receive the explicitly selected provider;
- the request provider is not derived from the selected model;
- `thread/list` continues to request threads from all providers; and
- changing a provider does not change the provider of an already-running
  conversation.

Filtering is therefore a picker behavior that helps align visible model
choices with the explicit provider selection. It does not introduce automatic
provider routing.

## Code Changes

### `patch_chatgpt_providers.py`

- Extend `PICKER_DIFF` with shared-state notification helpers.
- Add the provider-filtering hook and model-assignment helpers.
- Patch the parent composer picker to filter the raw model array before its
  existing calculations.
- Publish provider changes from `CodexCustomProviderPickerSection`.
- Reconcile a selected model that is absent from the filtered array.
- Render a disabled empty-state row when the filtered array is empty.
- Leave `CENTRAL_DIFF` explicit-provider routing behavior intact.

### `tests/test_sync_codex_models.py`

- Prove mapped models are assigned to their configured provider and unmapped
  models are assigned to `default_provider`.
- Prove the embedded picker patch filters the source model array before normal
  and advanced picker calculations.
- Prove provider selection publishes a state update.
- Prove incompatible selections use a canonical counterpart or the first
  filtered model.
- Prove an empty provider result renders the disabled empty-state row.
- Preserve regression coverage showing request routing remains explicit rather
  than model-derived.

### `README.md`

- Document that the selected provider filters every model picker.
- Explain that unmapped models belong to `default_provider`.
- Explain the automatic model replacement when switching providers.
- Keep the running-conversation provider limitation visible.

`sync_codex_models.py` requires no schema or behavior change because it already
generates the required provider mappings for every `cx/...` clone.

## Verification

Use test-driven implementation and run:

- focused regression tests for each new picker behavior;
- the complete Python unit-test suite;
- `git diff --check`;
- application of the complete embedded diffs to a temporary extraction of
  `/Applications/ChatGPT-original.backup/Contents/Resources/app.asar`;
- Prettier over the patched temporary JavaScript bundles; and
- `node --check` over the patched picker and central bundles.

The verification process must not modify `/Applications/ChatGPT.app` or the
clean original backup. Manual installed-app smoke testing occurs only after the
user intentionally reruns the patcher.

## Success Criteria

- Selecting OpenAI shows only original or otherwise unmapped models.
- Selecting 9router shows only models mapped to `9router`, including the
  generated `cx/...` clones.
- Normal and advanced model-picker views use the same filtered model set.
- The selected model is reconciled when it is absent from the new provider's
  list.
- Providers with no available models do not expose models owned by another
  provider.
- New tasks and forks still use the explicitly selected provider.
- Invalid configuration still falls back safely and visibly.
- All repository tests and temporary-bundle syntax checks pass.

## Non-Goals

- Preserving model selections from a previous provider.
- Migrating historical task or conversation data.
- Changing a running conversation's provider.
- Adding an `All providers` or automatic-provider option.
- Changing the provider configuration schema or generated model catalog.
