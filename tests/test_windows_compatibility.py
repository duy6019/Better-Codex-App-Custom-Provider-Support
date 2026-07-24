import subprocess
import sys
import unittest


class WindowsCompatibilityTests(unittest.TestCase):
    def test_patch_module_imports_when_the_pwd_module_is_unavailable(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.modules['pwd'] = None; import patch_chatgpt_providers",
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
