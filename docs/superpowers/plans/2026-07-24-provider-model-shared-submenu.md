# Provider and Model Shared Submenu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the provider selector at the start of the left power/model popup while leaving the right Model/Effort/Speed popup unmodified.

**Architecture:** The provider component remains embedded once in `PICKER_DIFF`. Its insertion is moved from the `Wcs` root popup wrapper to the native `kss` simple power/model view, which owns the `Compose` option and model choices. The existing `Qjs` advanced nested model-menu insertion remains intact.

**Tech Stack:** Python 3.9+, `unittest`, version-specific JavaScript unified-diff templates, Electron ASAR, Prettier, Node.js.

## Global Constraints

- Target only ChatGPT 26.721.31836 build 5828 and retain exact source contexts.
- Do not modify `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during tests.
- Keep provider routing explicit for `thread/start` and `thread/fork`; selecting a model must not infer a provider.
- Do not filter models, auto-select a replacement model, or change an existing task's provider.
- `Wcs` must retain its original `children: ee` content; Provider belongs at the start of the `kss` `YX.SimpleView` model menu and must remain in the nested `Qjs` menu.

---

### Task 1: Place Provider in the Native Left Model Menu

**Files:**
- Modify: `tests/test_sync_codex_models.py:358`
- Modify: `patch_chatgpt_providers.py:251`

**Interfaces:**
- Consumes: `patch_chatgpt_providers.PICKER_DIFF` and `parse_hunks()`.
- Produces: a build-5828 picker patch that inserts Provider before the native `kss` controls and preserves the existing `Qjs` nested-menu insertion.
- Preserves: `CodexCustomProviderPickerSection`, `codexWriteCustomProviderChoice`, explicit request routing, and the root `Wcs` `children: ee` expression.

- [x] **Step 1: Write the failing structural regression test**

  Replace `test_provider_picker_is_rendered_in_model_choice_menus_only` with:

  ```python
      def test_provider_picker_is_rendered_in_model_choice_menus_only(self):
          self.assertNotIn("children: ee", patcher.PICKER_DIFF)
          self.assertIn(
              """           className: YX.SimpleView,
  -          children: [E, M, P, I],
  +          children: [
  +            (0, XX.jsx)(CodexCustomProviderPickerSection, {}),
  +            E,""",
              patcher.PICKER_DIFF,
          )
          self.assertIn(
              """           children: [
  +            (0, TQ.jsx)(CodexCustomProviderPickerSection, {}),
               m,""",
              patcher.PICKER_DIFF,
          )
  ```

- [x] **Step 2: Run the focused test and verify RED**

  Run:

  ```bash
  python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_is_rendered_in_model_choice_menus_only -v
  ```

  Expected: failure because the old `Kcs` wrapper still edits `children: ee` and no `YX.SimpleView` hunk exists.

- [x] **Step 3: Move only the root-popup insertion hunk**

  Remove this complete hunk from `PICKER_DIFF`:

  ```diff
  @@ -521283,2 +521283,8 @@
            onOpenChange: G,
  -          children: ee,
  +          children: (0, Kcs.jsxs)(Kcs.Fragment, {
  +            children: [
  +              (0, Kcs.jsx)(CodexCustomProviderPickerSection, {}),
  +              ee,
  +            ],
  +          }),
  ```

  Insert this hunk before the existing `function Qjs(e)` hunk:

  ```diff
  @@ -519530,6 +519530,12 @@
       ? ((L = (0, XX.jsxs)(`div`, {
           className: YX.SimpleView,
  -          children: [E, M, P, I],
  +          children: [
  +            (0, XX.jsx)(CodexCustomProviderPickerSection, {}),
  +            E,
  +            M,
  +            P,
  +            I,
  +          ],
         })),
  ```

  Do not change the existing `Qjs` `TQ.jsx` Provider hunk, the provider component definition, or central request-routing diff.

- [x] **Step 4: Run the focused regression test and verify GREEN**

  Run:

  ```bash
  python3 -m unittest tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_is_rendered_in_model_choice_menus_only -v
  ```

  Expected: one passing test.

- [x] **Step 5: Verify exact source compatibility without touching either app**

  Run:

  ```bash
  python3 -m unittest discover -s tests -v
  git diff --check
  python3 - <<'PY'
  from pathlib import Path
  from tempfile import TemporaryDirectory

  import patch_chatgpt_providers as patcher

  with TemporaryDirectory(prefix="codex-provider-menu-verify-") as temporary:
      patcher.build_patched_artifacts(
          Path("/Applications/ChatGPT-original.backup"), Path(temporary)
      )
  PY
  ```

  Expected: all tests pass; diff check is silent; the temporary ASAR build completes after JavaScript formatting and syntax validation. The installed app and clean source remain untouched.

- [x] **Step 6: Inspect and commit the focused patch**

  Run:

  ```bash
  git diff --check
  git status --short
  git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
  git commit -m "fix: place provider in left model menu"
  ```

  Expected: the commit contains only the picker-diff relocation and its regression test; it excludes extraction artifacts and documentation.
