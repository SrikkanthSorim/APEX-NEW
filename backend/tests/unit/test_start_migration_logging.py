from unittest import TestCase

from app.application.use_cases.start_migration import StartMigrationUseCase
from app.infrastructure.build.gradle_log_hints import SOPHOS_GRADLE_LOCK_HINT


class StartMigrationLoggingTests(TestCase):
    def test_migration_error_lines_are_written_to_backend_logger(self):
        with self.assertLogs(
            "app.application.use_cases.start_migration",
            level="WARNING",
        ) as captured:
            StartMigrationUseCase._log_migration_error_lines(
                "job-123",
                [SOPHOS_GRADLE_LOCK_HINT],
            )

        self.assertIn("Migration tool error for job job-123", captured.output[0])
        self.assertIn(SOPHOS_GRADLE_LOCK_HINT, captured.output[0])