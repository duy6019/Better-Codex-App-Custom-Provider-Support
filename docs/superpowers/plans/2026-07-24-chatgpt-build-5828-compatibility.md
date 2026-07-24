# ChatGPT Build 5828 Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retarget the provider selector and explicit routing patch to ChatGPT `26.721.31836`, build `5828`, without restoring provider-based model filtering.

**Architecture:** Keep the existing exact-bundle and exact-hunk patch architecture, but replace build-5813 identity markers and minified symbols with their verified build-5828 equivalents. Preserve routing semantics, validate the new IPC function statically, and build a temporary patched ASAR from the clean sibling original without installing it.

**Tech Stack:** Python 3.9+, `unittest`, embedded JavaScript unified diffs, Electron ASAR 3.2.10, Prettier 3.6.2, Node.js `node --check`.

## Global Constraints

- Support only ChatGPT `26.721.31836`, build `5828`.
- Do not support ChatGPT `26.721.30844`, build `5813`.
- Keep exact `app-initial-*.js` filename discovery and unique-candidate checks.
- Keep the provider menu for new tasks.
- Keep the selected provider on `thread/start` and `thread/fork` requests.
- Keep `thread/list` visible across all providers.
- Keep `model_providers` as generated-config compatibility data only.
- Do not filter catalog models or replace the selected model.
- Do not modify `sync_codex_models.py` or the provider-routing JSON schema.
- Do not install into `/Applications/ChatGPT.app` during automated verification.
- Create an isolated `codex/chatgpt-build-5828` worktree through `superpowers:using-git-worktrees` before executing this plan.

---

## File Map

- `patch_chatgpt_providers.py`: build markers, bundle diagnostics, and both build-5828 embedded JavaScript diffs.
- `tests/test_sync_codex_models.py`: bundle-discovery, source-symbol, IPC, provider-menu, and hunk contracts.
- `tests/test_provider_model_filter_revert.py`: no-filter regression and latest-only documentation contract.
- `README.md`: supported official app version and recovery guidance.
- `docs/superpowers/specs/2026-07-24-chatgpt-build-5828-compatibility-design.md`: approved design; retain unchanged.

### Task 1: Target the unique build-5828 application bundle

**Files:**

- Modify: `tests/test_sync_codex_models.py` in `CurrentBundleTests`.
- Modify: `patch_chatgpt_providers.py` at the marker constant and `current_patch_bundle(...)`.

**Interfaces:**

- Consumes: `unique_candidate(assets, filename_glob, content_needles, role)`.
- Produces: `BUILD_5828_BUNDLE_MARKERS: tuple[str, ...]` and `current_patch_bundle(assets: Path) -> Path` restricted to build 5828.

- [ ] **Step 1: Write failing build-5828 bundle-discovery tests.**

Rename the build-specific test methods from `build_5813` to `build_5828`,
replace `patcher.BUILD_5813_BUNDLE_MARKERS` with
`patcher.BUILD_5828_BUNDLE_MARKERS`, change the expected filename to
`app-initial-C-fROkKo.js`, and add:

```python
def test_build_5828_markers_include_verified_minified_symbols(self):
    self.assertIn("function p9t(e)", patcher.BUILD_5828_BUNDLE_MARKERS)
    self.assertIn("function Qjs(e)", patcher.BUILD_5828_BUNDLE_MARKERS)
    self.assertIn("async function rp(...e)", patcher.BUILD_5828_BUNDLE_MARKERS)
```

Make the missing-layout test require the new diagnostic:

