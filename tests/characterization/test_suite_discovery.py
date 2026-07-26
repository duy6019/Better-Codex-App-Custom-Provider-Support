"""CHARACTERIZATION TESTS — ghim hành vi thu thập test đang có.

Các test này PHẢI pass ngay từ đầu; pass ngay là điều kiện thành công, không phải
red flag. Chúng tồn tại để bảo vệ thao tác đổi tên file test: rủi ro chính của một
lần `git mv` trong `tests/` là file rơi khỏi phạm vi discovery mà không ai nhận ra,
vì suite vẫn báo OK — chỉ là ít test hơn.
"""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent.parent
TESTS = ROOT / "tests"

# Số test suite thu được trước khi thêm bất kỳ guard nào của change
# rename-sync-catalog-test. Con số này là sàn, không phải mốc cố định: thêm test
# thì nó tăng, còn tụt xuống dưới nghĩa là có file đã rơi khỏi discovery.
BASELINE_TEST_COUNT = 157


def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def discovered_tests() -> list[unittest.TestCase]:
    suite = unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(ROOT))
    return list(flatten(suite))


class SuiteDiscoveryTests(unittest.TestCase):
    def test_every_test_module_imports_cleanly(self):
        broken = [
            test.id()
            for test in discovered_tests()
            if type(test).__name__ == "_FailedTest"
        ]
        self.assertEqual(
            [],
            broken,
            "Module test không nạp được (unittest biến lỗi import thành _FailedTest, "
            "nên suite vẫn chạy nhưng độ phủ thật đã mất)",
        )

    def test_suite_collects_at_least_the_baseline_count(self):
        collected = len(discovered_tests())
        self.assertGreaterEqual(
            collected,
            BASELINE_TEST_COUNT,
            f"Discovery thu được {collected} test, dưới sàn {BASELINE_TEST_COUNT}. "
            "Một file test đã rơi khỏi discovery hoặc bị xoá nhầm.",
        )

    def test_discovery_follows_source_files_not_bytecode(self):
        expected = {path.stem for path in TESTS.rglob("test_*.py")}
        discovered = {
            type(test).__module__.rsplit(".", 1)[-1] for test in discovered_tests()
        }
        self.assertEqual(
            expected,
            discovered,
            "Tập module test thu được phải khớp đúng tập file nguồn test_*.py. "
            "Lệch nghĩa là discovery đang nạp thứ không còn nguồn (bytecode mồ côi) "
            "hoặc bỏ sót file nguồn có thật.",
        )
