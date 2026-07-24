# ChatGPT Build 5813 Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `patch_chatgpt_providers.py` safely patch the official ChatGPT macOS `26.721.30844` build `5813` consolidated webview bundle.

**Architecture:** Replace the old split-bundle discovery with one exact current-layout bundle locator, then format and patch that bundle once through a focused `patch_current_bundle` function. Replace both embedded unified diffs with build-5813 contexts while preserving provider selection and routing behavior, and verify the complete artifact build against the clean sibling ASAR without modifying either application bundle.

**Tech Stack:** Python 3.9+, `unittest`, `unittest.mock`, Electron ASAR CLI `@electron/asar@3.2.10`, Prettier `3.6.2`, Node.js syntax checking, macOS Electron app bundles.

## Global Constraints

- Support only ChatGPT version `26.721.30844`, bundle build `5813`, on macOS.
- Remove support for build `5718` and its split-chunk layout.
- Preserve the existing provider picker, `thread/list`, `thread/start`, `thread/fork`, and prewarmed `thread/start` behavior.
- Do not implement the separate provider-model filtering plan.
- Continue to fail closed before live app replacement when discovery or any exact patch hunk differs.
- Do not modify `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during implementation or verification.
- Preserve unrelated untracked files already present in the worktree.

---

### Task 1: Discover and patch the consolidated build-5813 bundle once

**Files:**
- Modify: `tests/test_sync_codex_models.py`
- Modify: `patch_chatgpt_providers.py:1059-1082`
- Modify: `patch_chatgpt_providers.py:1348-1421`

**Interfaces:**
- Consumes: `unique_candidate(assets: Path, filename_fragment: str, content_needles: tuple[str, ...], role: str) -> Path`, `run(command: list[str], *, label: str)`, `apply_unified_diff(path: Path, unified_diff: str) -> None`.
- Produces: `BUILD_5813_BUNDLE_MARKERS: tuple[str, ...]`, `current_patch_bundle(assets: Path) -> Path`, and `patch_current_bundle(bundle: Path) -> None`.

- [ ] **Step 1: Write failing bundle-discovery tests**

Add this class after `PatcherTemplateTests` in `tests/test_sync_codex_models.py`:

```python
class CurrentBundleTests(unittest.TestCase):
    def write_bundle(self, assets: Path, name: str, markers=()) -> Path:
        bundle = assets / name
        bundle.write_text("\n".join(markers), encoding="utf-8")
        return bundle

    def test_current_patch_bundle_finds_build_5813_app_initial(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            expected = self.write_bundle(
                assets,
                "app-initial-BTphDPeq.js",
                patcher.BUILD_5813_BUNDLE_MARKERS,
            )
            self.write_bundle(
                assets,
                "en-US-localization.js",
                ("composer.intelligenceDropdown.tooltip",),
            )

            self.assertEqual(patcher.current_patch_bundle(assets), expected)

    def test_current_patch_bundle_rejects_missing_build_5813_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            self.write_bundle(
                assets,
                "app-initial-old.js",
                patcher.BUILD_5813_BUNDLE_MARKERS[:-1],
            )

            with self.assertRaisesRegex(
                patcher.PatchError,
                "found 0 out of 1 filename matches",
            ):
                patcher.current_patch_bundle(assets)

    def test_current_patch_bundle_rejects_ambiguous_build_5813_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary)
            for suffix in ("one", "two"):
                self.write_bundle(
                    assets,
                    f"app-initial-{suffix}.js",
                    patcher.BUILD_5813_BUNDLE_MARKERS,
                )

            with self.assertRaisesRegex(
                patcher.PatchError,
                "found 2 out of 2 filename matches",
            ):
                patcher.current_patch_bundle(assets)
