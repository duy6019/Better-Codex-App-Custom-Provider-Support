# Provider and Model Shared Submenu Design

## Problem

The current provider patch renders its provider section at the root of the
advanced composer configuration popup. In the desktop UI, that popup contains
the `Model`, `Effort`, and reset rows. Selecting `Model` opens a nested model
submenu, so the provider controls are separated from the model choices.

The desired interaction places the provider section at the top of the nested
model submenu, followed by the native `Model` heading and model list. The root
advanced popup must continue to contain only its native configuration rows.

## Decision

Render `CodexCustomProviderPickerSection` in each native menu that presents
model choices:

- Keep it in the standalone model picker, where that popup is itself the
  model-selection surface.
- Move it from the root advanced configuration popup into the nested model
  submenu, immediately before the native `Model` heading and scrollable model
  rows.

The patch must not duplicate the provider section in both layers of the
advanced UI.

## Behavior

Opening the advanced composer popup shows the native rows for `Model`,
`Effort`, and reset. Opening its `Model` row shows one submenu with:

1. `Provider for new tasks` and the configured provider choices.
2. A separator.
3. The native `Model` heading and unchanged catalog model rows.

Selecting a provider still persists the explicit provider choice and affects
only new tasks and forks. It does not filter the catalog, select a model, or
alter the provider of an existing conversation.

## Implementation Boundaries

Only `patch_chatgpt_providers.py` and its patch-template tests need changes.
The provider-routing JSON schema, generated model catalog, central request
routing, and README behavior stay unchanged.

The embedded patch remains version-specific and must retain exact source
contexts for ChatGPT 26.721.31836 build 5828.

## Verification

Tests must prove that:

- the standalone model picker still receives the provider section;
- the advanced root popup does not receive the provider section; and
- the nested advanced model submenu receives the provider section before the
  native model heading and rows.

Run the focused patch-template tests, the full Python unit-test suite,
`git diff --check`, and the existing temporary ASAR patch and JavaScript
syntax validation. Verification must not modify ChatGPT.app or its clean
original backup.