```python
with self.assertRaisesRegex(
    patcher.PatchError,
    "ChatGPT 26.721.31836 build 5828 application.*found 0 out of 1 filename matches",
):
    patcher.current_patch_bundle(assets)
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

```bash
python3 -m unittest -v tests.test_sync_codex_models.CurrentBundleTests
```

Expected: errors report that `BUILD_5828_BUNDLE_MARKERS` is absent and the
diagnostic still names build 5813.

- [ ] **Step 3: Implement the build-5828 identity.**

Replace the old marker constant with:

```python
BUILD_5828_BUNDLE_MARKERS = (
    "async prewarmThreadStart(",
    "async sendConfigReadRequest(",
    "composer.intelligenceDropdown.tooltip",
    "data-model-picker-model-row",
    "vertical-scroll-fade-mask flex max-h-[250px] flex-col overflow-y-auto",
    "function p9t(e)",
    "function Qjs(e)",
    "async function rp(...e)",
)
```

Replace `current_patch_bundle(...)` with:

```python
def current_patch_bundle(assets: Path) -> Path:
    return unique_candidate(
        assets,
        "app-initial-*.js",
        BUILD_5828_BUNDLE_MARKERS,
        "ChatGPT 26.721.31836 build 5828 application",
    )
```

- [ ] **Step 4: Verify and commit the bundle identity.**

```bash
python3 -m unittest -v tests.test_sync_codex_models.CurrentBundleTests
git diff --check
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "fix: target ChatGPT build 5828 bundle"
```

Expected: every `CurrentBundleTests` test passes, diff check is silent, and the
commit succeeds.

### Task 2: Retarget routing and picker hunks to build-5828 symbols

**Files:**

- Modify: `tests/test_sync_codex_models.py` in `PatcherTemplateTests`.
- Modify: `patch_chatgpt_providers.py` in `CENTRAL_DIFF` and `PICKER_DIFF`.

**Interfaces:**

- Consumes: formatted build-5828 `app-initial-C-fROkKo.js`.
- Produces: six exact hunks whose injected code uses `rp(...)`, `TQ`, `KR`, and `Bm`.

- [ ] **Step 1: Write the failing build-5828 source contract.**

Replace `test_embedded_diffs_target_build_5813_bundle_symbols` with:

```python
def test_embedded_diffs_target_build_5828_bundle_symbols(self):
    self.assertIn("function p9t(e)", patcher.CENTRAL_DIFF)
    self.assertIn("let t = fbe(e);", patcher.CENTRAL_DIFF)
    self.assertIn("var m9t,", patcher.CENTRAL_DIFF)
    self.assertIn("function Qjs(e)", patcher.PICKER_DIFF)
    for diff in (patcher.CENTRAL_DIFF, patcher.PICKER_DIFF):
        self.assertIn("rp(`codex-home`", diff)
        self.assertIn("rp(`read-file`", diff)
        self.assertNotIn("tp(`codex-home`", diff)
        self.assertNotIn("tp(`read-file`", diff)
    self.assertIn("TQ.jsx", patcher.PICKER_DIFF)
    self.assertIn("KR.Item", patcher.PICKER_DIFF)
    self.assertIn("Bm : void 0", patcher.PICKER_DIFF)
    self.assertIn("(CodexProviderPatchReact = r(o(), 1))", patcher.PICKER_DIFF)
    for old_symbol in (
        "function o9t(e)",
        "let t = obe(e);",
        "var s9t,",
        "wQ.jsx",
        "yz.Item",
        "Ym : void 0",
        "fd()",
    ):
        with self.subTest(old_symbol=old_symbol):
            self.assertNotIn(old_symbol, patcher.CENTRAL_DIFF + patcher.PICKER_DIFF)
```

Update the provider-menu namespace loop to:

```python
for component in ("Item", "Title", "Separator"):
    self.assertIn(f"KR.{component}", provider_section)
    self.assertNotIn(f"yz.{component}", provider_section)
```

Replace the import-hunk fixture with:

```python
source = """}
var eMs,
  TQ,
  tMs = e(() => {
    ((eMs = c()),
      sd(),
      extraInitializer(),
      $u(),
      qcs(),
      nss(),
      rss(),
      OAs(),
      Vm(),
      qX(),
      qE(),
      qR(),
      Tos(),
      hcs(),
      ncs(),
      Sos(),
      Pos(),
      kos(),
      fcs(),
      (TQ = J()));
  }),
"""
```

- [ ] **Step 2: Run the three contracts and confirm they fail.**

```bash
python3 -m unittest -v \
  tests.test_sync_codex_models.PatcherTemplateTests.test_embedded_diffs_target_build_5828_bundle_symbols \
  tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_renders_subcomponents_from_menu_namespace \
  tests.test_sync_codex_models.PatcherTemplateTests.test_picker_import_hunk_tolerates_added_upstream_initializers
