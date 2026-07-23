# Provider-Filtered Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Codex model picker show only models assigned to the explicitly selected provider, and reconcile an incompatible selected model without restoring automatic provider routing.

**Architecture:** Keep `desktop-model-providers.json` as the source of provider-to-model assignments. Extend the picker bundle's shared provider state with subscriptions, filter the raw model catalog in the parent composer component before the app derives normal and advanced picker data, and reconcile the selected model in a React effect. Keep the central `thread/start` and `thread/fork` routing patch unchanged in purpose: it sends the explicit provider selection and never derives the provider from the model.

**Tech Stack:** Python 3.9+, `unittest`, embedded unified JavaScript diffs, React/Electron bundle code, Node.js, Prettier 3.6.2, `@electron/asar` 3.2.10

## Global Constraints

- Preserve macOS-only support and Python 3.9 compatibility.
- Do not change the `desktop-model-providers.json` version or schema.
- Assign a mapped model to `model_providers[slug]`; assign every unmapped model to `default_provider`.
- Filter every model-picker context; do not preserve a model selection from an older provider or an already-running conversation.
- Canonical counterpart matching removes exactly one leading `cx/` prefix and does not infer other namespaces.
- Do not add `All providers`, `Automatic`, or model-derived provider routing.
- Keep `thread/start` and `thread/fork` routed by the explicit provider selection, and keep `thread/list` visible across all providers.
- If a provider has no available model, show a disabled empty-state row and do not expose another provider's models.
- Do not modify `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during implementation or automated verification.
- Preserve the user's unrelated untracked `.agents/`, `.specify/`, and `docs/superpowers/plans/2026-07-23-model-picker-namespace-fix.md` files.

## File Structure

- Modify `patch_chatgpt_providers.py`: own all embedded picker JavaScript changes, including shared provider state, model filtering, selection reconciliation, and empty-state rendering.
- Modify `tests/test_sync_codex_models.py`: lock the embedded patch contract with focused regression tests and keep hunk-selection tests resilient to added hunks.
- Modify `README.md`: document the provider-filtered model list and replacement behavior.
- Do not modify `sync_codex_models.py`: it already generates `cx/...` clones and the required `model_providers` mapping.
- Do not create a new runtime module: the installed application consumes only the embedded diffs in `patch_chatgpt_providers.py`.

---

### Task 1: Add Shared Provider State and Source Model Filtering

**Files:**
- Modify: `tests/test_sync_codex_models.py:179-295`
- Modify: `patch_chatgpt_providers.py:239-455`

**Interfaces:**
- Consumes: normalized picker config `{ defaultProvider, providers, modelProviders }` and raw model options `Array<{ model: string, ... }> | undefined`.
- Produces: `codexProviderForModel(model, config) -> string`, `codexFilterModelsForProvider(models, config, provider) -> Array | undefined`, `codexPickerSetCustomProviderChoice(provider) -> string`, and `codexUseProviderFilteredModels(models) -> Array | undefined`.

- [ ] **Step 1: Add failing template tests for assignment, subscriptions, and provider publication**

Add these methods to `PatcherTemplateTests` after `test_start_and_fork_use_the_explicit_picker_provider`:

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

def test_picker_provider_state_notifies_model_filter_subscribers(self):
    self.assertIn("e.listeners ??= new Set()", patcher.PICKER_DIFF)
    self.assertIn("e.revision ??= 0", patcher.PICKER_DIFF)
    self.assertIn("for (let t of e.listeners) t(e.revision);", patcher.PICKER_DIFF)
    self.assertIn("codexPickerSetCustomProviderChoice(e)", patcher.PICKER_DIFF)
    self.assertIn("codexUseProviderFilteredModels", patcher.PICKER_DIFF)

def test_picker_import_hunk_is_found_by_content(self):
    hunk = next(
        hunk
        for hunk in patcher.parse_hunks(patcher.PICKER_DIFF)
        if any("CodexProviderPatchReact" in line for line in hunk)
    )
    self.assertTrue(any("CodexProviderPatchReact = t(m(), 1)" in line for line in hunk))
```

Replace the index-based hunk lookup at the start of
`test_picker_import_hunk_tolerates_added_upstream_initializers`:

```python
hunk = next(
    hunk
    for hunk in patcher.parse_hunks(patcher.PICKER_DIFF)
    if any("CodexProviderPatchReact" in line for line in hunk)
)
```

