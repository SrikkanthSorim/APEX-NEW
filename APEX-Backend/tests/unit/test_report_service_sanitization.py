import unittest

from app.application.services import report_service


class ReportServiceSanitizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_report = {
            "jobId": "job-1",
            "status": "completed",
            "logLines": [
                "[INFO] Scanning for projects...",
                "Selected Java recipe for target 25: org.openrewrite.java.migrate.UpgradeToJava21",
                "Asserting exact target Java version 25 via UpgradeJavaVersion",
                "[ERROR] org.openrewrite.maven.MavenDownloadingException: could not resolve dependencies",
                "\tat org.openrewrite.maven.RewriteRunMojo.execute(RewriteRunMojo.java:88)",
            ],
            "recipes": [
                "org.openrewrite.java.migrate.UpgradeToJava21",
                "org.openrewrite.java.migrate.UpgradeJavaVersion",
            ],
            "recipeSelection": [
                "Selected Java recipe for target 25: org.openrewrite.java.migrate.UpgradeToJava21",
            ],
            "buildModernization": [
                "Modernized legacy Gradle build script in build.gradle before OpenRewrite.",
            ],
            "migrationSummary": (
                "Executed 2 Migration recipe(s): "
                "org.openrewrite.java.migrate.UpgradeToJava21, "
                "org.openrewrite.java.migrate.UpgradeJavaVersion."
            ),
            "skippedRecipes": [
                {
                    "phase": "jakarta",
                    "label": "Jakarta namespace migration",
                    "recipes": ["org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta"],
                    "reason": "org.openrewrite.maven.MavenDownloadingException: could not find artifact",
                }
            ],
            "retryAttempts": [
                {
                    "attempt": 1,
                    "rootCause": "Build still references javax.* after the first pass; forcing the migration recipe.",
                    "recipesAdded": ["org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta"],
                    "buildStatus": "BUILD FAILED",
                }
            ],
            "springConversionNote": (
                "Legacy Spring Framework (non-Boot) to Spring Boot conversion is not yet "
                "supported: OpenRewrite has no automated recipe for bootstrapping."
            ),
            "errorMessage": None,
        }

    def _assert_no_leaks(self, value) -> None:
        if isinstance(value, str):
            self.assertNotIn("org.openrewrite", value)
            self.assertNotIn("OpenRewrite", value)
        elif isinstance(value, list):
            for item in value:
                self._assert_no_leaks(item)
        elif isinstance(value, dict):
            for item in value.values():
                self._assert_no_leaks(item)

    def test_build_result_has_no_openrewrite_internals(self) -> None:
        result = report_service.build_result(self.raw_report)
        self._assert_no_leaks(result)

        self.assertIn("Preparing Java version upgrade to 25", result["migration_log"])
        self.assertIn(
            "Unable to download a required Maven dependency. Check repository access and network configuration.",
            result["migration_log"],
        )
        self.assertEqual(result["recipes_executed"], ["Upgrade to Java 21", "Java version configuration"])
        self.assertIn("Upgrade to Java 21", result["migration_summary"])

    def test_build_summary_has_no_openrewrite_internals(self) -> None:
        result = report_service.build_summary(self.raw_report)
        self._assert_no_leaks(result)
        self.assertGreater(result["log_entry_count"], 0)

    def test_build_logs_has_no_openrewrite_internals(self) -> None:
        result = report_service.build_logs(self.raw_report)
        self._assert_no_leaks(result)
        self.assertNotIn(
            "\tat org.openrewrite.maven.RewriteRunMojo.execute(RewriteRunMojo.java:88)",
            result["logs"],
        )


if __name__ == "__main__":
    unittest.main()
