# Better Codex App Custom Provider Support

An unofficial patch for the macOS ChatGPT/Codex desktop app that adds per-task model-provider selection without requiring you to sign out of your ChatGPT account.

The patch:

- Adds a provider section to the model menu.
- Filters the model picker to models assigned to the selected provider.
- Sends the explicitly selected provider when a new task starts or Side Chat forks.
- Keeps tasks from all configured providers visible.
- Keeps the normal ChatGPT login active for OpenAI models.

This project currently supports **macOS only**.

> [!CAUTION]
> Changing the provider in a running conversation/thread does **not** work. The conversation/thread continues using the provider it started with.

<img width="500" src="https://github.com/user-attachments/assets/9b61e720-35e9-4021-9c6f-bd77e334e471" />
<br>

## Requirements

- macOS
- Official ChatGPT `26.721.30844`, build `5813`, installed at `/Applications/ChatGPT.app`
- Python 3.9 or newer
- Node.js with `npx`
- Codex CLI available as `codex`

## Install

<img width="600" src="https://github.com/user-attachments/assets/8800efd1-d490-4bc3-9959-47ddff5a6db8" />

<br>
<br>

<img width="600" src="https://github.com/user-attachments/assets/90461000-8b4b-4632-93cc-125a116b0830" />

<br>
<br>

1. Download both `patch_chatgpt_providers.py` and `sync_codex_models.py` from the repository.
2. Run the patch script:

```bash
python3 patch_chatgpt_providers.py
```

3. Run the model sync script from the same directory:

```bash
python3 sync_codex_models.py
```

The installer closes processes belonging to the target app, maintains a verified clean original beside it, creates a transactional snapshot before mutation, patches `app.asar`, updates Electron's ASAR integrity metadata, and applies an ad-hoc signature.

Run `python3 patch_chatgpt_providers.py --help` to see alternate app and config paths.

## Sync Codex models and 9router

Run the sync script after patching, and again whenever the bundled Codex model catalog changes:

```bash
python3 sync_codex_models.py
```

The script asks for a 9router base URL. Press Enter to use the local default:

```text
http://127.0.0.1:20128/v1
```

For an unattended run or another endpoint, pass the URL explicitly:

```bash
python3 sync_codex_models.py --9router-base-url https://router.example/v1
```

Each run reads `codex debug models --bundled` and recreates all three files:

- `~/.codex/model-catalogs/custom.json`: every bundled Codex model plus a `cx/<slug>` clone labeled ` (9router)`.
- `~/.codex/desktop-model-providers.json`: OpenAI for original slugs and 9router for every `cx/` clone.
- `~/.codex/config.toml`: the root `model_catalog_json` entry and `[model_providers.9router]` table.

The script preserves all other TOML settings, including project configuration and an existing `[model_providers.9router.auth]` table. It does not change your global `model = ...` choice. It recreates the catalog and provider-routing JSON on every run, so do not hand-edit those generated files.

Use `--catalog`, `--provider-config`, and `--config` to target alternate paths, or `--codex-bin` when the Codex CLI has a different executable name. Run `python3 sync_codex_models.py --help` for details.

Restart ChatGPT/Codex after synchronization so it loads the new model catalog. Do not set a global `model_provider` if OpenAI and 9router should coexist in the desktop app; choose the provider from the menu before each new task or Side Chat fork.

## Configure the patched provider menu

The installer creates:

```text
~/.codex/desktop-model-providers.json
```

The sync script creates this file. A shortened example:

```json
{
  "version": 1,
  "default_provider": "openai",
  "providers": [
    {
      "id": "openai",
      "label": "ChatGPT / OpenAI",
      "description": "Uses your signed-in ChatGPT account"
    },
    {
      "id": "9router",
      "label": "9router",
      "description": "Uses [model_providers.9router] from config.toml"
    }
  ],
  "model_providers": {
    "cx/gpt-5.6-sol": "9router",
    "cx/gpt-5.6-terra": "9router"
  }
}
```

- `providers` defines the providers displayed in the app menu.
- `default_provider` is used when the saved provider choice is missing or from an older version.
- `model_providers` maps model slugs for model-picker filtering; it does not derive the provider used for requests.
- Every custom provider ID must match a `[model_providers.<id>]` section in `config.toml`.
- API keys do not belong in this JSON file.

The provider menu is explicit: it defaults to ChatGPT / OpenAI and has no Automatic mode. Select 9router before starting a task or using Side Chat with a 9router model. The selected provider is sent for both new tasks and forks. Changing the model does not switch providers automatically.

The selected provider also filters the model picker. Models listed in
`model_providers` appear only for their mapped provider; models not listed
there appear under `default_provider`. When switching providers, the picker
uses the matching `cx/` counterpart when available, otherwise the first model
in the new provider's catalog. This affects new model selection only; it does
not change the provider of an already-running conversation.

The app reloads this file when the provider menu opens and before a new task starts or forks. Repatching is not required after running the sync script.

## Updates and recovery

ChatGPT updates replace the patch. This revision supports the official
ChatGPT `26.721.30844`, build `5813`. A newer app build may change the generated
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
