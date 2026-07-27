import unittest
from pathlib import Path

from app.infrastructure.testing.build_tool_paths import (
    find_test_results_dir,
    jacoco_report_path,
    stale_report_dirs,
)

_PROJECT = Path("/tmp/project")


class BuildToolPathsTests(unittest.TestCase):
    def test_maven_paths(self) -> None:
        self.assertEqual(find_test_results_dir(_PROJECT, "MAVEN"), _PROJECT / "target" / "surefire-reports")
        self.assertEqual(
            jacoco_report_path(_PROJECT, "MAVEN"), _PROJECT / "target" / "site" / "jacoco" / "jacoco.xml"
        )
        self.assertEqual(
            stale_report_dirs(_PROJECT, "MAVEN"),
            (_PROJECT / "target" / "surefire-reports", _PROJECT / "target" / "site" / "jacoco"),
        )

    def test_gradle_paths(self) -> None:
        self.assertEqual(find_test_results_dir(_PROJECT, "GRADLE"), _PROJECT / "build" / "test-results" / "test")
        self.assertEqual(
            jacoco_report_path(_PROJECT, "GRADLE"),
            _PROJECT / "build" / "reports" / "jacoco" / "test" / "jacocoTestReport.xml",
        )
        self.assertEqual(
            stale_report_dirs(_PROJECT, "GRADLE"),
            (_PROJECT / "build" / "test-results" / "test", _PROJECT / "build" / "reports" / "jacoco"),
        )

    def test_build_tool_is_case_insensitive_and_defaults_to_maven(self) -> None:
        self.assertEqual(find_test_results_dir(_PROJECT, "gradle"), _PROJECT / "build" / "test-results" / "test")
        self.assertEqual(find_test_results_dir(_PROJECT, ""), _PROJECT / "target" / "surefire-reports")


if __name__ == "__main__":
    unittest.main()