Delete the original line:

```python
hunk = patcher.parse_hunks(patcher.PICKER_DIFF)[2]
```

- [ ] **Step 2: Run the focused tests and confirm the new contract fails**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_assigns_models_to_mapped_or_default_provider \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_provider_state_notifies_model_filter_subscribers \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_import_hunk_is_found_by_content \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_import_hunk_tolerates_added_upstream_initializers \
  -v
```

Expected: the first two tests fail because the filtering and subscription helpers are absent; the two import-hunk tests pass after the test-only robustness change.

- [ ] **Step 3: Extend the embedded picker state with listeners and config publication**

In the first added JavaScript block of `PICKER_DIFF`, replace
`codexPickerProviderRoutingState` with this target JavaScript. Store every new
line as an added `+` line inside the embedded unified diff and update the hunk
header counts after editing:

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

Inside `codexPickerLoadProviderRoutingConfig`, replace the successful return:

```javascript
return ((t.config = a), (t.error = null), (t.loaded = !0), a);
```

with:

```javascript
return codexPickerAcceptProviderRoutingConfig(a, null);
```

Replace the complete catch return:

```javascript
return (
  (t.config = codexPickerProviderRoutingFallback()),
  (t.error = e instanceof Error ? e.message : String(e)),
  (t.loaded = !0),
  t.config
);
```

with:

```javascript
return codexPickerAcceptProviderRoutingConfig(
  codexPickerProviderRoutingFallback(),
  e instanceof Error ? e.message : String(e),
);
```

- [ ] **Step 4: Add provider assignment, selection publication, and the filtering hook**

Insert this target JavaScript after `codexWriteCustomProviderChoice` and before
`CodexCustomProviderPickerSection` in the first `PICKER_DIFF` hunk:

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
```

This hook deliberately returns `undefined` while the app model query is still
undefined and returns an empty array when the selected provider has no model.

- [ ] **Step 5: Publish provider changes from the provider section**

In the provider section's config-load effect, replace the `if (e)` body with:

```javascript
if (e) {
  let r = codexPickerProviderRoutingState();
  (t(n), i(r.error), o(r.selectedProvider));
}
```

Replace the provider selection handler:

```javascript
let s = (e) => (t) => {
  (t?.preventDefault(), codexWriteCustomProviderChoice(e), o(e));
},
```

with:

```javascript
let s = (e) => (t) => {
  (t?.preventDefault(), o(codexPickerSetCustomProviderChoice(e)));
},
```

- [ ] **Step 6: Run the focused tests and confirm the shared filtering contract passes**

Run the command from Step 2 again.

Expected: all four tests pass.

- [ ] **Step 7: Commit the shared provider filtering state**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "feat: add provider model filtering state"
```

---

### Task 2: Filter Composer Models and Reconcile the Selected Model

**Files:**
- Modify: `tests/test_sync_codex_models.py:179-310`
- Modify: `patch_chatgpt_providers.py:239-470`

**Interfaces:**
- Consumes: `codexUseProviderFilteredModels(models)` from Task 1, current model slug, current reasoning effort, and the existing `onSelectModel(model, reasoningEffort)` callback.
- Produces: `codexCanonicalModelSlug(model) -> string`, `codexFindProviderModelReplacement(models, selectedModel) -> model option | null`, and `codexReplacementReasoningEffort(modelOption, currentEffort) -> string | undefined`.

- [ ] **Step 1: Add failing tests for upstream filtering and deterministic replacement**

Add these methods to `PatcherTemplateTests` after the Task 1 tests:

```python
def test_picker_filters_raw_models_before_composer_derivations(self):
    self.assertIn(
        "y = codexUseProviderFilteredModels(_?.models)",
        patcher.PICKER_DIFF,
    )
    self.assertIn("U = Ob(y, T)", patcher.PICKER_DIFF)
    self.assertIn("te = xg(y, l)", patcher.PICKER_DIFF)
    self.assertIn("ne = Vg(y)", patcher.PICKER_DIFF)

