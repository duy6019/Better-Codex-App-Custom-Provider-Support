# Separate Provider Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make model synchronization provider-agnostic, keep provider setup in its dedicated wizard, and make the desktop patch default to OpenAI only.

**Architecture:** Move TOML, routing, and atomic-write primitives used by both commands to `codex_config.py`. `sync_codex_models.py` will only rebuild the bundled catalog and set `model_catalog_json`; `setup_custom_provider.py` will import the shared configuration primitives and remain the owner of provider routing, provider TOML, and credentials. The patch's JSON and JavaScript fallbacks will contain just the built-in OpenAI provider.

**Tech Stack:** Python 3.9 standard library, `unittest`, JSON, TOML text updates, embedded JavaScript unified diffs.

## Global Constraints

- Support Python 3.9 and add no dependencies.
- Keep all configuration writes atomic.
- Do not modify `desktop-model-providers.json` or provider TOML tables during a model-only sync.
- Preserve existing custom-provider and credential configuration.
- Provider choice, rather than model ID, determines the provider used by the patch.

---

## File Structure

- `codex_config.py`: catalog-independent configuration primitives shared by the sync command and provider wizard.
- `sync_codex_models.py`: bundled catalog validation, generation, command invocation, and `model_catalog_json` update only.
- `setup_custom_provider.py`: provider validation, credential storage, TOML provider tables, and provider-menu changes.
- `patch_chatgpt_providers.py`: generic initial provider-routing JSON and browser fallback.
- `tests/test_sync_codex_models.py`: catalog-only sync and patch fallback tests.
- `tests/test_setup_custom_provider.py`: provider-wizard regression coverage after imports move.
- `README.md`: three-step installation workflow and generic routing-file explanation.

### Task 1: Extract shared configuration primitives

**Files:**
- Create: `codex_config.py`
- Modify: `setup_custom_provider.py:17-28`
- Test: `tests/test_setup_custom_provider.py`

**Interfaces:**
- Produces: `ConfigError`, `codex_home() -> Path`, `validate_base_url(value: str) -> str`, `read_text(path: Path) -> str`, `atomic_write_text(path: Path, contents: str) -> None`, `atomic_write_json(path: Path, data: dict[str, Any]) -> None`, `toml_string(value: str) -> str`, `replace_toml_table(contents: str, table: str, body: str) -> str`, `read_provider_routing(path: Path) -> Optional[dict[str, Any]]`, and `upsert_provider_menu_entry(routing: Optional[dict[str, Any]], provider_id: str, label: str) -> dict[str, Any]`.
- Consumes: standard-library `json`, `os`, `re`, `stat`, `tempfile`, `Path`, and `urlparse` only.

- [ ] **Step 1: Write failing import-and-routing tests**

```python
import importlib.util

def test_shared_configuration_module_exists(self):
    self.assertIsNotNone(importlib.util.find_spec("codex_config"))
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest tests.test_setup_custom_provider.ProviderConfigurationTests.test_shared_provider_menu_defaults_to_openai_only -v`

Expected: FAIL because `find_spec("codex_config")` returns `None`.

- [ ] **Step 3: Create the shared module and repoint the wizard imports**

```python
# codex_config.py
class ConfigError(RuntimeError):
    """A safe, expected local configuration failure."""

def upsert_provider_menu_entry(routing, provider_id, label):
    current = copy.deepcopy(routing) if routing is not None else {
        "version": 1,
        "default_provider": "openai",
        "providers": [OPENAI_PROVIDER],
        "model_providers": {},
    }
    current["providers"] = [
        provider for provider in current["providers"]
        if provider["id"] != provider_id
    ] + [{
        "id": provider_id,
        "label": label,
        "description": f"Custom provider; uses [model_providers.{provider_id}] from config.toml",
    }]
    return current
```

Move the existing implementations of the listed interfaces from `sync_codex_models.py` without changing their data format or atomic-write behavior. Replace `setup_custom_provider.py` imports from `sync_codex_models` with imports from `codex_config`; make `SetupError` subclass `ConfigError`, and catch `ConfigError` in `main` and around configuration writes.