```

- [ ] **Step 2: Run the discovery tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.CurrentBundleTests.test_current_patch_bundle_finds_build_5813_app_initial \
  tests.test_sync_codex_models.CurrentBundleTests.test_current_patch_bundle_rejects_missing_build_5813_layout \
  tests.test_sync_codex_models.CurrentBundleTests.test_current_patch_bundle_rejects_ambiguous_build_5813_layout -v
```

Expected: all three tests error because `BUILD_5813_BUNDLE_MARKERS` or `current_patch_bundle` does not exist.

- [ ] **Step 3: Implement the exact current-bundle locator**

Add beside the package constants in `patch_chatgpt_providers.py`:

```python
BUILD_5813_BUNDLE_MARKERS = (
    "async prewarmThreadStart(",
    "async sendConfigReadRequest(",
    "composer.intelligenceDropdown.tooltip",
    "data-model-picker-model-row",
    "vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto",
)
```

Add immediately after `unique_candidate`:

```python
def current_patch_bundle(assets: Path) -> Path:
    return unique_candidate(
        assets,
        "app-initial-",
        BUILD_5813_BUNDLE_MARKERS,
        "ChatGPT 26.721.30844 build 5813 application",
    )
```

- [ ] **Step 4: Run the discovery tests and verify GREEN**

Run the Step 2 command again.

Expected: three tests pass.

- [ ] **Step 5: Write a failing same-file patch-pipeline test**

Add to `CurrentBundleTests`:

```python
    def test_patch_current_bundle_applies_both_diffs_to_one_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "app-initial-current.js"
            bundle.write_text("original\n", encoding="utf-8")

            def apply_marker(path, unified_diff):
                marker = (
                    patcher.PATCH_MARKER.decode()
                    if unified_diff is patcher.CENTRAL_DIFF
                    else "CodexCustomProviderPickerSection"
                )
                path.write_text(
                    path.read_text(encoding="utf-8") + marker + "\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(patcher, "run") as run,
                mock.patch.object(
                    patcher,
                    "apply_unified_diff",
                    side_effect=apply_marker,
                ) as apply,
            ):
                patcher.patch_current_bundle(bundle)

            self.assertEqual(
                apply.call_args_list,
                [
                    mock.call(bundle, patcher.CENTRAL_DIFF),
                    mock.call(bundle, patcher.PICKER_DIFF),
                ],
            )
            self.assertEqual(
                run.call_args_list,
                [
                    mock.call(
                        [
                            "npx",
                            "--yes",
                            patcher.PRETTIER_PACKAGE,
                            "--write",
                            str(bundle),
                        ],
                        label="Preparing the JavaScript bundle",
                    ),
                    mock.call(
                        [
                            "npx",
                            "--yes",
                            patcher.PRETTIER_PACKAGE,
                            "--write",
                            str(bundle),
                        ],
                        label="Formatting the patched JavaScript",
                    ),
                    mock.call(
                        ["node", "--check", str(bundle)],
                        label="Validating the patched JavaScript",
                    ),
                ],
            )
```

- [ ] **Step 6: Run the same-file test and verify RED**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.CurrentBundleTests.test_patch_current_bundle_applies_both_diffs_to_one_file -v
```

Expected: ERROR because `patch_current_bundle` does not exist.

- [ ] **Step 7: Implement the single-bundle patch pipeline**

Add after `apply_unified_diff`:

```python
def patch_current_bundle(bundle: Path) -> None:
    run(
        ["npx", "--yes", PRETTIER_PACKAGE, "--write", str(bundle)],
        label="Preparing the JavaScript bundle",
    )
    apply_unified_diff(bundle, CENTRAL_DIFF)
    apply_unified_diff(bundle, PICKER_DIFF)

    source = bundle.read_text(encoding="utf-8")
    if PATCH_MARKER.decode() not in source:
        raise PatchError("Routing marker missing after patch")
    if "CodexCustomProviderPickerSection" not in source:
        raise PatchError("Provider picker missing after patch")

    run(
        ["npx", "--yes", PRETTIER_PACKAGE, "--write", str(bundle)],
        label="Formatting the patched JavaScript",
    )
    run(
        ["node", "--check", str(bundle)],
        label="Validating the patched JavaScript",
    )