def test_picker_reconciles_an_incompatible_selected_model(self):
    self.assertIn("function codexCanonicalModelSlug(e)", patcher.PICKER_DIFF)
    self.assertIn("e.startsWith(`cx/`) ? e.slice(3) : e", patcher.PICKER_DIFF)
    self.assertIn("function codexFindProviderModelReplacement(e, t)", patcher.PICKER_DIFF)
    self.assertIn("return r ?? e[0];", patcher.PICKER_DIFF)
    self.assertIn("function codexReplacementReasoningEffort(e, t)", patcher.PICKER_DIFF)
    self.assertIn("codexFindProviderModelReplacement(y, T)", patcher.PICKER_DIFF)
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_filters_raw_models_before_composer_derivations \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_reconciles_an_incompatible_selected_model \
  -v
```

Expected: both tests fail because the parent composer still uses `_?.models`
directly and replacement helpers do not exist.

- [ ] **Step 3: Add canonical counterpart and reasoning-effort helpers**

Insert this target JavaScript after `codexUseProviderFilteredModels` and before
`CodexCustomProviderPickerSection` in the first `PICKER_DIFF` hunk:

```javascript
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

- [ ] **Step 4: Add an embedded diff hunk that filters the raw composer model array**

In a temporary formatted copy of the matching original picker bundle, change
the parent composer component from:

```javascript
{ data: _, status: v } = Va({ hostId: f.hostId }),
  y = _?.models,
  {
    modelSettings: S,
```

to:

```javascript
{ data: _, status: v } = Va({ hostId: f.hostId }),
  y = codexUseProviderFilteredModels(_?.models),
  {
    modelSettings: S,
```

Generate a unified-diff hunk from that exact formatted source and append it to
`PICKER_DIFF` in source order. Keep enough context to include `Va`, the `y`
assignment, and the opening `modelSettings` destructure. This placement ensures
the existing lines `U = Ob(y, T)`, `te = xg(y, l)`, `ne = Vg(y)`, and the
`models: y` prop all consume the filtered array.

- [ ] **Step 5: Reconcile a model that is not present after filtering**

In the same parent composer function, insert this unconditional effect after
the existing `function ye(t, n)` definition and before `function be()`:

```javascript
CodexProviderPatchReact.useEffect(() => {
  let e = codexFindProviderModelReplacement(y, T);
  if (e == null) return;
  ye(e.model, codexReplacementReasoningEffort(e, S.reasoningEffort));
}, [y, T, S.reasoningEffort]);
```

Include this insertion in the parent-composer hunk generated in Step 4. Do not
add `ye` to the dependency array because it is recreated by the compiled
component; the stable data dependencies already cause one rerun after the
replacement model is selected.

- [ ] **Step 6: Run the focused tests and verify reconciliation passes**

Run the command from Step 2 again.

Expected: both tests pass.

- [ ] **Step 7: Verify the complete picker diff still applies to a synthetic hunk source**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests -v
```

Expected: all `PatcherTemplateTests` pass, including the content-based import
hunk lookup and provider-section namespace regression.

- [ ] **Step 8: Commit upstream filtering and selection reconciliation**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "feat: filter composer models by provider"
```

---

### Task 3: Render an Explicit Empty Provider State

**Files:**
- Modify: `tests/test_sync_codex_models.py:179-320`
- Modify: `patch_chatgpt_providers.py:239-480`

**Interfaces:**
- Consumes: the filtered `models` prop produced by Task 2.
- Produces: a disabled `Ly.Item` with the exact text `No models available for selected provider` when the filtered array is empty.

- [ ] **Step 1: Add a failing regression test for the empty-state row**

Add this method to `PatcherTemplateTests` after the reconciliation test:

```python
def test_picker_renders_disabled_empty_state_for_provider_without_models(self):
    self.assertIn("p.length === 0", patcher.PICKER_DIFF)
    self.assertIn(
        "No models available for selected provider",
        patcher.PICKER_DIFF,
    )
    self.assertIn("disabled: !0", patcher.PICKER_DIFF)
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_renders_disabled_empty_state_for_provider_without_models \
  -v
```

Expected: FAIL because the model row calculation still uses only `p?.map(...)`.

- [ ] **Step 3: Replace the model-row mapping with loading, empty, and populated branches**

In the `MO` function hunk inside `PICKER_DIFF`, replace the target patched
JavaScript assignment:

