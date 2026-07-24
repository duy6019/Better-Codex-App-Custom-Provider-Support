# Provider-Filtered Model Picker Build 5813 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore provider-aware model filtering in the ChatGPT `26.721.30844` / build `5813` consolidated model picker.

**Architecture:** Extend the existing picker-side provider state with revision listeners, filter the raw catalog models before ChatGPT derives picker state, and reconcile a selected model that disappears after a provider change. Keep the current central explicit routing patch and exact `app-initial-*.js` bundle discovery unchanged.

**Tech Stack:** Python 3.9+, `unittest`, embedded JavaScript unified diffs, Electron ASAR, Prettier 3.6.2, Node.js `vm`/`node --check`.

## Global Constraints

- Support only ChatGPT `26.721.30844`, build `5813`.
- Modify only the picker-side embedded patch for the new behavior; do not change `sync_codex_models.py` or the provider JSON schema.
- Assign a mapped model to `model_providers[slug]`; assign an unmapped model to `default_provider`.
- Filter the raw model array before normal, advanced, reasoning, and power-picker derivations.
- Keep `thread/start` and `thread/fork` routed by the explicit provider selection; never derive request provider from model.
- Keep `thread/list` visible across all providers.
- Do not add Automatic or All providers options.
- Preserve `codex.customProviderSelection.v1`, fallback config, and visible config-error behavior.
- Do not modify `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during implementation or verification.
- Every task ends with a focused test run and a commit.

---

## File Map

- `tests/test_sync_codex_models.py`: focused contract and JavaScript behavior tests for the embedded picker diff.
- `patch_chatgpt_providers.py`: build-5813 `PICKER_DIFF` state helpers and model-picker hunks; `CENTRAL_DIFF` remains unchanged.
- `README.md`: user-visible provider-filtering behavior and model replacement rules.
- `docs/superpowers/specs/2026-07-24-provider-model-filter-build-5813-design.md`: approved design; do not rewrite during implementation.

### Task 1: Add failing tests for provider assignment and picker filtering

**Files:**
- Modify: `tests/test_sync_codex_models.py` in `PatcherTemplateTests` after the existing explicit-provider tests.

**Interfaces:**
- Consumes: `patcher.PICKER_DIFF`, `patcher.CENTRAL_DIFF`, `patcher.parse_hunks`.
- Produces: regression tests that fail against the current patch because the filtering helpers and model-picker hunk do not exist.

- [x] **Step 1: Write the failing static contract tests.**

Add these methods:

```python
def test_picker_assigns_models_to_mapped_or_default_provider(self):
    self.assertIn(
        "return t.modelProviders[e] ?? t.defaultProvider;",
        patcher.PICKER_DIFF,
    )
    self.assertIn(
        "e.filter((e) => codexProviderForModel(e.model, t) === n)",
        patcher.PICKER_DIFF,
    )

def test_picker_filters_raw_models_before_composer_derivations(self):
    self.assertIn(
        "x = codexUseProviderFilteredModels(y?.models)",
        patcher.PICKER_DIFF,
    )
    self.assertIn("S = g.model;", patcher.PICKER_DIFF)
    self.assertLess(
        patcher.PICKER_DIFF.index("x = codexUseProviderFilteredModels(y?.models)"),
        patcher.PICKER_DIFF.index("S = g.model;"),
    )

def test_picker_provider_state_notifies_model_filter_subscribers(self):
    self.assertIn("e.listeners ??= new Set()", patcher.PICKER_DIFF)
    self.assertIn("e.revision ??= 0", patcher.PICKER_DIFF)
    self.assertIn("for (let t of e.listeners) t(e.revision);", patcher.PICKER_DIFF)
    self.assertIn("codexPickerSetCustomProviderChoice(e)", patcher.PICKER_DIFF)
    self.assertIn("codexUseProviderFilteredModels", patcher.PICKER_DIFF)

def test_picker_reconciles_an_incompatible_selected_model(self):
    self.assertIn("function codexCanonicalModelSlug(e)", patcher.PICKER_DIFF)
    self.assertIn("e.startsWith(`cx/`) ? e.slice(3) : e", patcher.PICKER_DIFF)
    self.assertIn(
        "function codexFindProviderModelReplacement(e, t)",
        patcher.PICKER_DIFF,
    )
    self.assertIn("return r ?? e[0];", patcher.PICKER_DIFF)
    self.assertIn(
        "function codexReplacementReasoningEffort(e, t)",
        patcher.PICKER_DIFF,
    )
    self.assertIn(
        "codexFindProviderModelReplacement(x, S)",
        patcher.PICKER_DIFF,
    )