- [ ] **Step 4: Run provider-wizard tests**

Run: `python -m unittest tests.test_setup_custom_provider -v`

Expected: PASS.

- [ ] **Step 5: Commit the extracted primitives**

```bash
git add codex_config.py setup_custom_provider.py tests/test_setup_custom_provider.py
git commit -m "refactor: extract shared configuration helpers"
```

### Task 2: Reduce model synchronization to catalog-only behavior

**Files:**
- Modify: `sync_codex_models.py:1-244`
- Modify: `tests/test_sync_codex_models.py:1-240`

**Interfaces:**
- Consumes: `ConfigError`, `atomic_write_json`, `atomic_write_text`, `codex_home`, `read_text`, and `update_root_setting` from `codex_config`.
- Produces: `SyncError` as an alias of `ConfigError`, `build_catalog(catalog: dict[str, Any]) -> dict[str, Any]`, `update_codex_toml(contents: str, catalog_path: Path) -> str`, and `synchronize(codex_bin: str, catalog_path: Path, toml_path: Path, *, command_runner=...) -> None`.

- [ ] **Step 1: Replace provider-specific tests with catalog-only tests**

```python
def test_build_catalog_keeps_only_bundled_models(self):
    catalog = sync.build_catalog(FIXTURE_CATALOG)
    self.assertEqual(
        [model["slug"] for model in catalog["models"]],
        ["gpt-5.6-sol", "codex-auto-review"],
    )
    self.assertNotIn("cx/gpt-5.6-sol", json.dumps(catalog))

def test_synchronize_leaves_provider_files_and_tables_unchanged(self):
    routing_path.write_text('{"preserved": true}\n', encoding="utf-8")
    toml_path.write_text('[model_providers.9router]\nname = "9Router"\n', encoding="utf-8")
    sync.synchronize("codex", catalog_path, toml_path, command_runner=runner)
    self.assertEqual(routing_path.read_text(encoding="utf-8"), '{"preserved": true}\n')
    self.assertIn('[model_providers.9router]', toml_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run the focused sync tests to verify they fail**

Run: `python -m unittest tests.test_sync_codex_models.CatalogTests tests.test_sync_codex_models.TomlTests tests.test_sync_codex_models.SynchronizeTests -v`

Expected: FAIL because the command still creates aliases, routing, and a 9router table.

- [ ] **Step 3: Remove all provider setup from the sync command**

```python
def build_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    models = validate_bundled_catalog(catalog)
    generated_catalog = copy.deepcopy(catalog)
    generated_catalog["models"] = copy.deepcopy(models)
    return generated_catalog

def update_codex_toml(contents: str, catalog_path: Path) -> str:
    return update_root_setting(contents, "model_catalog_json", catalog_path.as_posix())

def synchronize(codex_bin, catalog_path, toml_path, *, command_runner=subprocess.run):
    bundled_catalog = read_bundled_catalog(codex_bin, command_runner=command_runner)
    catalog = build_catalog(bundled_catalog)
    updated_toml = update_codex_toml(read_text(toml_path), catalog_path)
    atomic_write_json(catalog_path, catalog)
    atomic_write_text(toml_path, updated_toml)