```

Expected: build-5813 symbols fail the static assertions and the build-5828
fixtures do not match the old picker hunks.

- [ ] **Step 3: Retarget `CENTRAL_DIFF`.**

Apply only these source mappings:

```text
function o9t(e)  -> function p9t(e)
let t = obe(e);  -> let t = fbe(e);
var s9t,         -> var m9t,
tp(`codex-home`  -> rp(`codex-home`
tp(`read-file`   -> rp(`read-file`
```

Keep `thread/list`, `thread/start`, `thread/fork`, `sendRequest`, and
`prewarmThreadStart` behavior unchanged.

- [ ] **Step 4: Retarget `PICKER_DIFF`.**

Apply only these source mappings:

```text
qo()             -> Ho()
ad()             -> ed()
KD()             -> DD()
Aa(Q             -> Oa(Q
t(PD, e)         -> t(hD, e)
t(LD, e)         -> t(vD, e)
tp(`codex-home`  -> rp(`codex-home`
tp(`read-file`   -> rp(`read-file`
wQ               -> TQ
yz               -> KR
Ym               -> Bm
fd()             -> sd()
```

Retain `CodexProviderPatchReact = r(o(), 1)` and add no filtering, listener,
model-mapping, or replacement code.

- [ ] **Step 5: Verify and commit the embedded diffs.**

```bash
python3 -m unittest -v \
  tests.test_sync_codex_models.PatcherTemplateTests \
  tests.test_provider_model_filter_revert.ProviderModelFilterRevertTests
git diff --check
git add patch_chatgpt_providers.py tests/test_sync_codex_models.py
git commit -m "fix: patch ChatGPT build 5828 symbols"
```

Expected: all focused tests pass, diff check is silent, and the commit succeeds.

### Task 3: Advertise only the supported build

**Files:**

- Modify: `tests/test_provider_model_filter_revert.py`.
- Modify: `tests/test_sync_codex_models.py` in the CLI help contract.
- Modify: `patch_chatgpt_providers.py` in `parse_args()`.
- Modify: `README.md` in Requirements and Updates and recovery.

**Interfaces:**

- Consumes: repository-local `README.md`.
- Produces: CLI help and user documentation naming only ChatGPT
  `26.721.31836`, build `5828`.

- [ ] **Step 1: Add a failing latest-only documentation test.**

```python
def test_readme_targets_only_chatgpt_build_5828(self):
    readme = Path(patcher.__file__).with_name("README.md").read_text(
        encoding="utf-8"
    )
    self.assertIn("26.721.31836", readme)
    self.assertIn("build `5828`", readme)
    self.assertNotIn("26.721.30844", readme)
    self.assertNotIn("build `5813`", readme)
```

Extend `test_patcher_help_describes_explicit_provider_selection` after calling
`parse_args()`:

```python
help_text = output.getvalue()
self.assertIn("explicit provider selector", help_text)
self.assertIn("26.721.31836", help_text)
self.assertIn("build 5828", help_text)
self.assertNotIn("26.721.30844", help_text)
self.assertNotIn("build 5813", help_text)
self.assertNotIn("per-model provider routing", help_text)
```

- [ ] **Step 2: Run the test and confirm it fails.**

```bash
python3 -m unittest -v \
  tests.test_provider_model_filter_revert.ProviderModelFilterRevertTests.test_readme_targets_only_chatgpt_build_5828
python3 -m unittest -v \
  tests.test_sync_codex_models.PatcherTemplateTests.test_patcher_help_describes_explicit_provider_selection
```

Expected: both tests fail because README and CLI help do not yet advertise the
new supported version and build.

- [ ] **Step 3: Update both README support statements.**

Use this Requirements bullet:

```markdown
- Official ChatGPT `26.721.31836`, build `5828`, installed at `/Applications/ChatGPT.app`
```

Use this Updates and recovery paragraph:

```markdown
ChatGPT updates replace the patch. This revision supports the official
ChatGPT `26.721.31836`, build `5828`. A newer app build may change the generated
JavaScript again; wait for a compatible patch revision before rerunning the
installer.
```

Replace the `FancyArgumentParser` description in `parse_args()` with:

```python
description=(
    "Add an explicit provider selector to the macOS ChatGPT/Codex desktop app. "
    "Supports ChatGPT 26.721.31836 build 5828."
)
```

- [ ] **Step 4: Verify and commit documentation.**

```bash
python3 -m unittest -v tests/test_provider_model_filter_revert.py
python3 -m unittest -v
git diff --check
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
git add \
  README.md \
  patch_chatgpt_providers.py \
  tests/test_provider_model_filter_revert.py \
  tests/test_sync_codex_models.py
git commit -m "docs: support ChatGPT build 5828"
```

Expected: all tests and CLI checks pass, diff check is silent, and the commit
succeeds.

### Task 4: Verify the real build-5828 artifact without installation

**Files:**

- Verify only: `/Applications/ChatGPT.app`.
- Verify only: `/Applications/ChatGPT-original.backup`.
- Verify only: repository working tree.

**Interfaces:**

- Consumes: `build_patched_artifacts(original: Path, work: Path) -> tuple[Path, Path]`.
- Produces: a temporary patched ASAR and plist with verified syntax, markers, routing, and ASAR integrity.

- [ ] **Step 1: Run the production temporary-build verification.**

```bash
python3 - <<'PY'
import hashlib
import json
import plistlib
import tempfile
from pathlib import Path

import patch_chatgpt_providers as patcher


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


original = Path("/Applications/ChatGPT-original.backup")
protected = (
    Path("/Applications/ChatGPT.app/Contents/Resources/app.asar"),
    Path("/Applications/ChatGPT.app/Contents/Info.plist"),
    original / "Contents/Resources/app.asar",
    original / "Contents/Info.plist",
)
before = {str(path): sha256(path) for path in protected}
info, _ = patcher.load_plist(original / "Contents/Info.plist")
assert info["CFBundleShortVersionString"] == "26.721.31836"
assert str(info["CFBundleVersion"]) == "5828"

with tempfile.TemporaryDirectory(prefix="chatgpt-build-5828-") as temporary:
    work = Path(temporary)
    patched_asar, patched_plist = patcher.build_patched_artifacts(original, work)
    bundle = patcher.current_patch_bundle(work / "app/webview/assets")
    source = bundle.read_text(encoding="utf-8")
    central = source.split("function codexProviderRoutingFallback()", 1)[1].split(
        "var m9t,", 1
    )[0]
    picker = source.split("function CodexCustomProviderPickerSection()", 1)[1].split(
        "function Qjs(e)", 1
    )[0]
    assert "rp(`codex-home`" in central
    assert "rp(`read-file`" in central
    assert "tp(`codex-home`" not in central
    assert "TQ.jsx" in picker
    assert "KR.Item" in picker
    assert "RightIcon: a === e.id ? Bm : void 0" in picker
    assert "codexUseProviderFilteredModels" not in source
    assert "codexFindProviderModelReplacement" not in source
    assert "modelProvider: await codexSelectedProvider()" in source
    assert "if (e === `thread/list`)" in source
    assert "modelProviders: []" in source
    with patched_plist.open("rb") as handle:
        patched_info = plistlib.load(handle)
    assert patcher.contains_marker(patched_asar)
    assert patcher.asar_header_hash(patched_asar) == patcher.asar_integrity_hash(
        patched_info
    )

after = {str(path): sha256(path) for path in protected}
assert after == before
print(json.dumps({"protected_hashes": after, "status": "ok"}, indent=2))
PY
```

Expected: both Prettier passes, all six hunks, `node --check`, ASAR packing,
marker checks, and integrity verification succeed. JSON ends with
`"status": "ok"`, and all protected hashes remain stable.

- [ ] **Step 2: Run final verification against the committed tree.**

```bash
python3 -m unittest -v
git diff --check
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
git status --short --branch
git log --oneline -5
```

Expected: every command exits 0, the branch is clean, and the three
implementation commits are visible above the approved design and plan commits.
