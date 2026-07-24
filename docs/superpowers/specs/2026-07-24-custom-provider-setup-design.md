# Custom Provider Setup Wizard

## Problem

Adding a custom provider currently requires manually editing Codex TOML,
desktop provider-routing JSON, and macOS Keychain entries. The existing
`sync_codex_models.py` script is specific to 9router and regenerates the
provider-routing file, which can remove manually added providers.

## Goal

Provide a separate interactive script that adds or updates one custom model
provider per run. It must make the provider immediately selectable in the
desktop app while retaining other providers, and it must support either a
Keychain-backed API key or no authentication. Model catalog management is
explicitly out of scope.

## Scope

- Add `setup_custom_provider.py` as the interactive provider setup command.
- Prompt for a provider ID, display name, base URL, and wire API.
- Support two authentication choices: Keychain-backed API key and no auth.
- Add or update exactly one provider in `~/.codex/config.toml` and
  `~/.codex/desktop-model-providers.json` per invocation.
- Name each Keychain service `codex-<provider-id>`.
- Preserve unrelated TOML settings, provider configuration, provider-menu
  entries, and existing model mappings.
- Change the 9router sync path only enough to retain providers added by the
  new script when it rewrites the desktop provider-routing JSON.
- Document the new command and its model-catalog boundary.

## Non-goals

- Create, clone, filter, or route model catalog entries for a custom provider.
- Support environment-variable, OAuth, command-helper, custom-header, or
  bearer-token authentication setup in the wizard.
- Modify the patched desktop application or its provider-routing schema.
- Change the existing 9router model-sync behavior beyond preservation of
  unrelated provider menu entries and mappings.

## Design

### Interactive setup

`python3 setup_custom_provider.py` prompts for these values:

1. Provider ID, validated as a non-empty lowercase identifier suitable for a
   TOML table and Keychain service suffix. Reserved built-in IDs are rejected.
2. Display name, used in Codex configuration and the desktop provider menu.
3. Absolute HTTP or HTTPS base URL.
4. Wire API, selected from `responses` (the default) and `chat`.
5. Authentication: `Keychain` or `No auth`.

For Keychain authentication, the script collects the API key through hidden
terminal input and stores it as a generic-password entry with service
`codex-<provider-id>` and account `<provider-id>`. It uses `security
add-generic-password -U` so rerunning setup updates the entry rather than
creating duplicates.

The generated authentication configuration reads the key only when Codex needs
it:

```toml
[model_providers.acme]
name = "Acme"
base_url = "https://api.acme.example/v1"
wire_api = "responses"

[model_providers.acme.auth]
command = "security"
args = ["find-generic-password", "-s", "codex-acme", "-a", "acme", "-w"]
```

For `No auth`, the provider root table is written without a nested `.auth`
table; an existing authentication table for that provider is removed. The API
key is never written to TOML, JSON, output, or documentation examples.

### Configuration updates

The new script reuses safe atomic file writes and focused TOML-table mutation
patterns from `sync_codex_models.py`. It updates only the selected provider's
root and nested auth tables in the user-level config. It must not write
provider authentication to a project-local config.

The desktop routing JSON is read before mutation. Its `providers` array gains
or replaces an entry with the provider ID, display name, and an explanation
that its connection settings live in `config.toml`. Existing provider entries,
`default_provider`, and `model_providers` mappings remain unchanged.

`sync_codex_models.py` will merge its generated OpenAI/9router entries and
9router model mappings with existing unrelated entries instead of replacing
the complete routing document. This prevents a later 9router sync from
removing providers created by the setup wizard.

### Error handling and safety

- Validate all user-entered identifiers, URLs, and menu choices before file
  mutation.
- Fail clearly if the macOS `security` command cannot store the supplied key.
- Write the Keychain entry before TOML points Codex at it.
- On a configuration write failure after a successful Keychain update, report
  that the Keychain entry was retained and identify its service name.
- Keep existing providers unchanged if validation fails.
- Treat malformed routing JSON as an error rather than silently discarding
  providers or model mappings.

## Tests and acceptance criteria

- Provider IDs reject invalid and reserved values; base URLs and wire API
  choices are validated.
- Keychain setup invokes the expected `security add-generic-password` command
  using `codex-<provider-id>` and writes the matching command-backed TOML auth
  table without exposing the secret.
- No-auth setup creates no auth table and removes one from an existing provider
  update.
- Adding or updating one provider preserves unrelated TOML tables, menu
  providers, defaults, and model mappings.
- The existing 9router synchronization preserves wizard-created provider menu
  entries and their model mappings.
- CLI prompts use hidden input for API keys and report the files updated.
- The focused tests, full Python test suite, and `git diff --check` pass.
