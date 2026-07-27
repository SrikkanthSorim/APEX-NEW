import tempfile
import unittest
from pathlib import Path

from app.infrastructure.testing.jacoco_report_parser import parse_jacoco_report

_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="sample-project">
  <package name="com/example/service">
    <class name="com/example/service/UserService">
      <counter type="INSTRUCTION" missed="10" covered="20"/>
      <counter type="LINE" missed="4" covered="6"/>
      <counter type="BRANCH" missed="1" covered="1"/>
      <counter type="METHOD" missed="1" covered="2"/>
      <counter type="CLASS" missed="0" covered="1"/>
    </class>
    <class name="com/example/service/UserDto">
      <counter type="INSTRUCTION" missed="0" covered="5"/>
      <counter type="LINE" missed="0" covered="3"/>
      <counter type="BRANCH" missed="0" covered="0"/>
      <counter type="METHOD" missed="0" covered="2"/>
      <counter type="CLASS" missed="0" covered="1"/>
    </class>
  </package>
  <counter type="INSTRUCTION" missed="10" covered="25"/>
  <counter type="LINE" missed="4" covered="9"/>
  <counter type="BRANCH" missed="1" covered="1"/>
  <counter type="METHOD" missed="1" covered="4"/>
  <counter type="CLASS" missed="0" covered="2"/>
</report>
"""


class JacocoReportParserTests(unittest.TestCase):
    def test_missing_report_is_unavailable_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            overall, bl = parse_jacoco_report(Path(tmp))
        self.assertFalse(overall.available)
        self.assertIsNotNone(overall.reason)
        self.assertFalse(bl.available)

    def test_empty_report_is_unavailable_with_clear_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").write_text("", encoding="utf-8")

            overall, bl = parse_jacoco_report(Path(tmp))

        self.assertFalse(overall.available)
        self.assertEqual(overall.reason, "JaCoCo XML report was empty.")
        self.assertFalse(bl.available)

    def test_parses_overall_and_business_logic_only_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").write_text(_JACOCO_XML, encoding="utf-8")

            overall, bl = parse_jacoco_report(Path(tmp), {"com.example.service.UserService"})

        self.assertTrue(overall.available)
        # overall LINE: covered=9, missed=4 -> 9/13 = 69.2%
        self.assertAlmostEqual(overall.line_coverage_pct, 69.2, places=1)
        self.assertEqual(overall.lines_covered, 9)
        self.assertEqual(overall.lines_missed, 4)

        self.assertTrue(bl.available)
        # BL-only (UserService) LINE: covered=6, missed=4 -> 60.0%
        self.assertAlmostEqual(bl.line_coverage_pct, 60.0, places=1)
        self.assertEqual(bl.lines_covered, 6)
        self.assertEqual(bl.lines_missed, 4)

    def test_no_business_logic_classes_given_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").write_text(_JACOCO_XML, encoding="utf-8")

            _, bl = parse_jacoco_report(Path(tmp), set())

        self.assertFalse(bl.available)

    def test_business_logic_classes_not_in_report_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").write_text(_JACOCO_XML, encoding="utf-8")

            _, bl = parse_jacoco_report(Path(tmp), {"com.example.other.NotInReport"})

        self.assertFalse(bl.available)


if __name__ == "__main__":
    unittest.main()