```javascript
o = p?.map((e) =>
  (0, FO.jsx)(
    NO,
    {
      keepOpenOnSelect: i,
      modelOption: e,
      selectedModel: u,
      selectedReasoningEffort: T,
      selectedServiceTier: I,
      selectedServiceTierIconKind: r ? null : L,
      stripGptPrefix: r,
      onSelect: (e, t) => {
        (y(e, t), i || v?.());
      },
    },
    e.model,
  ),
);
```

with:

```javascript
o =
  p == null
    ? null
    : p.length === 0
      ? (0, FO.jsx)(Ly.Item, {
          disabled: !0,
          children: `No models available for selected provider`,
        })
      : p.map((e) =>
          (0, FO.jsx)(
            NO,
            {
              keepOpenOnSelect: i,
              modelOption: e,
              selectedModel: u,
              selectedReasoningEffort: T,
              selectedServiceTier: I,
              selectedServiceTierIconKind: r ? null : L,
              stripGptPrefix: r,
              onSelect: (e, t) => {
                (y(e, t), i || v?.());
              },
            },
            e.model,
          ),
        );
```

Regenerate the affected unified-diff hunk against the formatted original
bundle so its line counts and context remain valid. Insert this hunk in
`PICKER_DIFF` in source order, before the existing provider-section hunk at
the `function MO(e)` insertion. Do not change the existing `Ly.Title`, scroll
container, or provider section ordering.

- [ ] **Step 4: Run the empty-state and namespace tests**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_renders_disabled_empty_state_for_provider_without_models \
  tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_renders_subcomponents_from_menu_namespace \
  -v
```

Expected: both tests pass and the empty row uses `Ly.Item`.

- [ ] **Step 5: Re-run all patch-template tests**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests -v
```

Expected: all tests pass, including explicit provider routing and hunk
compatibility regressions.

- [ ] **Step 6: Commit the empty provider state**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "feat: show empty provider model state"
```

---

### Task 4: Document and Verify the Complete Provider Filter

**Files:**
- Modify: `tests/test_sync_codex_models.py:179-330`
- Modify: `README.md:5-15`
- Modify: `README.md:77-130`
- Verify: `patch_chatgpt_providers.py`

**Interfaces:**
- Consumes: all embedded picker behavior from Tasks 1-3 and the unchanged generated routing JSON from `sync_codex_models.py`.
- Produces: user-facing documentation plus evidence that both embedded diffs apply, format, and pass JavaScript syntax validation against the clean ChatGPT 26.715.72359 backup.

- [ ] **Step 1: Add a failing documentation regression test**

Add this method to `PatcherTemplateTests`:

```python
def test_readme_documents_provider_filtered_model_picker(self):
    readme = Path(patcher.__file__).with_name("README.md").read_text(encoding="utf-8")
    self.assertIn("filters the model list to the selected provider", readme)
    self.assertIn("Unmapped models belong to `default_provider`", readme)
    self.assertIn("selects the matching `cx/` counterpart", readme)
```

- [ ] **Step 2: Run the documentation test and confirm it fails**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_readme_documents_provider_filtered_model_picker \
  -v
```

Expected: FAIL because the README still describes `model_providers` as a
compatibility-only field and does not describe filtering or replacement.

- [ ] **Step 3: Update the feature summary and provider-menu documentation**

In the opening feature list, add this bullet immediately after the provider
section bullet:

```markdown
- Selecting a provider filters the model list to the selected provider.
```

Replace the `model_providers` bullet in the configuration section with:

```markdown
- `model_providers` assigns model slugs to providers for model-menu filtering; it does not choose the request provider. Unmapped models belong to `default_provider`.
```

Replace the paragraph beginning `The provider menu is explicit` with:

```markdown
The provider menu is explicit: it defaults to ChatGPT / OpenAI and has no Automatic mode. Selecting a provider immediately filters every model picker. When the current model is not available for the new provider, the app selects the matching `cx/` counterpart when one exists, otherwise the first available model. Select 9router before starting a task or using Side Chat with a 9router model. The selected provider is sent for both new tasks and forks. Changing the model does not switch providers automatically.
```

Keep the existing running-conversation caution unchanged.

- [ ] **Step 4: Run the documentation test and full Python suite**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_readme_documents_provider_filtered_model_picker \
  -v
