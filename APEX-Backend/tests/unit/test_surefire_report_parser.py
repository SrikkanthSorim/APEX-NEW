import tempfile
import unittest
from pathlib import Path

from app.infrastructure.testing.surefire_report_parser import (
    parse_surefire_report_for_class,
    parse_surefire_reports,
)

_PASSING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.service.UserServiceTest" tests="1" failures="0" errors="0" skipped="0" time="0.05">
  <testcase name="createsUser" classname="com.example.service.UserServiceTest" time="0.05"/>
</testsuite>
"""

_MIXED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.service.OrderServiceTest" tests="3" failures="1" errors="1" skipped="1" time="0.2">
  <testcase name="passes" classname="com.example.service.OrderServiceTest" time="0.05"/>
  <testcase name="fails" classname="com.example.service.OrderServiceTest" time="0.05">
    <failure message="expected [1] but was [2]" type="org.opentest4j.AssertionFailedError">stack...</failure>
  </testcase>
  <testcase name="errors" classname="com.example.service.OrderServiceTest" time="0.05">
    <error message="NullPointerException" type="java.lang.NullPointerException">stack...</error>
  </testcase>
</testsuite>
"""


class SurefireReportParserTests(unittest.TestCase):
    def test_no_reports_returns_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = parse_surefire_reports(Path(tmp))
        self.assertFalse(summary.available)
        self.assertIsNotNone(summary.reason)

    def test_aggregates_multiple_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp) / "target" / "surefire-reports"
            reports_dir.mkdir(parents=True)
            (reports_dir / "TEST-com.example.service.UserServiceTest.xml").write_text(_PASSING_XML, encoding="utf-8")
            (reports_dir / "TEST-com.example.service.OrderServiceTest.xml").write_text(_MIXED_XML, encoding="utf-8")

            summary = parse_surefire_reports(Path(tmp))

        self.assertTrue(summary.available)
        self.assertEqual(summary.total, 4)
        self.assertEqual(summary.passed, 2)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(len(summary.failures), 2)
        reasons = {f.reason for f in summary.failures}
        self.assertIn("expected [1] but was [2]", reasons)
        self.assertIn("NullPointerException", reasons)

    def test_single_class_report_missing_means_did_not_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = parse_surefire_report_for_class(Path(tmp), "com.example.service.UserServiceTest")
        self.assertFalse(summary.available)

    def test_single_class_report_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp) / "target" / "surefire-reports"
            reports_dir.mkdir(parents=True)
            (reports_dir / "TEST-com.example.service.UserServiceTest.xml").write_text(_PASSING_XML, encoding="utf-8")

            summary = parse_surefire_report_for_class(Path(tmp), "com.example.service.UserServiceTest")

        self.assertTrue(summary.available)
        self.assertEqual(summary.total, 1)
        self.assertEqual(summary.passed, 1)


if __name__ == "__main__":
    unittest.main()
