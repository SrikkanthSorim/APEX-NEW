"""Scenarios: existing test success, existing test failure, missing JaCoCo
report, valid JaCoCo report -- all against RunUnitTestsUseCase, with a fake
MavenTestRunner so no real `mvn` invocation is needed (the actual Maven/
JaCoCo mechanics are covered separately against a real scratch project).
"""

import tempfile
import unittest
from pathlib import Path

from app.application.use_cases.run_unit_tests import RunUnitTestsUseCase
from app.domain.enums.unit_test_status import (
    COVERAGE_STATUS_GENERATED,
    COVERAGE_STATUS_MISSING,
    TEST_EXECUTION_STATUS_FAILED,
    TEST_EXECUTION_STATUS_PASSED,
)
from app.domain.models.build_result import BuildResult
from app.domain.models.unit_test_report import ProjectInventory
from app.infrastructure.persistence.job_repository import JobRepository

_PASSING_SUREFIRE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.service.TodoServiceTest" tests="1" failures="0" errors="0" skipped="0" time="0.05">
  <testcase name="describeWorks" classname="com.example.service.TodoServiceTest" time="0.05"/>
</testsuite>
"""

_FAILING_SUREFIRE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.service.TodoServiceTest" tests="1" failures="1" errors="0" skipped="0" time="0.05">
  <testcase name="contextLoads" classname="com.example.service.TodoServiceTest" time="0.05">
    <failure message="Application context failed to load" type="org.opentest4j.AssertionFailedError">stack...</failure>
  </testcase>
</testsuite>
"""

_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="sample-project">
  <package name="com/example/service">
    <class name="com/example/service/TodoService">
      <counter type="LINE" missed="2" covered="8"/>
    </class>
  </package>
  <counter type="INSTRUCTION" missed="5" covered="25"/>
  <counter type="LINE" missed="2" covered="8"/>
  <counter type="BRANCH" missed="0" covered="2"/>
  <counter type="METHOD" missed="0" covered="3"/>
  <counter type="CLASS" missed="0" covered="1"/>
