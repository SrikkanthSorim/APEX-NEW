from unittest import TestCase

from app.infrastructure.build.gradle_log_hints import SOPHOS_GRADLE_LOCK_HINT
from app.infrastructure.migration_engine.migration_log_parser import parse_rewrite_output


class MigrationLogParserTests(TestCase):
    def test_adds_sophos_hint_for_gradle_rewrite_access_denied(self):
        stderr = """
FAILURE: Build failed with an exception.
* What went wrong:
Could not move temporary workspace (C:\\Users\\dev\\.gradle\\caches\\modules-2\\tmp)
Caused by: java.nio.file.AccessDeniedException: C:\\Users\\dev\\.gradle\\caches\\modules-2\\tmp
"""

        parsed = parse_rewrite_output("", stderr)

        self.assertEqual(parsed.error_lines[0], SOPHOS_GRADLE_LOCK_HINT)
        self.assertTrue(
            any("Could not move temporary workspace" in line for line in parsed.error_lines)
        )
        self.assertTrue(
            any("AccessDeniedException" in line for line in parsed.error_lines)
        )
