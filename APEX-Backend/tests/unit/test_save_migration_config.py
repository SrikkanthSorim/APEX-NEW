import unittest

from app.application.use_cases.save_migration_config import SaveMigrationConfigUseCase


class SaveMigrationConfigUseCaseTests(unittest.TestCase):
    def test_removes_spring_boot_conversion_for_plain_java_repo(self) -> None:
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version", "spring_boot"],
            {"projectType": "PLAIN_JAVA", "springBootVersion": None},
        )

        self.assertEqual(conversions, ["java_version"])

    def test_adds_spring_boot_conversion_for_detected_spring_boot_repo(self) -> None:
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version"],
            {"projectType": "SPRING_BOOT", "springBootVersion": "2.7.18"},
        )

        self.assertEqual(conversions, ["java_version", "spring_boot"])

    def test_collapses_spring_boot_alias_to_canonical_conversion(self) -> None:
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version", "spring-to-spring-boot"],
            {"projectType": "SPRING_BOOT"},
        )

        self.assertEqual(conversions, ["java_version", "spring_boot"])


if __name__ == "__main__":
    unittest.main()