</report>
"""


class _FakeMavenRunner:
    """Simulates a real `mvn ... test jacoco:report` invocation: writes the
    given fixture report(s) into project_dir/target/... only when actually
    invoked, exactly like the real Maven process would -- so the use case's
    "clean stale reports before running" step (which runs before this is
    called) doesn't wipe out fixtures seeded too early by mistake.
    """

    def __init__(self, build_result: BuildResult, surefire_xml: str | None = None, jacoco_xml: str | None = None) -> None:
        self._build_result = build_result
        self._surefire_xml = surefire_xml
        self._jacoco_xml = jacoco_xml

    def run_suite_with_coverage(self, project_dir, target_major=None):
        if self._surefire_xml is not None:
            reports_dir = project_dir / "target" / "surefire-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "TEST-com.example.service.TodoServiceTest.xml").write_text(
                self._surefire_xml, encoding="utf-8"
            )
        if self._jacoco_xml is not None:
            jacoco_dir = project_dir / "target" / "site" / "jacoco"
            jacoco_dir.mkdir(parents=True, exist_ok=True)
            (jacoco_dir / "jacoco.xml").write_text(self._jacoco_xml, encoding="utf-8")
        return self._build_result


class _FakeGradleRunner:
    """Same simulation as ``_FakeMavenRunner`` but writing to Gradle's own
    report locations (build/test-results/test, build/reports/jacoco/test)."""

    def __init__(self, build_result: BuildResult, surefire_xml: str | None = None, jacoco_xml: str | None = None) -> None:
        self._build_result = build_result
        self._surefire_xml = surefire_xml
        self._jacoco_xml = jacoco_xml

    def run_suite_with_coverage(self, project_dir, target_major=None):
        if self._surefire_xml is not None:
            reports_dir = project_dir / "build" / "test-results" / "test"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "TEST-com.example.service.TodoServiceTest.xml").write_text(
                self._surefire_xml, encoding="utf-8"
            )
        if self._jacoco_xml is not None:
            jacoco_dir = project_dir / "build" / "reports" / "jacoco" / "test"
            jacoco_dir.mkdir(parents=True, exist_ok=True)
            (jacoco_dir / "jacocoTestReport.xml").write_text(self._jacoco_xml, encoding="utf-8")
        return self._build_result


def _successful_build_result() -> BuildResult:
    return BuildResult(success=True, tool="maven", status="SUCCESS", return_code=0, duration_ms=1200)


def _empty_inventory() -> ProjectInventory:
    return ProjectInventory(
        project_dir="/tmp", production_file_count=0, test_file_count=0,
        production_classes=[], test_classes=[],
    )


class ExistingTestOutcomeTests(unittest.TestCase):
    def test_existing_test_success_is_reported_as_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            job_repository = JobRepository(storage_dir=project_dir / "storage")
            runner = _FakeMavenRunner(_successful_build_result(), surefire_xml=_PASSING_SUREFIRE_XML)
            use_case = RunUnitTestsUseCase(job_repository, runner)
            report = use_case.execute("job_pass", project_dir, _empty_inventory())

        self.assertEqual(report["testExecutionStatus"], TEST_EXECUTION_STATUS_PASSED)
        self.assertEqual(report["summary"]["passedTests"], 1)
        self.assertEqual(report["summary"]["failedTests"], 0)
        self.assertEqual(report["failures"], [])

    def test_existing_test_failure_reports_real_class_method_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            job_repository = JobRepository(storage_dir=project_dir / "storage")
            runner = _FakeMavenRunner(_successful_build_result(), surefire_xml=_FAILING_SUREFIRE_XML)
            use_case = RunUnitTestsUseCase(job_repository, runner)
            report = use_case.execute("job_fail", project_dir, _empty_inventory())

        self.assertEqual(report["testExecutionStatus"], TEST_EXECUTION_STATUS_FAILED)
        self.assertEqual(report["summary"]["passedTests"], 0)
        self.assertEqual(report["summary"]["failedTests"], 1)
        self.assertEqual(len(report["failures"]), 1)
        failure = report["failures"][0]
        self.assertEqual(failure["testClass"], "com.example.service.TodoServiceTest")
        self.assertEqual(failure["testMethod"], "contextLoads")
        self.assertEqual(failure["reason"], "Application context failed to load")

    def test_stale_report_from_a_previous_run_is_never_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            reports_dir = project_dir / "target" / "surefire-reports"
            reports_dir.mkdir(parents=True)
            # Leftover from a previous (different) run, seeded before execute()
            # is called -- simulates stale build output already on disk.
            (reports_dir / "TEST-com.example.service.OldTest.xml").write_text(
                _PASSING_SUREFIRE_XML.replace("TodoServiceTest", "OldTest"), encoding="utf-8"
            )

            job_repository = JobRepository(storage_dir=project_dir / "storage")
            # This run's Maven invocation produces NO reports at all (e.g. a
            # transient failure) -- the stale OldTest report must not be
            # read as if it belonged to this run.
            use_case = RunUnitTestsUseCase(job_repository, _FakeMavenRunner(_successful_build_result()))
            report = use_case.execute("job_stale", project_dir, _empty_inventory())

        self.assertFalse(reports_dir.exists())
        self.assertFalse(report["testExecutionAvailable"])


class GradleDispatchTests(unittest.TestCase):
    def test_gradle_build_tool_uses_gradle_paths_and_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            job_repository = JobRepository(storage_dir=project_dir / "storage")
            runner = _FakeGradleRunner(
                _successful_build_result(), surefire_xml=_PASSING_SUREFIRE_XML, jacoco_xml=_JACOCO_XML,
            )
            use_case = RunUnitTestsUseCase(job_repository, gradle_runner=runner)
            report = use_case.execute("job_gradle", project_dir, _empty_inventory(), build_tool="GRADLE")

        self.assertEqual(report["testExecutionStatus"], TEST_EXECUTION_STATUS_PASSED)
        self.assertEqual(report["summary"]["passedTests"], 1)
        self.assertEqual(report["coverageStatus"], COVERAGE_STATUS_GENERATED)
        self.assertAlmostEqual(report["jacocoCoverage"], 80.0, places=1)

    def test_gradle_stale_reports_are_cleaned_from_gradle_paths_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            stale_dir = project_dir / "build" / "test-results" / "test"
            stale_dir.mkdir(parents=True)
            (stale_dir / "TEST-com.example.service.OldTest.xml").write_text(
                _PASSING_SUREFIRE_XML.replace("TodoServiceTest", "OldTest"), encoding="utf-8"
            )

            job_repository = JobRepository(storage_dir=project_dir / "storage")
            use_case = RunUnitTestsUseCase(
                job_repository, gradle_runner=_FakeGradleRunner(_successful_build_result())
            )
            report = use_case.execute("job_gradle_stale", project_dir, _empty_inventory(), build_tool="GRADLE")

        self.assertFalse(stale_dir.exists())
        self.assertFalse(report["testExecutionAvailable"])


class CoverageStatusTests(unittest.TestCase):
    def test_missing_jacoco_report_is_reported_as_missing_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            job_repository = JobRepository(storage_dir=project_dir / "storage")
            use_case = RunUnitTestsUseCase(job_repository, _FakeMavenRunner(_successful_build_result()))
            report = use_case.execute("job_no_coverage", project_dir, _empty_inventory())

        self.assertEqual(report["coverageStatus"], COVERAGE_STATUS_MISSING)
        self.assertIsNone(report["jacocoCoverage"])
        self.assertIsNone(report["businessLogicCoverage"])
        self.assertIsNone(report["coverage"]["jacocoLineCoverage"])

    def test_valid_jacoco_report_is_reported_with_real_percentages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            job_repository = JobRepository(storage_dir=project_dir / "storage")
            runner = _FakeMavenRunner(_successful_build_result(), jacoco_xml=_JACOCO_XML)
            use_case = RunUnitTestsUseCase(job_repository, runner)
            report = use_case.execute("job_coverage", project_dir, _empty_inventory())

        self.assertEqual(report["coverageStatus"], COVERAGE_STATUS_GENERATED)
        self.assertAlmostEqual(report["jacocoCoverage"], 80.0, places=1)


if __name__ == "__main__":
    unittest.main()
