import tempfile
import unittest
from pathlib import Path

from app.infrastructure.analyzers.project_analyzer import ProjectAnalyzer
from app.infrastructure.analyzers.spring_boot_eligibility import compute_eligibility

_LEGACY_SPRING_POM = """<?xml version="1.0"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>legacy-app</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-webmvc</artifactId>
      <version>5.3.20</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>5.3.20</version>
    </dependency>
  </dependencies>
</project>
"""

_SPRING_BOOT_PARENT_POM = """<?xml version="1.0"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.5</version>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>boot-app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
"""

_PLAIN_JAVA_POM = """<?xml version="1.0"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>plain-app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
      <version>32.1.3-jre</version>
    </dependency>
  </dependencies>
</project>
"""

# A custom internal parent that manages Spring Boot elsewhere -- the pom alone
# gives no version-bearing signal, so detection must fall back to scanning the
# actual source code for @SpringBootApplication / SpringApplication.run(...).
_CUSTOM_PARENT_BOOT_POM = """<?xml version="1.0"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>internal-platform-parent</artifactId>
    <version>4.1.0</version>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>internal-app</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.1.6</version>
    </dependency>
  </dependencies>
</project>
"""

_ENTRY_CLASS = """package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InternalApplication {
    public static void main(String[] args) {
        SpringApplication.run(InternalApplication.class, args);
    }
}
"""


class ProjectAnalyzerSpringDetectionTests(unittest.TestCase):
    def test_legacy_spring_mvc_project_is_conversion_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(_LEGACY_SPRING_POM, encoding="utf-8")

            analysis = ProjectAnalyzer().analyze(root)

            self.assertEqual(analysis.project_type, "SPRING_MVC")
            self.assertIsNone(analysis.spring_boot_version)
            self.assertEqual(analysis.spring_framework_version, "5.3.20")

            eligibility = compute_eligibility(
                build_tool_supported=analysis.is_supported,
                build_tool=analysis.build_tool,
                project_type=analysis.project_type,
                spring_framework_version=analysis.spring_framework_version,
                spring_boot_version=analysis.spring_boot_version,
                spring_boot_signal=analysis.spring_boot_signal,
                entrypoint_found=analysis.spring_entry_class is not None,
            )
            self.assertTrue(eligibility.spring_boot_conversion_eligible)
            self.assertFalse(eligibility.spring_boot_upgrade_eligible)

    def test_existing_spring_boot_project_is_upgrade_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(_SPRING_BOOT_PARENT_POM, encoding="utf-8")

            analysis = ProjectAnalyzer().analyze(root)

            self.assertEqual(analysis.project_type, "SPRING_BOOT")
            self.assertEqual(analysis.spring_boot_version, "3.2.5")

            eligibility = compute_eligibility(
                build_tool_supported=analysis.is_supported,
                build_tool=analysis.build_tool,
                project_type=analysis.project_type,
                spring_framework_version=analysis.spring_framework_version,
                spring_boot_version=analysis.spring_boot_version,
                spring_boot_signal=analysis.spring_boot_signal,
                entrypoint_found=analysis.spring_entry_class is not None,
            )
            self.assertFalse(eligibility.spring_boot_conversion_eligible)
            self.assertTrue(eligibility.spring_boot_upgrade_eligible)

    def test_plain_java_project_is_not_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(_PLAIN_JAVA_POM, encoding="utf-8")

            analysis = ProjectAnalyzer().analyze(root)

            self.assertEqual(analysis.project_type, "PLAIN_JAVA")

            eligibility = compute_eligibility(
                build_tool_supported=analysis.is_supported,
                build_tool=analysis.build_tool,
                project_type=analysis.project_type,
                spring_framework_version=analysis.spring_framework_version,
                spring_boot_version=analysis.spring_boot_version,
                spring_boot_signal=analysis.spring_boot_signal,
                entrypoint_found=analysis.spring_entry_class is not None,
            )
            self.assertFalse(eligibility.spring_boot_conversion_eligible)
            self.assertFalse(eligibility.spring_boot_upgrade_eligible)

    def test_custom_parent_boot_project_detected_via_code_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(_CUSTOM_PARENT_BOOT_POM, encoding="utf-8")
            src_dir = root / "src" / "main" / "java" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "InternalApplication.java").write_text(_ENTRY_CLASS, encoding="utf-8")

            analysis = ProjectAnalyzer().analyze(root)

            self.assertTrue(analysis.spring_boot_signal)
            self.assertEqual(
                analysis.spring_entry_class,
                "src/main/java/com/example/InternalApplication.java",
            )
            self.assertEqual(analysis.project_type, "SPRING_BOOT")

            eligibility = compute_eligibility(
                build_tool_supported=analysis.is_supported,
                build_tool=analysis.build_tool,
                project_type=analysis.project_type,
                spring_framework_version=analysis.spring_framework_version,
                spring_boot_version=analysis.spring_boot_version,
                spring_boot_signal=analysis.spring_boot_signal,
                entrypoint_found=analysis.spring_entry_class is not None,
            )
            self.assertTrue(eligibility.spring_boot_upgrade_eligible)
            self.assertFalse(eligibility.spring_boot_conversion_eligible)


if __name__ == "__main__":
    unittest.main()
