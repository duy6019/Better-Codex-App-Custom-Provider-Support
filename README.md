# Better Codex App Custom Provider Support

An unofficial patch for the macOS ChatGPT/Codex desktop app that adds per-task model-provider selection without requiring you to sign out of your ChatGPT account.

The patch:

- Adds a provider section to the model menu.
- Sends the explicitly selected provider when a new task starts or Side Chat forks.
- Keeps tasks from all configured providers visible.
- Keeps the normal ChatGPT login active for OpenAI models.

The desktop application patch is macOS-only. The standalone
`setup_custom_provider.py` wizard supports macOS Keychain and Windows
Credential Manager.

> [!CAUTION]
> Changing the provider in a running conversation/thread does **not** work. The conversation/thread continues using the provider it started with.

<img width="500" src="https://github.com/user-attachments/assets/9b61e720-35e9-4021-9c6f-bd77e334e471" />
<br>

## Requirements

- macOS for the desktop application patch
- Official ChatGPT `26.721.31836`, build `5828`, installed at `/Applications/ChatGPT.app`
- Python 3.9 or newer
- Node.js with `npx`
- Codex CLI available as `codex`

Windows is supported for the standalone `setup_custom_provider.py` wizard with
Windows Credential Manager; it does not support the desktop application patch.

## Install

<img width="600" src="https://github.com/user-attachments/assets/8800efd1-d490-4bc3-9959-47ddff5a6db8" />

<br>
<br>

<img width="600" src="https://github.com/user-attachments/assets/90461000-8b4b-4632-93cc-125a116b0830" />

<br>
<br>

1. Download `patch_chatgpt_providers.py`, `sync_codex_models.py`,
   `setup_custom_provider.py`, and `codex_config.py` from the repository.
2. Run the patch script:

```bash
python3 patch_chatgpt_providers.py
```

3. Run the model sync script from the same directory:

```bash
python3 sync_codex_models.py
```

4. Add 9router or another custom provider when needed:

```bash
python3 setup_custom_provider.py
```

The installer closes processes belonging to the target app, maintains a verified clean original beside it, creates a transactional snapshot before mutation, patches `app.asar`, updates Electron's ASAR integrity metadata, and applies an ad-hoc signature.

Run `python3 patch_chatgpt_providers.py --help` to see alternate app and config paths.

## Sync Codex models

Run the sync script after patching, and again whenever the bundled Codex model catalog changes:

```bash
python3 sync_codex_models.py
```

Each run reads `codex debug models --bundled`, then recreates
`~/.codex/model-catalogs/custom.json` with exactly the bundled Codex models.
It updates only the root `model_catalog_json` entry in
`~/.codex/config.toml`.

The command does not create aliases, configure a provider, or read or modify
`~/.codex/desktop-model-providers.json`. It preserves every provider table,
credential setting, project setting, and global `model = ...` choice in
`config.toml`.

Use `--catalog` and `--config` to target alternate paths, or `--codex-bin`
when the Codex CLI has a different executable name. Run
`python3 sync_codex_models.py --help` for details.

Restart ChatGPT/Codex after synchronization so it loads the updated catalog.

## Add a custom provider

Use the separate setup wizard to add or update one provider without editing
Codex configuration files manually:

```bash
python3 setup_custom_provider.py
```

On Windows, run:

```powershell
py setup_custom_provider.py
```

The wizard asks for the provider ID, display name, base URL, wire API, and
authentication mode. Choose the native secure-store option to keep the API key
out of configuration files: `keychain` on macOS stores it in macOS Keychain,
while `credential-manager` on Windows stores it as a Generic Credential in
Windows Credential Manager. Choose `none` for endpoints that do not require
authentication. The key is not written to `config.toml` or the provider-routing
JSON file. The stored credential is named `codex-<provider-id>`.

The wizard supports macOS and Windows. The application patch remains
macOS-specific.

The provider is added to the desktop provider menu. This wizard does not create
model catalog entries or model routing; choose a model supported by the endpoint,
then select the provider before starting a new task. Run the script again to
update that provider or add another provider.

## Configure the patched provider menu

The installer creates:

```text
~/.codex/desktop-model-providers.json
```

The patch installer creates this file with its OpenAI-only fallback. A shortened
example:

```json
{
  "version": 1,
  "default_provider": "openai",
  "providers": [
    {
      "id": "openai",
      "label": "ChatGPT / OpenAI",
      "description": "Uses your signed-in ChatGPT account"
    }
  ],
  "model_providers": {}
}
```

- `providers` defines the providers displayed in the app menu.
- `default_provider` is used when the saved provider choice is missing or from an older version.
- `model_providers` is retained for compatibility, but the desktop patch does not use model IDs to route requests.
- Every custom provider ID must match a `[model_providers.<id>]` section in `config.toml`.
- API keys do not belong in this JSON file.

Run `setup_custom_provider.py` to add 9router or another provider to this file.
The provider menu is explicit: it defaults to ChatGPT / OpenAI and has no
Automatic mode. Select the desired provider before starting a task or using
Side Chat. The selected provider is sent for both new tasks and forks. Changing
the model does not switch providers automatically.

The app reloads this file when the provider menu opens and before a new task
starts or forks. Repatching is not required after running either setup command.

## Updates and recovery

ChatGPT updates replace the patch. This revision supports the official
ChatGPT `26.721.31836`, build `5828`. A newer app build may change the generated
JavaScript again; wait for a compatible patch revision before rerunning the
installer.

The installer validates the expected bundle filename shape, source markers,
and exact patch contexts. If an app update changes them, it stops before
modifying the installed app.

For the default app path, recovery files are:

```text
/Applications/ChatGPT-original.backup
/Applications/ChatGPT-previous.backup
```

`ChatGPT-original.backup` is the clean source for every patch. `ChatGPT-previous.backup` exists only during an installation attempt and is used to restore the exact pre-patch state if installation fails. A successfully verified patch or rollback removes the previous snapshot.

The installer migrates a valid legacy `~/.codex/ChatGPT-original.app` into the sibling original and deletes the legacy copy only after the new copy verifies. Existing `ChatGPT.patch-failed-*.app` bundles are not removed automatically.

## Disclaimer

Use this script entirely at your own risk. It modifies the installed ChatGPT application in an unofficial and unsupported way.

The author and contributors provide no warranty and accept no responsibility or liability for any problems, damage, or loss caused directly or indirectly by using this script. This includes, but is not limited to, lost or corrupted chat history or other data, an unusable or "bricked" application, account warnings or restrictions, account suspension or banning, security or privacy issues, and any other direct or consequential damage.

Create and verify your own backups before running the script.

---

_This is an unofficial modification and is not affiliated with or supported by OpenAI._
