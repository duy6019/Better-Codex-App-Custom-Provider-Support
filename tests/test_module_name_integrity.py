"""Guard the module names that tests and project docs refer to.

Renaming a root module and forgetting to clean up leaves two kinds of debris that
no ordinary test catches: a dead name quoted in the docs, and a dead name carried
by a test filename. Neither fails anything, so both survive for a long time.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# Surfaces this guard reads. `.superpowers/` and `openspec/changes/` are excluded
# on purpose: they are work logs and proposals that record the repository as it
# stood when they were written. Rewriting them to match the present would falsify
# the record.
SCANNED_DOCS = ("README.md", "CLAUDE.md", "openspec/config.yaml")

MODULE_REFERENCE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.py\b")

# Test modules that cut across several modules, so they carry no module name. The
# allowlist lives in source rather than an external config file so that every new
# exemption shows up in a diff and gets reviewed.
THEME_NAMED_TESTS = {
    "windows_compatibility": "runs the patcher on Windows; not tied to one module",
    "windows_store_patch": "covers the Windows Store patch flow across many helpers",
    "provider_model_filter_revert": "covers one revert scenario, not a module",
    "module_name_integrity": "guards a naming convention; tests no single module",
    "suite_discovery": "pins how the suite itself collects tests",
}


def scanned_surfaces() -> list[Path]:
    # This module is excluded from its own scan: it has to spell out the names it
    # forbids, so scanning it would make the guard permanently red.
    this_file = Path(__file__).resolve()
    modules = [path for path in TESTS.rglob("test_*.py") if path.resolve() != this_file]
    return sorted(modules) + [ROOT / name for name in SCANNED_DOCS]


def test_modules() -> list[Path]:
    return sorted(TESTS.rglob("test_*.py"))


def resolves(module_name: str) -> bool:
    if (ROOT / f"{module_name}.py").is_file():
        return True
    return any(path.stem == module_name for path in TESTS.rglob("*.py"))


class ModuleReferenceTests(unittest.TestCase):
    def test_every_module_reference_points_at_a_real_file(self):
        unresolved = []
        for surface in scanned_surfaces():
            relative = surface.relative_to(ROOT).as_posix()
            lines = surface.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, 1):
                for match in MODULE_REFERENCE.finditer(line):
                    name = match.group(1)
                    if not resolves(name):
                        unresolved.append(f"{relative}:{lineno} -> {name}.py")

        self.assertEqual(
            [],
            unresolved,
            "References to modules that do not exist (renamed without cleanup?):\n  "
            + "\n  ".join(unresolved),
        )


class TestModuleNamingTests(unittest.TestCase):
    def test_every_test_module_names_its_subject(self):
        misnamed = []
        for path in test_modules():
            subject = path.stem[len("test_") :]
            if (ROOT / f"{subject}.py").is_file():
                continue
            if subject in THEME_NAMED_TESTS:
                continue
            misnamed.append(
                f"{path.relative_to(ROOT).as_posix()}: no {subject}.py at repo root"
            )

        self.assertEqual(
            [],
            misnamed,
            "Test file does not say what it tests. Either rename it to match the "
            "module under test, or add it to THEME_NAMED_TESTS with a reason:\n  "
            + "\n  ".join(misnamed),
        )

    def test_allowlist_carries_no_stale_entries(self):
        stale = []
        existing = {path.stem[len("test_") :] for path in test_modules()}
        for subject, reason in THEME_NAMED_TESTS.items():
            if subject not in existing:
                stale.append(f"{subject}: no matching test_{subject}.py")
            elif (ROOT / f"{subject}.py").is_file():
                stale.append(f"{subject}: {subject}.py now exists; exemption is moot")
            if not reason.strip():
                stale.append(f"{subject}: exemption has no stated reason")

        self.assertEqual(
            [],
            stale,
            "THEME_NAMED_TESTS has stale or unexplained entries:\n  "
            + "\n  ".join(stale),
        )


class RetiredModuleNameTests(unittest.TestCase):
    RETIRED = "sync_codex_models"

    def test_retired_sync_module_name_appears_nowhere(self):
        hits = []
        for surface in scanned_surfaces():
            relative = surface.relative_to(ROOT).as_posix()
            lines = surface.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, 1):
                if self.RETIRED in line:
                    hits.append(f"{relative}:{lineno}")

        self.assertEqual(
            [],
            hits,
            f"{self.RETIRED} was removed from the repository, but the name "
            "survives at:\n  " + "\n  ".join(hits),
        )

    def test_sync_catalog_test_module_uses_the_current_name(self):
        self.assertTrue(
            (TESTS / "test_sync_model_catalog.py").is_file(),
            "tests/test_sync_model_catalog.py should exist",
        )
        self.assertFalse(
            (TESTS / "test_sync_codex_models.py").exists(),
            "tests/test_sync_codex_models.py is named after a removed module",
        )
