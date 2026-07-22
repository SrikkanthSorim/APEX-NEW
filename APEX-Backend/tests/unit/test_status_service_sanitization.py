import shutil
import tempfile
import unittest
from pathlib import Path

from app.application.services.status_service import MigrationReportStore
from app.infrastructure.workspace.workspace_paths import WorkspacePaths


class AppendLogsSanitizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="javaapex-log-sanitizer-test-"))
        self.paths = WorkspacePaths("job-1", storage_dir=self._tmp)
        self.store = MigrationReportStore(self.paths)
        self.store.write({"jobId": "job-1", "logLines": []})

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_raw_lines_are_preserved_on_disk_but_not_in_the_report(self) -> None:
        raw_lines = [
            "Selected Java recipe for target 21: org.openrewrite.java.migrate.UpgradeToJava21",
            "[ERROR] org.openrewrite.maven.MavenDownloadingException: could not resolve dependencies",
        ]
        self.store.append_logs(raw_lines)

        # Backend-only raw mirror: full technical detail, untouched.
        raw_on_disk = self.paths.migration_log_path.read_text(encoding="utf-8")
        for line in raw_lines:
            self.assertIn(line, raw_on_disk)

        # User-facing report: sanitized, no OpenRewrite internals.
        report = self.store.read()
        assert report is not None
        log_lines = report["logLines"]
        joined = "\n".join(log_lines)
        self.assertNotIn("org.openrewrite", joined)
        self.assertNotIn("OpenRewrite", joined)
        self.assertIn("Preparing Java version upgrade to 21", log_lines)

    def test_append_logs_is_additive_across_calls(self) -> None:
        self.store.append_logs(["[INFO] Scanning for projects..."])
        self.store.append_logs(["[INFO] Building demo 1.0.0"])
        report = self.store.read()
        assert report is not None
        self.assertEqual(
            report["logLines"],
            ["Analyzing project structure", "Preparing project build"],
        )


if __name__ == "__main__":
    unittest.main()
