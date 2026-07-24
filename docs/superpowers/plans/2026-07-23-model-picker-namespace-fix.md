# Model Picker Namespace Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the generated provider picker so Codex renders valid menu subcomponents instead of showing its generic error boundary when model selection opens.

**Architecture:** Keep the existing provider picker and routing flow unchanged. Add one regression test around the real `PICKER_DIFF` output, then replace the four invalid `zy` subcomponent references with the app bundle's existing `Ly` menu namespace and validate the corrected diff against the matching original ASAR in temporary storage.

**Tech Stack:** Python 3 standard library, `unittest`, embedded unified JavaScript diffs, Node.js syntax checking, Prettier 3.6.2, Electron ASAR 3.2.10.

## Global Constraints

- Do not modify `/Applications/ChatGPT.app`; the user will reapply the corrected patch.
- Preserve all pre-existing worktree changes in `patch_chatgpt_providers.py` and `tests/test_sync_codex_models.py`.
- Do not add or change JavaScript imports.
- Do not change provider configuration loading, fallback handling, local-storage selection, request routing, or backup behavior.
- Use `Ly` for provider menu subcomponents and continue using `zy` only for the dropdown root.

---

### Task 1: Correct provider menu subcomponent rendering

**Files:**
- Modify: `tests/test_sync_codex_models.py:227`
- Modify: `patch_chatgpt_providers.py:400-432`

**Interfaces:**
- Consumes: `PICKER_DIFF: str`, `parse_hunks(unified_diff: str) -> list[list[str]]`, and `apply_unified_diff(path: Path, unified_diff: str) -> None`.
- Produces: a `PICKER_DIFF` whose `CodexCustomProviderPickerSection` renders `Ly.Item`, `Ly.Title`, and `Ly.Separator` while the native dropdown root remains `zy`.

- [x] **Step 1: Write the failing regression test**

Add this method to `PatcherTemplateTests` before `test_picker_import_hunk_tolerates_added_upstream_initializers`:

```python
def test_provider_picker_renders_subcomponents_from_menu_namespace(self):
    hunk = patcher.parse_hunks(patcher.PICKER_DIFF)[0]
    diff = "@@ -1,1 +1,1 @@\n" + "\n".join(hunk) + "\n"
    source = "\n".join(line[1:] for line in hunk if line[0] in " -") + "\n"

    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary) / "picker.js"
        bundle.write_text(source, encoding="utf-8")

        patcher.apply_unified_diff(bundle, diff)

        patched = bundle.read_text(encoding="utf-8")

    provider_section = patched.split(
        "function CodexCustomProviderPickerSection()", 1
    )[1].split("function MO(e)", 1)[0]
    for component in ("Item", "Title", "Separator"):
        self.assertIn(f"Ly.{component}", provider_section)
        self.assertNotIn(f"zy.{component}", provider_section)
```

- [x] **Step 2: Run the focused test and verify the diagnosed failure**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_renders_subcomponents_from_menu_namespace -v
```

Expected: FAIL because `CodexCustomProviderPickerSection` contains `zy.Item`, `zy.Title`, and `zy.Separator`, so `Ly.Item` is not found.

- [x] **Step 3: Make the minimal production correction**

In `PICKER_DIFF`, change only the custom provider section to use the native menu namespace:

```javascript
c = e.providers.map((e) =>
  (0, FO.jsx)(
    Ly.Item,
    {
      RightIcon: a === e.id ? ct : void 0,
      SubText:
        e.description.length === 0
          ? null
          : (0, FO.jsx)(`span`, {
              className: `text-token-description-foreground`,
              children: e.description,
            }),
      onSelect: s(e.id),
      children: e.label,
    },
    e.id,
  ),
);
return (0, FO.jsxs)(FO.Fragment, {
  children: [
    (0, FO.jsx)(Ly.Title, { children: `Provider for new tasks` }),
    n == null
      ? null
      : (0, FO.jsx)(Ly.Item, {
          disabled: !0,
          SubText: (0, FO.jsx)(`span`, {
            className: `text-token-description-foreground`,
            children: n,
          }),
          children: `Provider config error — using fallback`,
        }),
    c,
    (0, FO.jsx)(Ly.Separator, {}),
  ],
});
```

Retain the leading `+` diff markers in the Python raw string; make no other edits to the embedded JavaScript.

- [x] **Step 4: Run the focused test and verify it passes**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_renders_subcomponents_from_menu_namespace -v
```

Expected: PASS.

- [x] **Step 5: Run the complete repository test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass with zero failures and errors.

- [x] **Step 6: Check the repository diff without staging user-owned changes**

Run:

```bash
git diff --check
git diff -- patch_chatgpt_providers.py tests/test_sync_codex_models.py
```

Expected: no whitespace errors; the diff contains the namespace correction and regression test alongside preserved pre-existing changes. Leave both files unstaged because they already contained user-owned modifications before this repair.

### Task 2: Validate against the matching original Codex bundle

**Files:**
- Modify: none in the repository or installed application.
- Temporary output: `/private/tmp/codex-picker-namespace-verify.*`

**Interfaces:**
- Consumes: `/Users/duy/.codex/ChatGPT-original.app/Contents/Resources/app.asar` and the corrected `PICKER_DIFF`.
- Produces: a temporary picker bundle that accepts the complete embedded diff, formats successfully, and passes `node --check`.

- [x] **Step 1: Create a unique temporary verification directory**

Run in a persistent shell session:

```bash
picker_verify_dir=$(mktemp -d /private/tmp/codex-picker-namespace-verify.XXXXXX)
```

Expected: prints no error and sets `picker_verify_dir` to a new directory under `/private/tmp`.

- [x] **Step 2: Extract the managed original ASAR into temporary storage**

Run:

```bash
npx --yes @electron/asar@3.2.10 extract /Users/duy/.codex/ChatGPT-original.app/Contents/Resources/app.asar "$picker_verify_dir/app"
```

Expected: exit 0 and an extracted `webview/assets` directory under `$picker_verify_dir/app`.

- [x] **Step 3: Format and apply the complete corrected picker diff**

Run:

```bash
python3 -c 'from pathlib import Path; import patch_chatgpt_providers as p; assets=Path(__import__("sys").argv[1]); picker=p.unique_candidate(assets, "settings-command-menu-section-items~new-thread-panel-page~settings-pag", ("composer.intelligenceDropdown.tooltip",), "model picker"); p.run(["npx", "--yes", p.PRETTIER_PACKAGE, "--write", str(picker)], label="Formatting original picker bundle"); p.apply_unified_diff(picker, p.PICKER_DIFF); p.run(["npx", "--yes", p.PRETTIER_PACKAGE, "--write", str(picker)], label="Formatting corrected picker bundle"); print(picker)' "$picker_verify_dir/app/webview/assets"
```

Expected: exit 0, exactly one picker bundle is selected, all three diff hunks apply, and Prettier reports the corrected file without a syntax error.

- [x] **Step 4: Run JavaScript syntax validation on the corrected bundle**

Run:

```bash
picker_bundle=$(rg -l 'CodexCustomProviderPickerSection' "$picker_verify_dir/app/webview/assets")
node --check "$picker_bundle"
```

Expected: exactly one path is assigned to `picker_bundle`; `node --check` exits 0 with no output.

- [x] **Step 5: Confirm the installed application was not modified**

Run:

```bash
stat -f '%Sm %N' /Applications/ChatGPT.app/Contents/Resources/app.asar
git status --short
```

Expected: the installed ASAR timestamp is unchanged from before implementation; only the planned repository files plus the user's pre-existing changes are present.
