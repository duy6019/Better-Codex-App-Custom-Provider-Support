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
    def test_readme_targets_only_chatgpt_build_5828(self):
        readme = Path(patcher.__file__).with_name("README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("26.721.31836", readme)
        self.assertIn("build `5828`", readme)
        self.assertNotIn("26.721.30844", readme)
        self.assertNotIn("build `5813`", readme)

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
