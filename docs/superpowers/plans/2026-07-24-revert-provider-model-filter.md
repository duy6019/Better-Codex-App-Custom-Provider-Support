# Revert Provider Model Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove provider-based model filtering and automatic model replacement while preserving the provider selector, explicit request routing, and ChatGPT build-5813 support.

**Architecture:** Add a regression contract that defines provider selection as request-routing state only, then non-destructively revert the six isolated provider-filter commits in reverse chronological order. Verify the restored embedded diffs against the clean build-5813 ASAR without installing them into the live application.

**Tech Stack:** Python 3.9+, `unittest`, embedded JavaScript unified diffs, Git revert, Electron ASAR, Prettier 3.6.2, Node.js `node --check`.

## Global Constraints

- Support only ChatGPT `26.721.30844`, build `5813`.
- Revert commits `5e1166b` through `cb6ce84` without rewriting Git history.
- Keep exact discovery of the consolidated `app-initial-*.js` bundle.
- Keep the provider menu for new tasks.
- Keep the selected provider on `thread/start` and `thread/fork` requests.
- Keep `thread/list` visible across all providers.
- Do not modify `sync_codex_models.py` or the provider-routing JSON schema.
- Model IDs must not choose a provider, filter the picker, or change the current model.
- Preserve invalid-config fallback and visible config-error handling.
- Do not modify `/Applications/ChatGPT.app` or `/Applications/ChatGPT-original.backup` during verification.
- Create an isolated `codex/revert-provider-model-filter` worktree through `superpowers:using-git-worktrees` before executing this plan.

---

## File Map

- `tests/test_provider_model_filter_revert.py`: new regression contract proving provider selection routes requests without filtering or replacing models.
- `patch_chatgpt_providers.py`: restored pre-filter picker patch and compatibility-only `model_providers` completion text.
- `tests/test_sync_codex_models.py`: removal of tests that require model filtering, listener publication, and automatic replacement.
- `README.md`: restored documentation that describes `model_providers` as generated-config compatibility data only.
- `docs/superpowers/specs/2026-07-24-provider-model-filter-build-5813-design.md`: removed superseded filter design.
- `docs/superpowers/plans/2026-07-24-provider-model-filter-build-5813.md`: removed superseded filter implementation plan.
- `docs/superpowers/specs/2026-07-24-revert-provider-model-filter-design.md`: approved revert design; retain unchanged.
- `docs/superpowers/plans/2026-07-24-revert-provider-model-filter.md`: this execution plan; retain unchanged.

### Task 1: Lock and restore provider-only routing behavior

**Files:**

- Create: `tests/test_provider_model_filter_revert.py`
- Modify through Git revert: `patch_chatgpt_providers.py`
- Modify through Git revert: `tests/test_sync_codex_models.py`
- Modify through Git revert: `README.md`
- Delete through Git revert: `docs/superpowers/specs/2026-07-24-provider-model-filter-build-5813-design.md`
- Delete through Git revert: `docs/superpowers/plans/2026-07-24-provider-model-filter-build-5813.md`

**Interfaces:**

- Consumes: `patcher.CENTRAL_DIFF`, `patcher.PICKER_DIFF`, and `patcher.print_completion_summary(...)`.
- Produces: a provider picker that persists `codex.customProviderSelection.v1` and supplies `modelProvider` to `thread/start` and `thread/fork`, with no model-catalog filtering or automatic selection changes.

- [ ] **Step 1: Add the failing provider-only routing regression contract.**

Create `tests/test_provider_model_filter_revert.py` with this complete content:

