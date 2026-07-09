from unittest import TestCase

from app.infrastructure.build.build_log_parser import parse_build_output
from app.infrastructure.build.gradle_log_hints import SOPHOS_GRADLE_LOCK_HINT


_GRADLE_ACCESS_DENIED = """
FAILURE: Build failed with an exception.

* What went wrong:
Could not move temporary workspace
(C:\\Users\\dev\\.gradle\\caches\\8.9\\transforms\\abc)
to immutable location
(C:\\Users\\dev\\.gradle\\caches\\8.9\\transforms\\def)

Caused by: java.nio.file.AccessDeniedException:
C:\\Users\\dev\\.gradle\\caches\\8.9\\transforms\\abc\\metadata.bin
"""


class BuildLogParserTests(TestCase):
    def test_adds_sophos_hint_for_gradle_temp_workspace_access_denied(self):
        parsed = parse_build_output(_GRADLE_ACCESS_DENIED, "")

        self.assertGreaterEqual(len(parsed.error_lines), 4)
        self.assertEqual(parsed.error_lines[0], SOPHOS_GRADLE_LOCK_HINT)
        self.assertTrue(
            any("Could not move temporary workspace" in line for line in parsed.error_lines)
        )
        self.assertTrue(
            any("AccessDeniedException" in line for line in parsed.error_lines)
        )
