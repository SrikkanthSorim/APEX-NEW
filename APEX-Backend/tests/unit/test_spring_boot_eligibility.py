import unittest

from app.infrastructure.analyzers.spring_boot_eligibility import compute_eligibility


class SpringBootEligibilityTests(unittest.TestCase):
    def test_traditional_spring_project_is_conversion_eligible(self) -> None:
        result = compute_eligibility(
            build_tool_supported=True,
            build_tool="MAVEN",
            project_type="SPRING_MVC",
            spring_framework_version="5.3.20",
            spring_boot_version=None,
            spring_boot_signal=False,
            entrypoint_found=False,
        )

        self.assertTrue(result.spring_detected)
        self.assertFalse(result.spring_boot_detected)
        self.assertTrue(result.spring_boot_conversion_eligible)
        self.assertFalse(result.spring_boot_upgrade_eligible)
        self.assertEqual(result.eligibility_reason, "Eligible for Spring Boot conversion.")

    def test_existing_spring_boot_project_is_upgrade_eligible_not_conversion_eligible(self) -> None:
        result = compute_eligibility(
            build_tool_supported=True,
            build_tool="MAVEN",
            project_type="SPRING_BOOT",
            spring_framework_version=None,
            spring_boot_version="2.7.18",
            spring_boot_signal=True,
            entrypoint_found=True,
        )

        self.assertTrue(result.spring_detected)
        self.assertTrue(result.spring_boot_detected)
        self.assertFalse(result.spring_boot_conversion_eligible)
        self.assertTrue(result.spring_boot_upgrade_eligible)
        self.assertEqual(
            result.eligibility_reason, "This repository is already a Spring Boot application."
        )

    def test_non_spring_java_project_is_not_eligible(self) -> None:
        result = compute_eligibility(
            build_tool_supported=True,
            build_tool="GRADLE",
            project_type="PLAIN_JAVA",
            spring_framework_version=None,
            spring_boot_version=None,
            spring_boot_signal=False,
            entrypoint_found=False,
        )

        self.assertFalse(result.spring_detected)
        self.assertFalse(result.spring_boot_detected)
        self.assertTrue(result.java_migration_eligible)
        self.assertFalse(result.spring_boot_conversion_eligible)
        self.assertFalse(result.spring_boot_upgrade_eligible)
        self.assertEqual(
            result.eligibility_reason, "Spring Framework was not detected in this repository."
        )

    def test_unsupported_build_tool_disables_both_pathways(self) -> None:
        result = compute_eligibility(
            build_tool_supported=False,
            build_tool="UNKNOWN",
            project_type="UNKNOWN",
            spring_framework_version=None,
            spring_boot_version=None,
            spring_boot_signal=False,
            entrypoint_found=False,
        )

        self.assertFalse(result.spring_boot_conversion_eligible)
        self.assertFalse(result.spring_boot_upgrade_eligible)
        self.assertFalse(result.java_migration_eligible)

    def test_entrypoint_only_signal_still_marks_spring_boot_detected(self) -> None:
        """A @SpringBootApplication/SpringApplication.run() code signal alone
        (no resolvable build-file version) must still count as Spring Boot."""
        result = compute_eligibility(
            build_tool_supported=True,
            build_tool="MAVEN",
            project_type="SPRING_BOOT",
            spring_framework_version=None,
            spring_boot_version=None,
            spring_boot_signal=False,
            entrypoint_found=True,
        )

        self.assertTrue(result.spring_boot_detected)
        self.assertTrue(result.spring_boot_upgrade_eligible)
        self.assertFalse(result.spring_boot_conversion_eligible)

    def test_to_dict_uses_required_field_names(self) -> None:
        result = compute_eligibility(
            build_tool_supported=True,
            build_tool="MAVEN",
            project_type="SPRING_MVC",
            spring_framework_version="5.3.20",
            spring_boot_version=None,
            spring_boot_signal=False,
            entrypoint_found=False,
        )

        self.assertEqual(
            set(result.to_dict().keys()),
            {
                "repositoryAnalyzed",
                "javaMigrationEligible",
                "javaMigrationReason",
                "springDetected",
                "springBootDetected",
                "springVersion",
                "springBootVersion",
                "buildTool",
                "springBootConversionEligible",
                "springBootUpgradeEligible",
                "eligibilityReason",
            },
        )


if __name__ == "__main__":
    unittest.main()