```python
from pathlib import Path
import unittest
from unittest import mock

import patch_chatgpt_providers as patcher


FILTER_MARKERS = (
    "e.listeners ??= new Set()",
    "e.revision ??= 0",
    "codexPickerSetCustomProviderChoice",
    "codexProviderForModel",
    "codexFilterModelsForProvider",
    "codexUseProviderFilteredModels",
    "codexCanonicalModelSlug",
    "codexFindProviderModelReplacement",
    "codexReplacementReasoningEffort",
    "x = codexUseProviderFilteredModels(y?.models)",
)


class ProviderModelFilterRevertTests(unittest.TestCase):
    def test_provider_selection_routes_requests_without_filtering_models(self):
        self.assertIn(
            "function CodexCustomProviderPickerSection()",
            patcher.PICKER_DIFF,
        )
        self.assertIn("codexWriteCustomProviderChoice", patcher.PICKER_DIFF)
        self.assertIn("thread/start", patcher.CENTRAL_DIFF)
        self.assertIn("thread/fork", patcher.CENTRAL_DIFF)
        self.assertIn("if (e === `thread/list`)", patcher.CENTRAL_DIFF)
        self.assertIn("modelProviders: []", patcher.CENTRAL_DIFF)
        self.assertIn(
            "modelProvider: await codexSelectedProvider()",
            patcher.CENTRAL_DIFF,
        )
        for marker in FILTER_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, patcher.PICKER_DIFF)

    def test_completion_summary_marks_model_mapping_compatibility_only(self):
        with (
            mock.patch.object(patcher, "terminal_bullet") as bullet,
            mock.patch.object(patcher, "terminal_status"),
            mock.patch.object(patcher, "terminal_heading"),
            mock.patch("builtins.print"),
        ):
            patcher.print_completion_summary(
                Path("/tmp/desktop-model-providers.json"),
                already_installed=True,
            )

        self.assertIn(
            mock.call(
                "model_providers",
                "Retained for generated-config compatibility; "
                "model IDs do not choose a provider.",
            ),
            bullet.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the regression contract and confirm the current filter fails it.**

Run:

```bash
python3 -m unittest -v tests/test_provider_model_filter_revert.py
```

Expected: two failures. The first reports at least one filter marker still in
`PICKER_DIFF`; the second reports the current picker-filtering completion copy
instead of the compatibility-only copy.

- [ ] **Step 3: Apply the six isolated reverts without creating intermediate commits.**

Run from the isolated worktree:

```bash
git revert --no-commit cb6ce84 096a169 1e41336 763054c 5a0b17c 5e1166b
git status --short
```

Expected: no conflicts. `README.md`, `patch_chatgpt_providers.py`, and
`tests/test_sync_codex_models.py` are modified; the superseded filter spec and
plan are deleted; the new regression test remains untracked. The approved
revert spec and this plan remain unchanged.

- [ ] **Step 4: Run the focused contract and retained provider-routing tests.**

Run:

```bash
python3 -m unittest -v tests/test_provider_model_filter_revert.py
python3 -m unittest -v \
  tests.test_sync_codex_models.PatcherTemplateTests.test_provider_picker_defaults_legacy_auto_to_openai_without_showing_auto \
  tests.test_sync_codex_models.PatcherTemplateTests.test_start_and_fork_use_the_explicit_picker_provider \
  tests.test_sync_codex_models.PatcherTemplateTests.test_embedded_diffs_target_build_5813_bundle_symbols \
  tests.test_sync_codex_models.CurrentBundleTests.test_current_patch_bundle_finds_build_5813_app_initial \
  tests.test_sync_codex_models.CurrentBundleTests.test_patch_current_bundle_applies_both_diffs_to_one_file
```

Expected: all seven tests pass. The first command contributes two regression
tests; the second contributes five retained compatibility and routing tests.

- [ ] **Step 5: Run the complete unit and CLI verification.**

Run:

```bash
python3 -m unittest -v
git diff --check
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
```

Expected: the full suite passes, `git diff --check` prints nothing, and both
help commands exit with status 0.

- [ ] **Step 6: Build and inspect temporary artifacts from the clean build-5813 original.**

Run this read-only verification script. It calls the production build helper,
which applies the embedded diffs, runs Prettier and `node --check`, packs the
ASAR, and checks the patch marker. It never calls `install_patched_artifacts`.

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
assert info["CFBundleShortVersionString"] == "26.721.30844"
assert str(info["CFBundleVersion"]) == "5813"

with tempfile.TemporaryDirectory(prefix="provider-routing-revert-") as temporary:
    work = Path(temporary)
    patched_asar, patched_plist = patcher.build_patched_artifacts(original, work)
    bundle = patcher.current_patch_bundle(work / "app/webview/assets")
    source = bundle.read_text(encoding="utf-8")

    assert "CodexCustomProviderPickerSection" in source
    assert "modelProvider: await codexSelectedProvider()" in source
    assert "if (e === `thread/list`)" in source
    assert "modelProviders: []" in source
    for marker in (
        "codexUseProviderFilteredModels",
        "codexFindProviderModelReplacement",
        "codexFilterModelsForProvider",
    ):
        assert marker not in source

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

Expected: production patch/build output completes successfully, the final JSON
contains `"status": "ok"`, and all four protected hashes are unchanged.

- [ ] **Step 7: Inspect the exact revert and commit it.**

Run:

```bash
git diff --stat
git diff -- README.md patch_chatgpt_providers.py tests/test_sync_codex_models.py tests/test_provider_model_filter_revert.py
git status --short
git add -A \
  README.md \
  patch_chatgpt_providers.py \
  tests/test_sync_codex_models.py \
  tests/test_provider_model_filter_revert.py \
  docs/superpowers/specs/2026-07-24-provider-model-filter-build-5813-design.md \
  docs/superpowers/plans/2026-07-24-provider-model-filter-build-5813.md
git commit -m "revert: remove provider model filtering"
git status --short --branch
```

Expected: the commit contains the exact six-commit feature reversal plus the
new provider-only routing regression test. The final status is clean.

- [ ] **Step 8: Re-run verification against the committed tree.**

Run:

```bash
python3 -m unittest -v
git diff --check HEAD^
python3 patch_chatgpt_providers.py --help >/dev/null
python3 sync_codex_models.py --help >/dev/null
git show --stat --oneline HEAD
```

Expected: every command exits 0; the final commit summary shows only the
intended filter removal, superseded documentation deletion, and regression
test addition.