```

In `build_patched_artifacts`, replace both old `unique_candidate` calls, both multi-file Prettier calls, both `apply_unified_diff` calls, and both inline marker checks with:

```python
    bundle = current_patch_bundle(assets)
    patch_current_bundle(bundle)
```

Leave ASAR packing, marker verification, integrity hashing, and plist generation unchanged.

- [ ] **Step 8: Run all current-bundle tests and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_sync_codex_models.CurrentBundleTests -v
```

Expected: four tests pass.

- [ ] **Step 9: Commit the bundle pipeline**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "refactor: target consolidated ChatGPT bundle"
```

---

### Task 2: Replace the embedded patches with build-5813 source contexts

**Files:**
- Modify: `tests/test_sync_codex_models.py:PatcherTemplateTests`
- Modify: `patch_chatgpt_providers.py:67-455`

**Interfaces:**
- Consumes: `CENTRAL_DIFF: str`, `PICKER_DIFF: str`, `parse_hunks(unified_diff: str) -> list[list[str]]`, and `apply_unified_diff(path: Path, unified_diff: str) -> None`.
- Produces: build-5813 `CENTRAL_DIFF` and `PICKER_DIFF` values that apply sequentially to the formatted consolidated bundle.

- [ ] **Step 1: Change the embedded-patch tests to require build-5813 symbols**

Add this test to `PatcherTemplateTests`:

```python
    def test_embedded_diffs_target_build_5813_bundle_symbols(self):
        self.assertIn("function Qjs(e)", patcher.PICKER_DIFF)
        self.assertIn("tp(`codex-home`", patcher.CENTRAL_DIFF)
        self.assertIn("tp(`codex-home`", patcher.PICKER_DIFF)
        self.assertIn("wQ.jsx", patcher.PICKER_DIFF)
        self.assertIn("yz.Item", patcher.PICKER_DIFF)
        self.assertIn("Ym : void 0", patcher.PICKER_DIFF)
        self.assertIn(
            "(CodexProviderPatchReact = r(o(), 1))",
            patcher.PICKER_DIFF,
        )
        self.assertNotIn("function MO(e)", patcher.PICKER_DIFF)
        self.assertNotIn("Xe(`codex-home`", patcher.CENTRAL_DIFF)
```

Update `test_provider_picker_renders_subcomponents_from_menu_namespace` so the provider-section boundary is `function Qjs(e)` and the expected namespace is `yz`:

```python
        provider_section = patched.split(
            "function CodexCustomProviderPickerSection()", 1
        )[1].split("function Qjs(e)", 1)[0]
        for component in ("Item", "Title", "Separator"):
            self.assertIn(f"yz.{component}", provider_section)
            self.assertNotIn(f"Ly.{component}", provider_section)
```

Update `test_picker_import_hunk_tolerates_added_upstream_initializers` to use the build-5813 initializer:

```python
        source = """}
var eMs,
  wQ,
  tMs = e(() => {
    ((eMs = c()),
      fd(),
      id(),
      qcs(),
      nss(),
      rss(),
      OAs(),
      Xm(),
      KX(),
      fD(),
      bz(),
      Tos(),
      hcs(),
      ncs(),
      Sos(),
      Pos(),
      kos(),
      fcs(),
      (wQ = J()));
  }),
"""
```

Change its final assertion to:

```python
        self.assertIn("(CodexProviderPatchReact = r(o(), 1))", patched)
```

- [ ] **Step 2: Run the build-symbol tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests.test_embedded_diffs_target_build_5813_bundle_symbols \
  tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_renders_subcomponents_from_menu_namespace \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_import_hunk_tolerates_added_upstream_initializers -v
```

Expected: failures showing old `MO`, `Xe`, `FO`, `Ly`, `ct`, and `t(m(), 1)` symbols.

