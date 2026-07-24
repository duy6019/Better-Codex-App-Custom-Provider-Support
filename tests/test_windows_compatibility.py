import io
import subprocess
import sys
import unittest

import patch_chatgpt_providers as patcher


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

    def test_terminal_status_uses_ascii_detail_marker_for_cp1252_stream(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

        patcher.terminal_status(
            "CONFIG", "Configured", "36", detail="C:\\config.toml", stream=stream
        )
        stream.flush()

        self.assertIn(b"-> C:\\config.toml", buffer.getvalue())
