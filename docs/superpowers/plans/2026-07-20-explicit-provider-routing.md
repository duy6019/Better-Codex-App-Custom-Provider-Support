# Explicit Provider Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Remove Automatic provider routing so every new task and Side Chat fork uses an explicitly selected provider, defaulting to OpenAI.

**Architecture:** The desktop ASAR patch remains the sole routing layer. It normalizes a missing or legacy auto picker value to the configured default provider, openai, and injects that concrete provider into thread/start and thread/fork. It never reads a model ID to select a provider.

**Tech Stack:** Python 3.9 standard library, embedded JavaScript unified diffs, unittest.

## Global Constraints

- Do not modify, build, replace, or configure the Codex CLI binary.
- Do not add source-thread caching, a thread/read request, or model-to-provider routing.
- The default provider is openai. 9router is used only after an explicit picker selection.
- Preserve the generated cx/ model catalog, 9router TOML/auth configuration, and Python 3.9 compatibility.
- Preserve existing uncommitted backup/reapply changes; do not discard them.

---

### Task 1: Lock the explicit-provider contract with failing template tests

**Files:**
- Modify: tests/test_sync_codex_models.py:176-201
- Test: tests/test_sync_codex_models.py

**Interfaces:**
- Consumes: patch_chatgpt_providers.CENTRAL_DIFF and patch_chatgpt_providers.PICKER_DIFF.
- Produces: regression assertions for OpenAI fallback, no Automatic picker item, no auto model routing, and a concrete provider for both task-start paths.

- [ ] **Step 1: Replace the current fork-routing expectation with explicit-routing tests**

~~~python
def test_provider_picker_defaults_legacy_auto_to_openai_without_showing_auto(self):
    self.assertEqual(patcher.DEFAULT_PROVIDER_CONFIG["default_provider"], "openai")
    self.assertNotIn("Automatic", patcher.PICKER_DIFF)
    self.assertNotIn("modelProviders[e?.model]", patcher.CENTRAL_DIFF)
    self.assertIn("e.defaultProvider", patcher.PICKER_DIFF)

def test_start_and_fork_use_the_explicit_picker_provider(self):
    self.assertIn("thread/start", patcher.CENTRAL_DIFF)
    self.assertIn("thread/fork", patcher.CENTRAL_DIFF)
    self.assertIn("modelProvider: await codexSelectedProvider()", patcher.CENTRAL_DIFF)
~~~

- [ ] **Step 2: Run the focused tests before production changes**

Run: python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests -v

Expected: FAIL because the embedded picker still renders Automatic, retains auto, and maps a model to a provider.

- [ ] **Step 3: Keep ReapplyTests unchanged**

The backup/reapply fixtures cover another behavior and must remain green.

### Task 2: Remove Auto from the embedded app patch

**Files:**
- Modify: patch_chatgpt_providers.py:194-218
- Modify: patch_chatgpt_providers.py:361-446
- Test: tests/test_sync_codex_models.py:176-201

**Interfaces:**
- Consumes: desktop-model-providers.json with providers and default_provider.
- Produces: codexSelectedProvider returning one configured provider ID and a picker without Automatic.

- [ ] **Step 1: Normalize local storage to a configured provider**

In both JavaScript contexts, a stored value is valid only if it matches a configured provider ID. A missing value or legacy auto resolves to config.defaultProvider, which is openai. On picker config load, write the normalized value back to local storage.

~~~javascript
function codexSelectedProvider() {
  return codexLoadProviderRoutingConfig(true).then((config) => {
    const saved = window.localStorage.getItem('codex.customProviderSelection.v1');
    return config.providers.some((provider) => provider.id === saved)
      ? saved
      : config.defaultProvider;
  });
}
~~~

- [ ] **Step 2: Delete Automatic UI and model routing**

Delete the JSX item with children Automatic and onSelect selecting auto. Delete the branch that reads modelProviders from codexProviderForThreadStart. Keep model_providers in the generated JSON only for backwards-compatible file shape; the app routing code must not consume it.

- [ ] **Step 3: Route both starts through the selected provider**

Replace the current request branch with one that handles both thread/start and thread/fork and always overwrites a stale request value with the current picker selection.

~~~javascript
if (
  (method === 'thread/start' || method === 'thread/fork') &&
  params != null &&
  typeof params === 'object'
) {
  return { ...params, modelProvider: await codexSelectedProvider() };
}
~~~

Selecting openai before Side Chat must produce an OpenAI fork. Selecting 9router must produce a 9router fork. An absent model must not alter that result.

- [ ] **Step 4: Run the focused template tests**

Run: python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests -v

Expected: PASS, including the existing malformed-diff assertions.

### Task 3: Document and verify the manual provider contract

**Files:**
- Modify: README.md:1-150
- Test: tests/test_sync_codex_models.py

**Interfaces:**
- Consumes: the provider picker and desktop-model-providers.json.
- Produces: instructions to choose the provider before creating or forking a task.

- [ ] **Step 1: Replace Auto-routing language in README**

Add this behavior statement near the provider menu section:

~~~markdown
The provider menu is explicit: it defaults to ChatGPT / OpenAI and has no
Automatic mode. Select 9router before starting a task or using Side Chat with
a 9router model. The selected provider is sent for both new tasks and forks.
Changing the model does not switch providers automatically.
~~~

- [ ] **Step 2: Run the full regression suite and patch-input checks**

Run: python3 -m unittest discover -v && git diff --check && python3 patch_chatgpt_providers.py --help && python3 sync_codex_models.py --help

Expected: all tests pass, diff check prints no whitespace errors, and both help commands exit 0. Do not run the installer against the installed ChatGPT app during this task.

- [ ] **Step 3: Review the dirty worktree before a commit**

Run: git diff -- patch_chatgpt_providers.py tests/test_sync_codex_models.py README.md

Expected: stage and commit only if every hunk belongs to this plan or the pre-existing reapply work. Otherwise leave unrelated work unstaged. If it is safe to commit:

~~~bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py README.md
git commit -m "fix: require explicit provider routing"
~~~

## Plan Self-Review

- Coverage: Task 1 defines the regression behavior, Task 2 removes Auto and always sends a concrete provider, and Task 3 documents and verifies the behavior.
- Scope: excludes CLI source, binary replacement, 9router credentials, thread metadata caching, and model aliases.
- Consistency: openai is the only fallback; 9router requires an explicit selection.