- [ ] **Step 3: Rebase `CENTRAL_DIFF` onto the formatted build-5813 App Server client**

Keep every added provider-routing helper line behaviorally identical to the existing diff, but make these exact build changes:

- Change both host bridge calls from `Xe(...)` to `tp(...)`.
- Anchor the first hunk after the complete build-5813 `o9t` function and before `var s9t`:

```javascript
function o9t(e) {
  if (`data` in e) return e;
  let t = obe(e);
  return t == null ? e : { ...e, data: t };
}
var s9t,
```

- Replace the request hunk with the exact current method context and insert the routing call before its return:

```javascript
        async sendRequest(e, t, n) {
          if (this.dispatchMessage == null)
            throw Error(
              `AppServerRequestClient is missing a message dispatcher`,
            );
          t = await codexPatchAppServerParams(e, t);
          return e === `config/read`
            ? this.sendConfigReadRequest(t, n)
            : this.enqueueRequest(e, t, n);
        }
```

- Replace the prewarm hunk with the current `try` block and patch `e` before the four-argument enqueue call:

```javascript
          try {
            e = await codexPatchAppServerParams(`thread/start`, e);
            let a = await this.enqueueRequest(
              `thread/start`,
              e,
              { ...t, priority: n, trace: t?.trace ?? i?.trace ?? null },
              (e) => {
```

Do not change the inserted routing logic, fallback data, local-storage key, request method list, or patch marker.

- [ ] **Step 4: Rebase `PICKER_DIFF` onto the formatted build-5813 model picker**

Keep the provider picker behavior identical while applying this exact symbol map to every added line:

| Old build symbol | Build 5813 symbol | Meaning |
|---|---|---|
| `ye` | `tp` | host bridge |
| `FO` | `wQ` | JSX runtime |
| `Ly` | `yz` | menu component namespace |
| `ct` | `Ym` | selected-item check icon |
| `t(m(), 1)` | `r(o(), 1)` | React namespace import |
| `MO` | `Qjs` | model picker function |
| `PO` | `eMs` | React compiler cache runtime |
| `IO` | `tMs` | model picker module initializer |

Anchor the helper insertion immediately after the complete `Zjs` initializer and before `function Qjs(e)`:

```javascript
var Xjs,
  Zjs = e(() => {
    (qo(),
      ad(),
      KD(),
      (Xjs = Aa(Q, (e, { get: t }) =>
        Yjs({
          conversationId: e,
          resumeState: t(PD, e) ?? void 0,
          turnCount: t(LD, e),
        }),
      )));
  });
function Qjs(e) {
```

Insert the component before the native `m` title in the cached model-list fragment:

```javascript
        : ((g = (0, wQ.jsxs)(wQ.Fragment, {
            children: [
              (0, wQ.jsx)(CodexCustomProviderPickerSection, {}),
              m,
              (0, wQ.jsx)(`div`, {
```

Add the React namespace variable and initialization to the exact module block:

```javascript
var eMs,
  wQ,
  CodexProviderPatchReact,
  tMs = e(() => {
    ((eMs = c()),
      (CodexProviderPatchReact = r(o(), 1)),
      fd(),
```

Do not change provider labels, fallback configuration, normalization,
`codex.customProviderSelection.v1`, or error rendering.

- [ ] **Step 5: Run the targeted tests and verify GREEN**

Run the Step 2 command again.

Expected: three tests pass.

- [ ] **Step 6: Run the complete template and current-bundle suites**

Run:

```bash
python3 -m unittest \
  tests.test_sync_codex_models.PatcherTemplateTests \
  tests.test_sync_codex_models.CurrentBundleTests -v
```

Expected: all tests pass, including explicit provider routing and diff-shape checks.

- [ ] **Step 7: Commit the build-5813 patch data**

```bash
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "fix: support ChatGPT build 5813 patches"
```

---

### Task 3: Verify complete artifact generation against the clean official ASAR

