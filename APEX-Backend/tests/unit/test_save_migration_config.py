import unittest

from app.application.use_cases.save_migration_config import SaveMigrationConfigUseCase


def _discovery(*, conversion_eligible: bool, upgrade_eligible: bool) -> dict:
    return {
        "springBootConversion": {
            "springBootConversionEligible": conversion_eligible,
            "springBootUpgradeEligible": upgrade_eligible,
        }
    }


class SaveMigrationConfigUseCaseTests(unittest.TestCase):
    def test_removes_spring_boot_conversion_for_plain_java_repo(self) -> None:
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version", "spring_boot"],
            _discovery(conversion_eligible=False, upgrade_eligible=False),
        )

        self.assertEqual(conversions, ["java_version"])

    def test_does_not_add_spring_boot_conversion_for_upgrade_eligible_repo(self) -> None:
        """Already Spring Boot -> upgrade workflow is available, but opt-in."""
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version"],
            _discovery(conversion_eligible=False, upgrade_eligible=True),
        )

        self.assertEqual(conversions, ["java_version"])

    def test_keeps_explicit_spring_boot_conversion_for_conversion_eligible_repo(self) -> None:
        """Traditional Spring (non-Boot) -> selected conversion stays available."""
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version", "spring_boot"],
            _discovery(conversion_eligible=True, upgrade_eligible=False),
        )

        self.assertEqual(conversions, ["java_version", "spring_boot"])

    def test_collapses_spring_boot_alias_to_canonical_conversion(self) -> None:
        conversions = SaveMigrationConfigUseCase._normalize_conversion_types(
            ["java_version", "spring-to-spring-boot"],
            _discovery(conversion_eligible=False, upgrade_eligible=True),
        )

        self.assertEqual(conversions, ["java_version", "spring_boot"])


if __name__ == "__main__":
    unittest.main()
