import unittest

from app.shared import migration_log_sanitizer as sanitizer


class SanitizeLineTests(unittest.TestCase):
    def test_maven_scanning_line_is_translated(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line("[INFO] Scanning for projects..."),
            "Analyzing project structure",
        )

    def test_maven_building_line_is_translated(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line("[INFO] Building project-name 0.0.1-SNAPSHOT"),
            "Preparing project build",
        )

    def test_selected_java_recipe_line_is_translated_for_any_target(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line(
                "Selected Java recipe for target 25: org.openrewrite.java.migrate.UpgradeToJava21"
            ),
            "Preparing Java version upgrade to 25",
        )
        self.assertEqual(
            sanitizer.sanitize_line(
                "Selected Java recipe for target 17: org.openrewrite.java.migrate.UpgradeToJava17"
            ),
            "Preparing Java version upgrade to 17",
        )

    def test_asserting_exact_target_line_is_translated(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line(
                "Asserting exact target Java version 25 via UpgradeJavaVersion"
            ),
            "Applying Java version configuration",
        )

    def test_gradle_build_successful_is_translated(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line("BUILD SUCCESSFUL in 12s"),
            "Build verification succeeded",
        )

    def test_migration_phase_marker_is_translated(self) -> None:
        self.assertEqual(
            sanitizer.sanitize_line("===== MIGRATION PHASE: Java version migration ====="),
            "Starting: Java version migration",
        )

    def test_noise_lines_are_dropped(self) -> None:
        for noisy in (
            "",
            "   ",
            "----------------------------------------",
            "\tat org.openrewrite.maven.RewriteRunMojo.execute(RewriteRunMojo.java:120)",
            "Downloading from central: https://repo.maven.apache.org/x.jar",
            "> Task :compileJava",
            "org.openrewrite.recipe:rewrite-migrate-java:2.13.0",
        ):
            self.assertIsNone(sanitizer.sanitize_line(noisy), msg=noisy)

    def test_maven_downloading_exception_is_simplified(self) -> None:
        result = sanitizer.sanitize_line(
            "[ERROR] org.openrewrite.maven.MavenDownloadingException: Could not resolve dependencies"
        )
        self.assertEqual(
            result,
            "Unable to download a required Maven dependency. Check repository access and network configuration.",
        )

    def test_generic_error_line_keeps_useful_detail_without_recipe_class_name(self) -> None:
        result = sanitizer.sanitize_line(
            "[ERROR] Compilation failure: cannot find symbol in UserService.java"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("cannot find symbol", result)

    def test_errors_are_never_silently_dropped(self) -> None:
        result = sanitizer.sanitize_line("[ERROR] org.openrewrite.some.deeply.Nested$Recipe failed")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("org.openrewrite", result)

    def test_credentials_in_urls_are_redacted(self) -> None:
        result = sanitizer.sanitize_line(
            "[INFO] Pushing to https://oauth2:ghp_abcdefghijklmnopqrstuvwxyz012345@github.com/org/repo.git"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz012345", result)
        self.assertNotIn("oauth2:", result)

    def test_absolute_windows_path_is_redacted(self) -> None:
        result = sanitizer.sanitize_line(
            r"[INFO] Writing config to C:\Users\build\.javaapex-rewrite-abc123.yml"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn(r"C:\Users", result)

    def test_temp_artifact_name_is_redacted(self) -> None:
        result = sanitizer.sanitize_line(
            "[INFO] Using recipe config .javaapex-rewrite-9f1c2b7e.yml"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn(".javaapex-rewrite-9f1c2b7e.yml", result)

    def test_no_openrewrite_token_survives_any_mapped_or_cleaned_line(self) -> None:
        raw_lines = [
            "[INFO] Scanning for projects...",
            "Selected Java recipe for target 21: org.openrewrite.java.migrate.UpgradeToJava21",
            "Asserting exact target Java version 21 via UpgradeJavaVersion",
            "Selected conditional recipe jakarta-ee: org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta",
            "OpenRewrite could not run: Maven tooling was not found in this environment.",
            "No applicable OpenRewrite recipes for the selected target.",
            "[ERROR] org.openrewrite.maven.MavenDownloadingException: could not find artifact",
        ]
        for line in raw_lines:
            result = sanitizer.sanitize_line(line)
            if result is not None:
                self.assertNotIn("openrewrite", result.lower(), msg=line)


class SanitizeLinesTests(unittest.TestCase):
    def test_deduplicates_and_drops_noise(self) -> None:
        raw = [
            "[INFO] Scanning for projects...",
            "[INFO] Scanning for projects...",
            "",
            "Downloading from central: https://repo.maven.apache.org/x.jar",
            "[INFO] Building demo 1.0.0",
        ]
        result = sanitizer.sanitize_lines(raw)
        self.assertEqual(result, ["Analyzing project structure", "Preparing project build"])


class SanitizeTextTests(unittest.TestCase):
    def test_never_drops_content(self) -> None:
        text = "Modernized legacy Gradle build script in build.gradle before OpenRewrite."
        result = sanitizer.sanitize_text(text)
        self.assertTrue(result)
        self.assertNotIn("OpenRewrite", result)

    def test_embedded_recipe_names_are_humanized_in_prose(self) -> None:
        text = (
            "Executed 2 Migration recipe(s): "
            "org.openrewrite.java.migrate.UpgradeToJava21, "
            "org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta."
        )
        result = sanitizer.sanitize_text(text)
        self.assertNotIn("org.openrewrite", result)
        self.assertIn("Upgrade to Java 21", result)
        self.assertIn("Jakarta namespace migration", result)

    def test_empty_input_is_preserved(self) -> None:
        self.assertEqual(sanitizer.sanitize_text(None), "")
        self.assertEqual(sanitizer.sanitize_text(""), "")


class HumanizeRecipeNameTests(unittest.TestCase):
    def test_known_class_names(self) -> None:
        self.assertEqual(
            sanitizer.humanize_recipe_name("org.openrewrite.java.migrate.UpgradeToJava21"),
            "Upgrade to Java 21",
        )
        self.assertEqual(
            sanitizer.humanize_recipe_name("org.openrewrite.java.migrate.UpgradeToJava25"),
            "Upgrade to Java 25",
        )
        self.assertEqual(
            sanitizer.humanize_recipe_name(
                "org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta"
            ),
            "Jakarta namespace migration",
        )
        self.assertEqual(
            sanitizer.humanize_recipe_name(
                "org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_5"
            ),
            "Spring Boot 3.5 upgrade",
        )

    def test_unknown_recipe_falls_back_to_split_pascal_case(self) -> None:
        result = sanitizer.humanize_recipe_name("org.openrewrite.some.BrandNewRecipeType")
        self.assertEqual(result, "Brand New Recipe Type")

    def test_non_identifier_entry_is_scrubbed_not_shredded(self) -> None:
        result = sanitizer.humanize_recipe_name(
            "buildscript-repair: org.springframework.boot:spring-boot-gradle-plugin 2.7.1 -> 3.2.0"
        )
        self.assertIn("buildscript-repair", result.lower())
        self.assertNotIn("openrewrite", result.lower())

    def test_humanize_recipe_names_dedupes_preserving_order(self) -> None:
        result = sanitizer.humanize_recipe_names(
            [
                "org.openrewrite.java.migrate.UpgradeToJava21",
                "org.openrewrite.java.migrate.UpgradeJavaVersion",
                "org.openrewrite.java.migrate.UpgradeToJava21",
            ]
        )
        self.assertEqual(result, ["Upgrade to Java 21", "Java version configuration"])


if __name__ == "__main__":
    unittest.main()
