# Separate Model Synchronization from Provider Setup

## Goal

Keep model-catalog synchronization independent of custom-provider setup. The
patch and the setup wizard must support any provider without embedding 9router
as an automatic configuration side effect.

## Responsibilities

### `sync_codex_models.py`

- Read the bundled catalog through `codex debug models --bundled`.
- Validate the catalog and atomically write it to the configured custom catalog
  path.
- Update only the root `model_catalog_json` entry in `config.toml`.
- Preserve every provider table, routing entry, credential setting, and other
  TOML content.
- Do not create model aliases, edit `desktop-model-providers.json`, prompt for
  a provider URL, or configure 9router.

### `setup_custom_provider.py`

- Remain the dedicated workflow for adding or updating 9router and any other
  custom provider.
- Own provider menu entries in `desktop-model-providers.json`, the matching
  `model_providers.<id>` TOML tables, and secure credential storage.
- Reuse catalog-independent shared helpers without relying on 9router-specific
  behavior in the synchronization command.

### `patch_chatgpt_providers.py`

- Create a generic fallback routing file that contains only the built-in OpenAI
  provider.
- Load providers subsequently added by the setup wizard.
- Keep provider selection separate from model selection; `model_providers`
  remains compatibility metadata only.

## Compatibility and Safety

- Python 3.9 and the standard library remain sufficient.
- All writes remain atomic.
- Existing provider configuration is untouched by model synchronization.
- Existing custom provider setups continue to work; users need not re-run the
  setup wizard after a model-only sync.

## Verification

- Unit tests prove sync updates only the model catalog and root TOML key.
- Unit tests prove patch defaults are provider-agnostic and setup still adds a
  provider to routing and TOML.
- The full unittest suite and each command's `--help` output pass.