**Files:**
- Read only: `/Applications/ChatGPT-original.backup/Contents/Resources/app.asar`
- Read only: `/Applications/ChatGPT-original.backup/Contents/Info.plist`
- Temporary output only: a `tempfile.TemporaryDirectory()` created by the verification command

**Interfaces:**
- Consumes: `build_patched_artifacts(original: Path, work: Path) -> tuple[Path, Path]`, `contains_marker(path: Path) -> bool`, `asar_header_hash(path: Path) -> str`, `load_plist(path: Path)`, and `asar_integrity_hash(plist: dict[str, Any]) -> str`.
- Produces: evidence that current discovery, both embedded diffs, formatting, Node syntax checking, ASAR packing, and plist integrity generation work together.

- [ ] **Step 1: Confirm the verification source is the expected clean build**

Run:

```bash
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/ChatGPT-original.backup/Contents/Info.plist
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' /Applications/ChatGPT-original.backup/Contents/Info.plist
```

Expected output:

```text
26.721.30844
5813
```

- [ ] **Step 2: Build and validate patched artifacts entirely in a temporary directory**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import tempfile
import patch_chatgpt_providers as patcher

original = Path("/Applications/ChatGPT-original.backup")
with tempfile.TemporaryDirectory(prefix="chatgpt-build-5813-verify-") as temporary:
    patched_asar, patched_plist = patcher.build_patched_artifacts(
        original,
        Path(temporary),
    )
    plist, _ = patcher.load_plist(patched_plist)
    assert patcher.contains_marker(patched_asar)
    assert patcher.asar_header_hash(patched_asar) == patcher.asar_integrity_hash(plist)
    print(patched_asar)
    print("build 5813 artifact verification passed")
PY
```

Expected: extraction, one-bundle formatting, two successful patches, Node syntax validation, ASAR packing, and `build 5813 artifact verification passed`. No command writes into either `/Applications` bundle.

- [ ] **Step 3: Run the full Python suite**

Run:

```bash
python3 -m unittest -v
```

Expected: all tests pass with no warnings or errors.

- [ ] **Step 4: Run repository hygiene and CLI smoke checks**

Run:

```bash
git diff --check
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
```

Expected: all commands exit `0` with no output from `git diff --check`.

---

### Task 4: Document the exact supported official build

**Files:**
- Modify: `README.md:20-27`
- Modify: `README.md:132-138`

**Interfaces:**
- Consumes: verified build identity and fail-closed behavior from Tasks 1-3.
- Produces: user-facing installation and update expectations for build 5813.

- [ ] **Step 1: Update the requirements and recovery wording**

Change the ChatGPT requirement to:

```markdown
- Official ChatGPT `26.721.30844`, build `5813`, installed at `/Applications/ChatGPT.app`
```

Replace the two update-compatibility paragraphs with:

```markdown
ChatGPT updates replace the patch. This revision supports the official
ChatGPT `26.721.30844`, build `5813`. A newer app build may change the generated
JavaScript again; wait for a compatible patch revision before rerunning the
installer.

The installer validates the expected bundle filename shape, source markers,
and exact patch contexts. If an app update changes them, it stops before
modifying the installed app.
```

- [ ] **Step 2: Verify the documented build and formatting**

Run:

```bash
rg -n '26\.721\.30844|5813|stops before' README.md
git diff --check
```

Expected: the exact version and build appear in Requirements and Updates, and `git diff --check` prints nothing.

- [ ] **Step 3: Run final verification**

Run:

```bash
python3 -m unittest -v
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
git status --short
```

Expected: all tests and smoke checks pass; status lists only the intended script, test, README, and plan changes plus the user's pre-existing unrelated untracked files.

- [ ] **Step 4: Commit the documentation**

```bash
git add README.md docs/superpowers/plans/2026-07-24-build-5813-compatibility.md
git commit -m "docs: document supported ChatGPT build"
```
