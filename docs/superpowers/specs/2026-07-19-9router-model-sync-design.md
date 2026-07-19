# 9router Model Sync Design

## Goal

Provide a repeatable local command that rebuilds the custom Codex model catalog
from the installed Codex CLI, adds matching 9router aliases, refreshes provider
routing, and configures the required TOML entries.

## Behavior

- `sync_codex_models.py` runs `codex debug models --bundled` on every invocation.
- It replaces the configured `custom.json` with the bundled models followed by a
  `cx/` clone of every bundled model. A clone retains all capability metadata,
  changes `slug` to `cx/<source slug>`, and appends ` (9router)` to
  `display_name`.
- It replaces `desktop-model-providers.json` with two providers: `openai` and
  `9router`. Automatic routing uses OpenAI by default and routes every `cx/`
  clone to 9router.
- Unless `--9router-base-url` is supplied, the command asks for the 9router URL.
  Pressing Enter selects `http://127.0.0.1:20128/v1`.
- It updates only the root `model_catalog_json` assignment and the
  `[model_providers.9router]` table in `config.toml`. Other root options,
  provider tables, nested 9router authentication tables, marketplace settings,
  and project settings remain unchanged.

## Safety and Compatibility

- The command is Python 3.9 compatible and uses only the standard library.
- All generated JSON and TOML writes are atomic.
- Invalid CLI JSON, malformed catalogs, a missing `codex` executable, and invalid
  base URLs result in a clear error before configuration files are changed.
- The patcher's built-in template and JavaScript fallbacks name 9router rather
  than OpenRouter so new installs are aligned with the sync command.
