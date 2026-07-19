# 9router Model Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild a Codex custom catalog from the bundled CLI catalog and configure 9router aliases, provider routing, and TOML automatically.

**Architecture:** A standalone standard-library Python command owns catalog discovery and generated configuration. The existing patcher retains ownership of app patching, but its static default routing and fallback UI configuration are renamed to 9router so a fresh installation uses the same provider identity.

**Tech Stack:** Python 3.9 standard library, `unittest`, Codex CLI, JSON, TOML text updates.

## Global Constraints

- Preserve support for Python 3.9 and do not add dependencies.
- Regenerate JSON outputs on every sync invocation.
- Preserve TOML content outside the exact managed key and provider table.
- Use `http://127.0.0.1:20128/v1` when the interactive URL prompt is accepted empty.

---

### Task 1: Add tested catalog and TOML synchronization command

**Files:**
- Create: `sync_codex_models.py`
- Create: `tests/test_sync_codex_models.py`

**Interfaces:**
- Produces: `build_catalog_and_routing(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]`
- Produces: `update_codex_toml(contents: str, catalog_path: Path, base_url: str) -> str`
- Produces: `synchronize(...) -> None`

- [ ] **Step 1: Write failing catalog tests**

```python
def test_build_catalog_and_routing_clones_every_bundled_model(self):
    catalog, routing = sync.build_catalog_and_routing(FIXTURE_CATALOG)
    self.assertEqual([model["slug"] for model in catalog["models"]],
                     ["gpt-5.6-sol", "gpt-5.5", "cx/gpt-5.6-sol", "cx/gpt-5.5"])
    self.assertEqual(routing["default_provider"], "openai")
    self.assertEqual(routing["model_providers"], {
        "cx/gpt-5.6-sol": "9router", "cx/gpt-5.5": "9router"})
```

- [ ] **Step 2: Run the failing test**

Run: `python3 -m unittest tests.test_sync_codex_models -v`
Expected: FAIL because `sync_codex_models` does not exist.

- [ ] **Step 3: Implement catalog parsing and generation**

```python
def build_catalog_and_routing(catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    models = validate_bundled_catalog(catalog)
    clones = [clone_model(model) for model in models]
    return {**catalog, "models": models + clones}, provider_routing(clones)
```

- [ ] **Step 4: Write failing TOML preservation tests**

```python
def test_update_codex_toml_replaces_only_managed_entries(self):
    updated = sync.update_codex_toml(EXISTING_TOML, Path("/tmp/custom.json"), BASE_URL)
    self.assertIn('model_catalog_json = "/tmp/custom.json"', updated)
    self.assertIn('[model_providers.9router.auth]', updated)
    self.assertIn('[projects."/work"]', updated)
```

- [ ] **Step 5: Implement atomic writes, TOML update, prompt, and CLI invocation**

```python
def synchronize(codex_bin: str, catalog_path: Path, routing_path: Path,
                toml_path: Path, base_url: str) -> None:
    bundled = json.loads(run([codex_bin, "debug", "models", "--bundled"],
                             label="Reading bundled Codex model catalog").stdout)
    catalog, routing = build_catalog_and_routing(bundled)
    atomic_write_json(catalog_path, catalog)
    atomic_write_json(routing_path, routing)
    atomic_write_text(toml_path, update_codex_toml(read_text(toml_path), catalog_path, base_url))
```

- [ ] **Step 6: Run the unit tests**

Run: `python3 -m unittest tests.test_sync_codex_models -v`
Expected: PASS.

### Task 2: Align the patcher template and fallbacks with 9router

**Files:**
- Modify: `patch_chatgpt_providers.py`
- Test: `tests/test_sync_codex_models.py`

**Interfaces:**
- Consumes: current static provider configuration and the existing JavaScript fallback literals.
- Produces: `DEFAULT_PROVIDER_CONFIG` and browser fallback routing using provider id `9router`.

- [ ] **Step 1: Add a failing static-template test**

```python
def test_patcher_default_template_uses_9router(self):
    self.assertEqual(patcher.DEFAULT_PROVIDER_CONFIG["providers"][1]["id"], "9router")
    self.assertNotIn("openrouter", patcher.CENTRAL_DIFF)
    self.assertNotIn("openrouter", patcher.PICKER_DIFF)
```

- [ ] **Step 2: Run the failing test**

Run: `python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests -v`
Expected: FAIL because the template uses `openrouter`.

- [ ] **Step 3: Replace OpenRouter static configuration with 9router**

```python
DEFAULT_PROVIDER_CONFIG = {
    "version": 1,
    "default_provider": "openai",
    "providers": [OPENAI_PROVIDER, NINE_ROUTER_PROVIDER],
    "model_providers": NINE_ROUTER_MODEL_MAPPINGS,
}
```

- [ ] **Step 4: Run all unit tests**

Run: `python3 -m unittest discover -v`
Expected: PASS.

### Task 3: Document the workflow

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `sync_codex_models.py --help` behavior.
- Produces: installation and repeat-sync instructions users can execute without editing TOML manually.

- [ ] **Step 1: Document command usage and generated files**

```markdown
python3 sync_codex_models.py
python3 sync_codex_models.py --9router-base-url https://router.example/v1
```

- [ ] **Step 2: Document prompt default and restart requirement**

```markdown
Press Enter to accept `http://127.0.0.1:20128/v1`. Restart ChatGPT/Codex after
the command writes `config.toml` or the model catalog.
```

- [ ] **Step 3: Run final verification**

Run: `python3 -m unittest discover -v && python3 sync_codex_models.py --help && python3 patch_chatgpt_providers.py --help`
Expected: all tests pass and both help commands exit with status 0.