```

- [x] **Step 2: Add a real JavaScript behavior test for assignment and replacement.**

Extract the first `PICKER_DIFF` hunk into a Node `vm` context and exercise the
helpers with a provider config and catalog:

```python
def test_picker_model_filter_assigns_and_replaces_models(self):
    source = "\n".join(
        line[1:]
        for line in patcher.parse_hunks(patcher.PICKER_DIFF)[0]
        if line[0] in " +"
    )
    helpers = re.search(
        r"function codexPickerProviderRoutingFallback\(\) \{.*?"
        r"(?=function CodexCustomProviderPickerSection\(\))",
        source,
        re.DOTALL,
    )
    self.assertIsNotNone(helpers)
    script = f"""
const vm = require('node:vm');
const context = {{
  Set,
  window: {{ localStorage: {{ getItem: () => null }} }},
  CodexProviderPatchReact: {{
    useState: (value) => [value, () => {{}}],
    useEffect: () => {{}},
    useMemo: (callback) => callback(),
  }},
}};
vm.createContext(context);
vm.runInContext({helpers.group()!r}, context);
const config = {{
  defaultProvider: 'openai',
  providers: [{{ id: 'openai' }}, {{ id: '9router' }}],
  modelProviders: {{ 'cx/gpt-5.6-sol': '9router' }},
}};
const models = [
  {{ model: 'gpt-5.6-sol' }},
  {{ model: 'cx/gpt-5.6-sol' }},
  {{ model: 'gpt-5.4' }},
];
const filtered = context.codexFilterModelsForProvider(models, config, '9router');
const replacement = context.codexFindProviderModelReplacement(filtered, 'gpt-5.6-sol');
process.stdout.write(JSON.stringify([filtered.map((item) => item.model), replacement.model]));
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, check=True, text=True)
    self.assertEqual(json.loads(result.stdout), [["cx/gpt-5.6-sol"], "cx/gpt-5.6-sol"])
```

Add `import re` if the test module does not already import it; retain the
existing `json` and `subprocess` imports.

- [x] **Step 3: Run the focused tests and verify the RED state.**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_assigns_models_to_mapped_or_default_provider \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_filters_raw_models_before_composer_derivations \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_provider_state_notifies_model_filter_subscribers \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_reconciles_an_incompatible_selected_model \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_model_filter_assigns_and_replaces_models -v
```

Expected: the tests fail because the current build-5813 picker patch has no
filtering helpers or `x = codexUseProviderFilteredModels(y?.models)` hunk.

- [x] **Step 4: Commit the failing tests.**

```bash
git add tests/test_sync_codex_models.py
git commit -m "test: specify provider-filtered build 5813 picker"
```

### Task 2: Add shared provider state and filtering helpers

**Files:**
- Modify: `patch_chatgpt_providers.py` in the first `PICKER_DIFF` hunk after `codexPickerProviderRoutingFallback` and before `CodexCustomProviderPickerSection`.
- Test: focused tests from Task 1.

**Interfaces:**
- Consumes: existing normalized picker config and `CodexProviderPatchReact`.
- Produces: `codexPickerSetCustomProviderChoice`, `codexProviderForModel`, `codexFilterModelsForProvider`, and `codexUseProviderFilteredModels`.

- [x] **Step 1: Extend shared picker state and config publication.**

Replace the current state function with:

```javascript
function codexPickerProviderRoutingState() {
  let e = (window.__codexDesktopModelProvidersPatchV2 ??= {
    config: codexPickerProviderRoutingFallback(),
    configPath: null,
    error: null,
    loaded: !1,
    promise: null,
  });
  return (
    (e.listeners ??= new Set()),
    (e.revision ??= 0),
    (e.selectedProvider ??= codexReadCustomProviderChoice(e.config)),
    e
  );
}
function codexPickerPublishProviderRoutingState() {
  let e = codexPickerProviderRoutingState();
  e.revision += 1;
  for (let t of e.listeners) t(e.revision);
}
function codexPickerAcceptProviderRoutingConfig(e, t) {
  let n = codexPickerProviderRoutingState(),
    r = codexReadCustomProviderChoice(e);
  return (
    (n.config = e),
    (n.error = t),
    (n.loaded = !0),
    (n.selectedProvider = r),
    codexWriteCustomProviderChoice(r),
    codexPickerPublishProviderRoutingState(),
    e
  );
}
```

Change the config loader returns to:

```javascript
return codexPickerAcceptProviderRoutingConfig(a, null);
```

and:

```javascript
return codexPickerAcceptProviderRoutingConfig(
  codexPickerProviderRoutingFallback(),
  e instanceof Error ? e.message : String(e),
);
```

- [x] **Step 2: Add assignment, filter, and subscription helpers.**

Insert after `codexWriteCustomProviderChoice`:

```javascript
function codexPickerSetCustomProviderChoice(e) {
  let t = codexPickerProviderRoutingState(),
    n = t.config.providers.some((t) => t.id === e) ? e : t.config.defaultProvider;
  return (
    (t.selectedProvider = n),
    codexWriteCustomProviderChoice(n),
    codexPickerPublishProviderRoutingState(),
    n
  );
}
function codexProviderForModel(e, t) {
  return t.modelProviders[e] ?? t.defaultProvider;
}
function codexFilterModelsForProvider(e, t, n) {
  return e == null
    ? e
    : e.filter((e) => codexProviderForModel(e.model, t) === n);
}
function codexUseProviderFilteredModels(e) {
  let t = codexPickerProviderRoutingState(),
    [n, r] = CodexProviderPatchReact.useState(t.revision);
  CodexProviderPatchReact.useEffect(() => {
    let e = (e) => r(e);
    return (
      t.listeners.add(e),
      r(t.revision),
      codexPickerLoadProviderRoutingConfig(),
      () => {
        t.listeners.delete(e);
      }
    );
  }, [t]);
  let i = t.config,
    a = t.selectedProvider ?? codexReadCustomProviderChoice(i);
  return CodexProviderPatchReact.useMemo(
    () => codexFilterModelsForProvider(e, i, a),
    [e, i, a, n],
  );
}
function codexCanonicalModelSlug(e) {
  return e.startsWith(`cx/`) ? e.slice(3) : e;
}
function codexFindProviderModelReplacement(e, t) {
  if (e == null || e.length === 0 || e.some((e) => e.model === t)) return null;
  let n = codexCanonicalModelSlug(t),
    r = e.find((e) => codexCanonicalModelSlug(e.model) === n);
  return r ?? e[0];
}
function codexReplacementReasoningEffort(e, t) {
  return e.supportedReasoningEfforts?.some((e) => e.reasoningEffort === t)
    ? t
    : e.defaultReasoningEffort;
}
```

- [x] **Step 3: Publish provider changes from the picker section.**

Change the config-load effect body to:

```javascript
if (e) {
  let r = codexPickerProviderRoutingState();
  (t(n), i(r.error), o(r.selectedProvider));
}
```

Change the selection handler to:

```javascript
let s = (e) => (t) => {
  (t?.preventDefault(), o(codexPickerSetCustomProviderChoice(e)));
},
```

- [x] **Step 4: Run the helper-focused tests and verify GREEN.**

Run the four tests that exercise the helpers and provider publication:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_assigns_models_to_mapped_or_default_provider \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_provider_state_notifies_model_filter_subscribers \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_reconciles_an_incompatible_selected_model \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_model_filter_assigns_and_replaces_models -v
```

Expected: all four pass. The placement test
`test_picker_filters_raw_models_before_composer_derivations` remains the only
expected failure until Task 3 adds the composer hunk.

- [x] **Step 5: Commit the helper implementation.**

```bash
git add patch_chatgpt_providers.py
git commit -m "feat: add provider model filtering helpers"
```

### Task 3: Filter the consolidated composer picker and reconcile selections

**Files:**
- Modify: `patch_chatgpt_providers.py` by appending two hunks to `PICKER_DIFF` before its import hunk.
- Test: `tests/test_sync_codex_models.py` placement and reconciliation tests.

**Interfaces:**
- Consumes: Task 2 helpers and current build-5813 composer function `DMs`.
- Produces: a filtered `x` array used by every existing picker derivation and a safe effect for incompatible selected models.

- [x] **Step 1: Add the raw-model replacement hunk.**

Use this exact source context from the formatted build-5813 bundle:

```diff
@@ -550030,7 +550030,7 @@
     { data: y, status: b } = UM({
       additionalAvailableModels: void 0,
       hostId: d.hostId,
     }),
-    x = y?.models,
+    x = codexUseProviderFilteredModels(y?.models),
     S = g.model;
```

The diff applier ignores header line numbers but requires the unchanged lines
to match exactly; keep the hunk's context exactly as shown.

- [x] **Step 2: Add the reconciliation effect before `function Se`.**

Append this hunk after the existing `function xe` body and before
`function Se(e, t)`:

```diff
@@ -550170,6 +550170,12 @@
     );
   }
+  CodexProviderPatchReact.useEffect(() => {
+    let e = codexFindProviderModelReplacement(x, S);
+    if (e == null) return;
+    xe(e.model, codexReplacementReasoningEffort(e, g.reasoningEffort));
+  }, [x, S, g.reasoningEffort]);
   function Se(e, t) {
     return v(e, t);
   }
```

The effect must run after the callback declaration, outside render-time code,
and must not alter the explicit provider routing helpers.

- [x] **Step 3: Run focused tests and syntax checks.**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_filters_raw_models_before_composer_derivations \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_reconciles_an_incompatible_selected_model \
  tests.test_sync_codex_models.PatcherTemplateTests.test_start_and_fork_use_the_explicit_picker_provider -v
git diff --check
```

Expected: all focused tests pass and `git diff --check` prints no output.

- [x] **Step 4: Commit the consolidated-picker patch.**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "feat: filter build 5813 models by provider"
```

### Task 4: Document behavior and verify the complete temporary artifact

**Files:**
- Modify: `README.md` provider configuration and updates sections.
- Modify: `patch_chatgpt_providers.py` completion-summary copy.
- Test: `tests/test_sync_codex_models.py` completion-summary contract.
- Test: full `tests/` suite and temporary clean-original artifact.

**Interfaces:**
- Consumes: completed picker patch and existing provider config schema.
- Produces: user-facing instructions and evidence that the live app was not modified.

- [x] **Step 1: Update README provider behavior.**

After the provider menu explanation, add:

```markdown
The selected provider also filters the model picker. Models listed in
`model_providers` appear only for their mapped provider; models not listed
there appear under `default_provider`. When switching providers, the picker
uses the matching `cx/` counterpart when available, otherwise the first model
in the new provider's catalog. This affects new model selection only; it does
not change the provider of an already-running conversation.
```

Update the generated-config bullets so `model_providers` says it is the active
model-picker mapping as well as a compatibility field, while retaining the
warning not to put credentials in the JSON file.

Add a focused completion-summary test, watch it fail against the legacy copy,
then change the `model_providers` terminal bullet to:

```python
"Maps model slugs for picker filtering; model IDs do not choose a request provider."
```

- [x] **Step 2: Run the complete test suite and CLI checks.**

```bash
python3 -m unittest -v
git diff --check
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
```

Expected: all tests pass, no diff-check output, and both help commands exit 0.

- [x] **Step 3: Build and inspect a temporary patched ASAR.**

Run a Python verification script that calls
`patcher.build_patched_artifacts(Path('/Applications/ChatGPT-original.backup'), temp_work)`,
extracts the returned ASAR, and asserts the single `app-initial-*.js` contains:

```python
assert "CodexCustomProviderPickerSection" in source
assert "codexUseProviderFilteredModels" in source
assert "codexFindProviderModelReplacement" in source
assert "modelProviders: []" in source
```

The script must also run `node --check` through the production build helper and
must not call `install_patched_artifacts`.

- [x] **Step 4: Verify app identity and protected-file hashes.**

```bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/ChatGPT-original.backup/Contents/Info.plist
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' /Applications/ChatGPT-original.backup/Contents/Info.plist
shasum -a 256 /Applications/ChatGPT.app/Contents/Resources/app.asar /Applications/ChatGPT-original.backup/Contents/Resources/app.asar
shasum -a 256 /Applications/ChatGPT.app/Contents/Info.plist /Applications/ChatGPT-original.backup/Contents/Info.plist
```

Expected: version `26.721.30844` and build `5813`. Record each protected
file's hash before and after automated verification and confirm it is stable.
The live and original hashes may differ when the user has already installed an
earlier patch; automated verification must not change either file.

- [x] **Step 5: Commit documentation and final verification evidence.**

```bash
git add README.md
git commit -m "docs: explain provider-filtered model picker"
```
