# ChatGPT Build 5848 Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely patch only the installed macOS ChatGPT `26.721.41059` build `5848` while preserving explicit provider selection and request routing.

**Architecture:** Replace the former macOS build-5828 variant with one exact build-5848 variant. Its discovery markers and unified-diff contexts come from the formatted `app-initial-BHB6SClA.js` bundle; the existing Windows variants remain independent and unchanged. The patcher must still require one filename match, one supported variant, and exactly one match for every hunk before it creates a patched ASAR.

**Tech Stack:** Python 3.9+, `unittest`, embedded JavaScript unified diffs, Prettier 3.6.2, Node.js syntax checking, Electron ASAR 3.2.10.

## Global Constraints

- Support macOS ChatGPT version `26.721.41059`, build `5848`, and bundle `app-initial-BHB6SClA.js` only.
- Remove macOS build `5828` support; retain both existing Windows Store variants unchanged.
- Require exactly one `app-initial-*.js` file with exactly one complete supported marker set.
- Use build-5848 source contexts: `o9t`/`abe`/`s9t`, `tp(...)`, and `CMs`/`wQ`/`yz`/`Ym`.
- Route only `thread/start` and `thread/fork` through the explicitly selected provider; leave `thread/list` cross-provider with an empty `modelProviders` fallback.
- Do not filter catalog models, infer a provider from a model ID, or replace the user-selected model.
- Do not mutate `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during automated artifact verification.
- Do not modify `sync_model_catalog.py`, the provider-routing JSON schema, or Windows package logic.

---

## File structure

- `patch_chatgpt_providers.py`: macOS build identity, build-5848 routing/picker diffs, and CLI support text. Its existing Windows-specific patch constants and variants remain untouched.
- `tests/test_sync_codex_models.py`: exact marker discovery, variant selection, JavaScript-diff contracts, and CLI help checks.
- `tests/test_provider_model_filter_revert.py`: macOS support-version and no-model-filter regression coverage.
- `README.md`: the public macOS requirement and update/recovery compatibility statement.

### Task 1: Replace the macOS bundle identity with build 5848

**Files:**
- Modify: `tests/test_sync_codex_models.py:CurrentBundleTests`
- Modify: `patch_chatgpt_providers.py:BUILD_5848_BUNDLE_MARKERS` and `BUNDLE_PATCH_VARIANTS`

**Interfaces:**
- Consumes: `unique_candidate(...)` and `_matching_bundle_patch_variants(source)`.
- Produces: `BUILD_5848_BUNDLE_MARKERS: tuple[str, ...]` and a `BundlePatchVariant` named `"ChatGPT 26.721.41059 build 5848 application"`.

- [ ] **Step 1: Write failing discovery and identity tests.**

  Replace the build-5828 fixture with the installed build-5848 filename and assert its selected variant name:

  ```python
  def test_current_patch_bundle_finds_build_5848_app_initial(self):
      with tempfile.TemporaryDirectory() as temporary:
          assets = Path(temporary)
          expected = self.write_bundle(
              assets,
              "app-initial-BHB6SClA.js",
              patcher.BUILD_5848_BUNDLE_MARKERS,
          )

          self.assertEqual(patcher.current_patch_bundle(assets), expected)
          self.assertEqual(
              patcher.bundle_patch_variant(expected).name,
              "ChatGPT 26.721.41059 build 5848 application",
          )
  ```

  Replace the old static-marker test with this exact contract:

  ```python
  def test_build_5848_markers_include_verified_minified_symbols(self):
      self.assertIn("function o9t(e)", patcher.BUILD_5848_BUNDLE_MARKERS)
      self.assertIn("function CMs(e)", patcher.BUILD_5848_BUNDLE_MARKERS)
      self.assertIn("async function tp(...e)", patcher.BUILD_5848_BUNDLE_MARKERS)
  ```

  Update the missing-layout and ambiguous-layout fixtures to use
  `BUILD_5848_BUNDLE_MARKERS`. Add one mixed-variant case that combines the
  complete build-5848 and Windows-4979 marker sets in one
  `app-initial-mixed.js` fixture and asserts `current_patch_bundle(...)`
  raises `PatchError`, proving a bundle cannot be assigned two variants.

- [ ] **Step 2: Run the focused tests and confirm they fail for the removed identity.**

  Run:

  ```bash
  python3 -m unittest -v \
    tests.test_sync_codex_models.CurrentBundleTests.test_current_patch_bundle_finds_build_5848_app_initial \
    tests.test_sync_codex_models.CurrentBundleTests.test_build_5848_markers_include_verified_minified_symbols
  ```

  Expected: errors or failures because `BUILD_5848_BUNDLE_MARKERS` does not
  exist and the present macOS variant still names build 5828.

- [ ] **Step 3: Implement the exact build-5848 marker set and variant.**

  Replace the macOS marker constant with:

  ```python
  BUILD_5848_BUNDLE_MARKERS = (
      "async prewarmThreadStart(",
      "async sendConfigReadRequest(",
      "composer.intelligenceDropdown.tooltip",
      "data-model-picker-model-row",
      "vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto",
      "function o9t(e)",
      "function CMs(e)",
      "async function tp(...e)",
  )
  ```

  Replace the first `BUNDLE_PATCH_VARIANTS` entry with:

  ```python
  BundlePatchVariant(
      "ChatGPT 26.721.41059 build 5848 application",
      BUILD_5848_BUNDLE_MARKERS,
      CENTRAL_DIFF,
      PICKER_DIFF,
  ),
  ```

  Do not alter `WINDOWS_STORE_3996_*`, `WINDOWS_STORE_4979_*`, or their
  `BundlePatchVariant` entries.

- [ ] **Step 4: Verify the discovery suite passes.**

  Run:

  ```bash
  python3 -m unittest -v tests.test_sync_codex_models.CurrentBundleTests
  ```

  Expected: every macOS build-5848, missing-marker, ambiguous, prefixed-name,
  and Windows variant discovery test passes.

- [ ] **Step 5: Commit the independently verified identity change.**

  ```bash
  git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
  git commit -m "fix: target ChatGPT build 5848 bundle"
  ```

### Task 2: Rebase routing and picker hunks to the build-5848 source

**Files:**
- Modify: `tests/test_sync_codex_models.py:PatcherTemplateTests`
- Modify: `patch_chatgpt_providers.py:CENTRAL_DIFF` and `PICKER_DIFF`

**Interfaces:**
- Consumes: Prettier-formatted `app-initial-BHB6SClA.js`.
- Produces: `CENTRAL_DIFF` and `PICKER_DIFF` that each match their build-5848 source contexts exactly once and inject `__codexDesktopModelProvidersPatchV2` plus `CodexCustomProviderPickerSection`.

- [ ] **Step 1: Write failing static contracts for the build-5848 symbols.**

  Replace the build-5828 symbol assertions with:

  ```python
  def test_embedded_diffs_target_build_5848_bundle_symbols(self):
      self.assertIn("function o9t(e)", patcher.CENTRAL_DIFF)
      self.assertIn("let t = abe(e);", patcher.CENTRAL_DIFF)
      self.assertIn("var s9t,", patcher.CENTRAL_DIFF)
      self.assertIn("function CMs(e)", patcher.PICKER_DIFF)
      self.assertIn("children: ye,", patcher.PICKER_DIFF)
      for diff in (patcher.CENTRAL_DIFF, patcher.PICKER_DIFF):
          self.assertIn("tp(`codex-home`", diff)
          self.assertIn("tp(`read-file`", diff)
          self.assertNotIn("rp(`codex-home`", diff)
          self.assertNotIn("rp(`read-file`", diff)
      self.assertIn("wQ.jsx", patcher.PICKER_DIFF)
      self.assertIn("yz.Item", patcher.PICKER_DIFF)
      self.assertIn("Ym : void 0", patcher.PICKER_DIFF)
      self.assertIn("(CodexProviderPatchReact = r(o(), 1))", patcher.PICKER_DIFF)
  ```

  Add a small hunk fixture for the menu wrapper that asserts the diff replaces
  `children: ye,` with a `wQ.Fragment` containing
  `CodexCustomProviderPickerSection` before `ye`. Extend the existing import
  hunk fixture to use the real build-5848 initializer shape:

  ```python
  source = """}
  var TMs,
    wQ,
    EMs = e(() => {
      ((TMs = c()),
        pd(),
        ad(),
        gls(),
        Tss(),
        (wQ = J()));
    }),
  """
  ```

- [ ] **Step 2: Run the diff contracts and confirm they fail.**

  Run:

  ```bash
  python3 -m unittest -v \
    tests.test_sync_codex_models.PatcherTemplateTests.test_embedded_diffs_target_build_5848_bundle_symbols \
    tests.test_sync_codex_models.PatcherTemplateTests.test_picker_import_hunk_tolerates_added_upstream_initializers
  ```

  Expected: the present build-5828 contexts (`p9t`, `fbe`, `m9t`, and
  `rp(...)`) do not satisfy the build-5848 assertions.

- [ ] **Step 3: Rebase `CENTRAL_DIFF` onto the verified App Server client.**

  Change only the build-specific context and host-bridge function in the
  existing routing patch:

  ```text
  function p9t(e)       -> function o9t(e)
  let t = fbe(e);       -> let t = abe(e);
  var m9t,              -> var s9t,
  rp(`codex-home`       -> tp(`codex-home`
  rp(`read-file`        -> tp(`read-file`
  ```

  Preserve the existing injected `codexPatchAppServerParams(...)` function and
  its exact behavior: add `modelProviders: []` only for `thread/list`, add the
  selected provider only for `thread/start` and `thread/fork`, and leave every
  other request unchanged. Retain both exact-once hooks in `sendRequest(...)`
  and `prewarmThreadStart(...)`.

- [ ] **Step 4: Rebase `PICKER_DIFF` onto the build-5848 `CMs` menu wrapper.**

  Keep the provider-config loader and selector body, but use the current
  build's symbols and insertion points:

  ```text
  host IPC helper:       rp(...) -> tp(...)
  picker function:       Qjs(e) -> CMs(e)
  JSX runtime:           TQ      -> wQ
  menu namespace:        KR      -> yz
  selected icon:         Bm      -> Ym
  injected menu wrapper: children: ye,
                         -> children: <Fragment>[ProviderSection, ye]</Fragment>
  module initializer:    var TMs, wQ, EMs = e(() => ...)
                         -> declare and assign CodexProviderPatchReact with r(o(), 1)
  ```

  The menu-wrapper hunk must produce this JavaScript structure, preserving the
  existing `ye` menu body after the new section:

  ```javascript
  children: (0, wQ.jsxs)(wQ.Fragment, {
    children: [
      (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
      ye,
    ],
  }),
  ```

  Do not alter `CMs` props, model-selection callbacks, or `ye` construction.

- [ ] **Step 5: Verify source contracts and no-filter behavior.**

  Run:

  ```bash
  python3 -m unittest -v \
    tests.test_sync_codex_models.PatcherTemplateTests \
    tests.test_provider_model_filter_revert.ProviderModelFilterRevertTests.test_provider_selection_routes_requests_without_filtering_models
  ```

  Expected: the injected code uses `tp`, `wQ`, `yz`, and `Ym`; it includes the
  provider selector and contains none of the model-filter markers.

- [ ] **Step 6: Commit the rebased patch templates.**

  ```bash
  git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
  git commit -m "fix: patch ChatGPT build 5848 symbols"
  ```

### Task 3: Publish the build-5848 compatibility boundary

**Files:**
- Modify: `tests/test_provider_model_filter_revert.py`
- Modify: `tests/test_sync_codex_models.py:PatcherTemplateTests.test_patcher_help_describes_explicit_provider_selection`
- Modify: `patch_chatgpt_providers.py:parse_args`
- Modify: `README.md:Requirements` and `README.md:Updates and recovery`

**Interfaces:**
- Consumes: repository-local support copy.
- Produces: help and documentation that advertise only macOS `26.721.41059`, build `5848`.

- [ ] **Step 1: Write failing documentation and help contracts.**

  Replace the README test with:

  ```python
  def test_readme_targets_only_chatgpt_build_5848(self):
      readme = Path(patcher.__file__).with_name("README.md").read_text(
          encoding="utf-8"
      )
      self.assertIn("26.721.41059", readme)
      self.assertIn("build `5848`", readme)
      self.assertNotIn("26.721.31836", readme)
      self.assertNotIn("build `5828`", readme)
  ```

  Change the CLI-help test to require `26.721.41059` and `build 5848`, and to
  reject `26.721.31836` and `build 5828`.

- [ ] **Step 2: Run the copy contracts and confirm they fail.**

  Run:

  ```bash
  python3 -m unittest -v \
    tests.test_provider_model_filter_revert.ProviderModelFilterRevertTests.test_readme_targets_only_chatgpt_build_5848 \
    tests.test_sync_codex_models.PatcherTemplateTests.test_patcher_help_describes_explicit_provider_selection
  ```

  Expected: failures because the current requirements, recovery text, and help
  still identify build 5828.

- [ ] **Step 3: Update the public compatibility copy.**

  Change the macOS parser description to:

  ```python
  "Supports ChatGPT 26.721.41059 build 5848."
  ```

  In the README, replace both macOS build references with:

  ```markdown
  Official ChatGPT `26.721.41059`, build `5848`, installed at
  `/Applications/ChatGPT.app`
  ```

  Keep the warning that newer builds are unsupported until a compatible patch
  revision exists. Do not change any Windows requirements or release notes.

- [ ] **Step 4: Verify documentation and complete focused suites.**

  Run:

  ```bash
  python3 -m unittest -v \
    tests.test_provider_model_filter_revert \
    tests.test_sync_codex_models.PatcherTemplateTests \
    tests.test_sync_codex_models.CurrentBundleTests
  git diff --check
  ```

  Expected: all focused tests pass and `git diff --check` has no output.

- [ ] **Step 5: Commit the support-boundary documentation.**

  ```bash
  git add README.md patch_chatgpt_providers.py \
    tests/test_provider_model_filter_revert.py tests/test_sync_codex_models.py
  git commit -m "docs: target ChatGPT build 5848"
  ```

### Task 4: Verify a temporary patched build-5848 ASAR

**Files:**
- Modify: none
- Verify: `/Applications/ChatGPT.app`, `/Applications/ChatGPT-original.backup`, and temporary artifacts only

**Interfaces:**
- Consumes: `build_patched_artifacts(original: Path, work: Path) -> tuple[Path, Path]`.
- Produces: a temporary patched `app.asar` and `Info.plist` whose marker and integrity hash pass validation without writing into either application bundle.

- [ ] **Step 1: Run the complete Python test suite.**

  ```bash
  python3 -m unittest discover -v
  ```

  Expected: every repository test passes, including macOS routing, bundle
  discovery, Windows Store, setup, and provider-model regression suites.

- [ ] **Step 2: Build and validate the artifact in a temporary directory.**

  Run this read-only-to-`/Applications` verification after confirming both
  installed bundles have build `5848`:

  ```bash
  python3 - <<'PY'
  import hashlib
  import plistlib
  import tempfile
  from pathlib import Path
  import patch_chatgpt_providers as patcher

  app = Path("/Applications/ChatGPT.app")
  original = Path("/Applications/ChatGPT-original.backup")
  app_asar = app / "Contents" / "Resources" / "app.asar"
  original_asar = original / "Contents" / "Resources" / "app.asar"
  digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
  before = (digest(app_asar), digest(original_asar))
  for bundle in (app, original):
      with (bundle / "Contents" / "Info.plist").open("rb") as handle:
          info = plistlib.load(handle)
      assert info["CFBundleShortVersionString"] == "26.721.41059"
      assert info["CFBundleVersion"] == "5848"
  with tempfile.TemporaryDirectory(prefix="chatgpt-build-5848-verify-") as directory:
      patched_asar, patched_plist = patcher.build_patched_artifacts(
          original, Path(directory)
      )
      assert patcher.contains_marker(patched_asar)
      with patched_plist.open("rb") as handle:
          patched_info = plistlib.load(handle)
      assert patcher.asar_header_hash(patched_asar) == patcher.asar_integrity_hash(patched_info)
  assert before == (digest(app_asar), digest(original_asar))
  print("build 5848 artifact verification passed")
  PY
  ```

  Expected: extraction, formatting, both exact patch applications, JavaScript
  syntax validation, ASAR packing, marker validation, integrity validation,
  and `build 5848 artifact verification passed`. No file below `/Applications`
  changes.

- [ ] **Step 3: Check final repository state and commit verification-only amendments if needed.**

  Run:

  ```bash
  git status --short
  git diff --check
  python3 patch_chatgpt_providers.py --help >/dev/null
  ```

  Expected: a clean worktree, no whitespace errors, and exit status `0`. If
  verification exposed a product defect, add a new failing focused test first,
  correct only that defect, rerun this task from Step 1, and commit with a
  `fix:` message that names the corrected behavior.