```

Delete `DEFAULT_BASE_URL`, URL prompting, clone generation, routing generation and merging, provider-config CLI arguments, and all provider-specific output. Change the command description to `Rebuild the Codex custom model catalog from the bundled CLI catalog.`

- [ ] **Step 4: Run the focused sync tests**

Run: `python -m unittest tests.test_sync_codex_models.CatalogTests tests.test_sync_codex_models.TomlTests tests.test_sync_codex_models.SynchronizeTests -v`

Expected: PASS.

- [ ] **Step 5: Commit the catalog-only command**

```bash
git add sync_codex_models.py tests/test_sync_codex_models.py
git commit -m "refactor: make model sync provider agnostic"
```

### Task 3: Make patch fallback routing provider-agnostic

**Files:**
- Modify: `patch_chatgpt_providers.py:48-125`
- Modify: `tests/test_sync_codex_models.py:241-286`

**Interfaces:**
- Produces: `DEFAULT_PROVIDER_CONFIG` with exactly one `openai` provider and `{}` model mappings.
- Produces: JavaScript `codexProviderRoutingFallback()` with exactly the same OpenAI-only fallback shape in camelCase.

- [ ] **Step 1: Write failing fallback tests**

```python
def test_patcher_default_template_is_provider_agnostic(self):
    self.assertEqual(
        patcher.DEFAULT_PROVIDER_CONFIG,
        {
            "version": 1,
            "default_provider": "openai",
            "providers": [{
                "id": "openai",
                "label": "ChatGPT / OpenAI",
                "description": "Built-in provider; uses your signed-in ChatGPT account",
            }],
            "model_providers": {},
        },
    )
    self.assertNotIn("9router", patcher.CENTRAL_DIFF)
```

- [ ] **Step 2: Run the focused patch test to verify it fails**

Run: `python -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_patcher_default_template_is_provider_agnostic -v`

Expected: FAIL because the initial JSON and JavaScript fallback contain 9router.

- [ ] **Step 3: Replace static 9router fallback data with generic data**

```python
DEFAULT_PROVIDER_CONFIG = {
    "version": 1,
    "default_provider": "openai",
    "providers": [{
        "id": "openai",
        "label": "ChatGPT / OpenAI",
        "description": "Built-in provider; uses your signed-in ChatGPT account",
    }],
    "model_providers": {},
}
```

Remove the 9router provider object and all `cx/*` entries from the embedded JavaScript fallback. Update the `CENTRAL_DIFF` hunk's added-line count so it matches the changed hunk content; this preserves patch application for the supported app build.

- [ ] **Step 4: Run patch-related unit tests**

Run: `python -m unittest tests.test_sync_codex_models.PatcherTemplateTests tests.test_provider_model_filter_revert -v`

Expected: PASS.

- [ ] **Step 5: Commit generic patch defaults**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "refactor: use generic provider patch defaults"
```

### Task 4: Document the separated workflow and verify all commands

**Files:**
- Modify: `README.md:45-195`
- Test: `tests/test_sync_codex_models.py`

**Interfaces:**
- Consumes: `sync_codex_models.py --help`, `setup_custom_provider.py --help`, and patch installation behavior.
- Produces: copyable instructions for patching, catalog synchronization, then optional provider setup.

- [ ] **Step 1: Update README workflow and routing-file documentation**

```markdown
1. Download `patch_chatgpt_providers.py`, `sync_codex_models.py`,
   `setup_custom_provider.py`, and `codex_config.py`.
2. Run `python3 patch_chatgpt_providers.py`.
3. Run `python3 sync_codex_models.py` to refresh only the model catalog.
4. Run `python3 setup_custom_provider.py` to add 9router or another provider.
```

Replace the `Sync Codex models and 9router` section with `Sync Codex models`; state that it recreates only `~/.codex/model-catalogs/custom.json` and updates only `model_catalog_json`. Replace the static 9router JSON example with an OpenAI-only initial file followed by an explanation that the provider wizard adds entries. Remove `--9router-base-url` and `--provider-config` from sync-command documentation.

- [ ] **Step 2: Run the complete verification suite**

Run: `python -m unittest discover -v && python sync_codex_models.py --help && python setup_custom_provider.py --help && python patch_chatgpt_providers.py --help`

Expected: all unittest cases pass; each help command exits with status `0`; the sync help has no 9router or provider-config option.

- [ ] **Step 3: Inspect the final change set**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the planned source, test, and README files are modified.

- [ ] **Step 4: Commit documentation and final tests**

```bash
git add README.md tests/test_sync_codex_models.py
git commit -m "docs: separate model sync from provider setup"
```
