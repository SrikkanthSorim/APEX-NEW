"""Computes Spring -> Spring Boot conversion eligibility from real Discovery
analysis results.

Pure function over already-detected facts (project type, framework/version
signals, entry-point scan, build-tool support) -- no repository URL, name, or
mock data is ever consulted. This is the single source of truth the Discovery
response, the saved discovery report, and the migration-config normalization
all read from, so the enable/disable decision can never drift between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REASON_CONVERSION_ELIGIBLE = "Eligible for Spring Boot conversion."
REASON_ALREADY_SPRING_BOOT = "This repository is already a Spring Boot application."
REASON_NOT_SPRING = "Spring Framework was not detected in this repository."
REASON_UNSUPPORTED_PROJECT = (
    "Repository analysis could not determine a supported build tool "
    "(Maven or Gradle); Spring Boot conversion is unavailable."
)
REASON_JAVA_ELIGIBLE = "Eligible for Java/JDK version migration."
REASON_JAVA_UNSUPPORTED = (
    "Repository analysis could not determine a supported Java build tool "
    "(Maven or Gradle)."
)


@dataclass(frozen=True)
class SpringBootEligibility:
    repository_analyzed: bool
    java_migration_eligible: bool
    java_migration_reason: str
    spring_detected: bool
    spring_boot_detected: bool
    spring_version: str | None
    spring_boot_version: str | None
    build_tool: str
    spring_boot_conversion_eligible: bool
    spring_boot_upgrade_eligible: bool
    eligibility_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryAnalyzed": self.repository_analyzed,
            "javaMigrationEligible": self.java_migration_eligible,
            "javaMigrationReason": self.java_migration_reason,
            "springDetected": self.spring_detected,
            "springBootDetected": self.spring_boot_detected,
            "springVersion": self.spring_version,
            "springBootVersion": self.spring_boot_version,
            "buildTool": self.build_tool,
            "springBootConversionEligible": self.spring_boot_conversion_eligible,
            "springBootUpgradeEligible": self.spring_boot_upgrade_eligible,
            "eligibilityReason": self.eligibility_reason,
        }


def compute_eligibility(
    *,
    build_tool_supported: bool,
    build_tool: str,
    project_type: str,
    spring_framework_version: str | None,
    spring_boot_version: str | None,
    spring_boot_signal: bool,
    entrypoint_found: bool,
) -> SpringBootEligibility:
    spring_boot_detected = bool(
        spring_boot_version
        or spring_boot_signal
        or entrypoint_found
        or project_type == "SPRING_BOOT"
    )
    spring_detected = bool(
        spring_boot_detected
        or project_type == "SPRING_MVC"
        or spring_framework_version
    )

    if not build_tool_supported:
        return SpringBootEligibility(
            repository_analyzed=True,
            java_migration_eligible=False,
            java_migration_reason=REASON_JAVA_UNSUPPORTED,
            spring_detected=spring_detected,
            spring_boot_detected=spring_boot_detected,
            spring_version=spring_framework_version,
            spring_boot_version=spring_boot_version,
            build_tool=build_tool,
            spring_boot_conversion_eligible=False,
            spring_boot_upgrade_eligible=False,
            eligibility_reason=REASON_UNSUPPORTED_PROJECT,
        )

    if spring_boot_detected:
        conversion_eligible = False
        upgrade_eligible = True
        reason = REASON_ALREADY_SPRING_BOOT
    elif spring_detected:
        conversion_eligible = True
        upgrade_eligible = False
        reason = REASON_CONVERSION_ELIGIBLE
    else:
        conversion_eligible = False
        upgrade_eligible = False
        reason = REASON_NOT_SPRING

    return SpringBootEligibility(
        repository_analyzed=True,
        java_migration_eligible=True,
        java_migration_reason=REASON_JAVA_ELIGIBLE,
        spring_detected=spring_detected,
        spring_boot_detected=spring_boot_detected,
        spring_version=spring_framework_version,
        spring_boot_version=spring_boot_version,
        build_tool=build_tool,
        spring_boot_conversion_eligible=conversion_eligible,
        spring_boot_upgrade_eligible=upgrade_eligible,
        eligibility_reason=reason,
    )