python3 -m unittest discover -v
```

Expected: the focused documentation test passes, then the complete suite passes
with no failures or errors.

- [ ] **Step 5: Run repository-level static checks**

Run:

```bash
git diff --check
python3 patch_chatgpt_providers.py --help
python3 sync_codex_models.py --help
```

Expected: `git diff --check` prints nothing; both help commands exit 0 and show
their usage text.

- [ ] **Step 6: Extract the clean ASAR into a temporary verification directory**

Run:

```bash
provider_filter_verify_dir=$(mktemp -d /private/tmp/codex-provider-filter-verify.XXXXXX)
npx --yes @electron/asar@3.2.10 extract \
  /Applications/ChatGPT-original.backup/Contents/Resources/app.asar \
  "$provider_filter_verify_dir/app"
echo "$provider_filter_verify_dir"
```

Expected: the extraction exits 0, prints a unique path under `/private/tmp`,
and creates `$provider_filter_verify_dir/app/webview/assets` without modifying
the backup.

- [ ] **Step 7: Format the original bundles, apply both complete embedded diffs, and format the result**

Run:

```bash
python3 -c 'from pathlib import Path; import sys; import patch_chatgpt_providers as p; assets=Path(sys.argv[1]); central=p.unique_candidate(assets, "artifact-tab-content.electron~notebook-preview-panel~app-main~business-checkout", ("async prewarmThreadStart(", "async sendConfigReadRequest("), "App Server client"); picker=p.unique_candidate(assets, "settings-command-menu-section-items~new-thread-panel-page~settings-pag", ("composer.intelligenceDropdown.tooltip",), "model picker"); p.run(["npx", "--yes", p.PRETTIER_PACKAGE, "--write", str(central), str(picker)], label="Formatting original verification bundles"); p.apply_unified_diff(central, p.CENTRAL_DIFF); p.apply_unified_diff(picker, p.PICKER_DIFF); p.run(["npx", "--yes", p.PRETTIER_PACKAGE, "--write", str(central), str(picker)], label="Formatting patched verification bundles"); print(central); print(picker)' "$provider_filter_verify_dir/app/webview/assets"
```

Expected: exactly one central bundle and one picker bundle are selected, every
hunk in both embedded diffs applies, and Prettier exits 0 before and after
patching.

- [ ] **Step 8: Run JavaScript syntax validation on both patched bundles**

Run:

```bash
provider_filter_central_bundle=$(rg -l 'codexPatchAppServerParams' "$provider_filter_verify_dir/app/webview/assets")
provider_filter_picker_bundle=$(rg -l 'CodexCustomProviderPickerSection' "$provider_filter_verify_dir/app/webview/assets")
node --check "$provider_filter_central_bundle"
node --check "$provider_filter_picker_bundle"
```

Expected: each `rg -l` command resolves exactly one file and both `node --check`
commands exit 0 with no output.

- [ ] **Step 9: Inspect the final diff for scope and routing invariants**

Run:

```bash
git diff -- README.md patch_chatgpt_providers.py tests/test_sync_codex_models.py
rg -n 'modelProviders\[.*model|Automatic|All providers' patch_chatgpt_providers.py README.md
```

Expected: the diff contains only provider-filter UI behavior, regression tests,
and documentation. The search must not find model-derived provider routing or
new `Automatic`/`All providers` UI; the README may still contain the sentence
stating that the menu has no Automatic mode.

- [ ] **Step 10: Commit documentation and final verification-ready state**

```bash
git add README.md patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "docs: explain provider-filtered model picker"
```

Expected: the commit contains the README update plus any final test-only hunk
robustness adjustments required by the verified embedded diff. The user's
unrelated untracked files remain untracked and untouched.

---

## Final Verification Checklist

- [ ] `python3 -m unittest discover -v` passes.
- [ ] `git diff --check` prints no errors.
- [ ] `python3 patch_chatgpt_providers.py --help` exits 0.
- [ ] `python3 sync_codex_models.py --help` exits 0.
- [ ] Both complete embedded diffs apply to a temporary extraction of the clean ChatGPT 26.715.72359 ASAR.
- [ ] Prettier 3.6.2 formats both patched temporary bundles successfully.
- [ ] `node --check` passes for both patched temporary bundles.
- [ ] `/Applications/ChatGPT.app` and `/Applications/ChatGPT-original.backup` remain unmodified.
- [ ] The final history contains small task-level commits and no unrelated user files.
