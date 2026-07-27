import unittest

from app.application.services.unit_test_report_service import build_report_overlay


class UnitTestReportServiceTests(unittest.TestCase):
    def test_no_report_returns_empty_overlay(self) -> None:
        self.assertEqual(build_report_overlay(None), {})
        self.assertEqual(build_report_overlay({}), {})

    def test_overlay_shapes_real_report_into_frontend_contract(self) -> None:
        report = {
            "status": "COMPLETED_WITH_ISSUES",
            "llmModel": "meta-llama/Llama-3.1-8B-Instruct:novita",
            "llmProvider": "huggingface",
            "summary": {
                "totalSourceFiles": 46,
                "existingTestFiles": 5,
                "newTestFiles": 8,
                "existingTestCases": 21,
                "generatedTestCases": 24,
                "totalTestCases": 45,
                "passedTests": 43,
                "failedTests": 2,
                "skippedTests": 0,
            },
            "coverage": {
                "businessLogicLineCoverage": 78.4,
                "jacocoLineCoverage": 71.2,
                "branchCoverage": 63.8,
                "jacocoCoverageAvailable": True,
            },
            "generatedFiles": [
                {"className": "UserServiceTest", "path": "src/test/java/.../UserServiceTest.java", "testCount": 3, "status": "PASSED"},
            ],
            "failures": [
                {"testClass": "PaymentServiceTest", "testMethod": "processPayment_shouldFail", "type": "TEST_FAILURE", "reason": "Expected exception was not thrown"},
            ],
            "inventory": {
                "testClasses": [{"sourcePath": "src/test/java/.../ExistingTest.java"}],
            },
        }

        overlay = build_report_overlay(report)

        self.assertEqual(overlay["tests_run"], 45)
        self.assertEqual(overlay["tests_passed"], 43)
        self.assertEqual(overlay["tests_failed"], 2)
        self.assertEqual(overlay["bl_coverage"], 78.4)
        self.assertEqual(overlay["test_llm_model"], "meta-llama/Llama-3.1-8B-Instruct:novita")
        self.assertIn("Unit tests completed with some failures", overlay["test_summary"])
        self.assertEqual(len(overlay["test_insights"]), 1)

        pipeline = overlay["test_pipeline"]
        self.assertEqual(pipeline["test_summary_metrics"]["total_test_cases"], 45)
        self.assertEqual(pipeline["test_summary_metrics"]["generated_test_cases"], 24)
        self.assertEqual(pipeline["coverage_result"]["line_coverage_pct"], 71.2)
        self.assertTrue(pipeline["coverage_result"]["available"])
        self.assertEqual(pipeline["generated_test_files"], ["src/test/java/.../UserServiceTest.java"])
        self.assertEqual(pipeline["existing_test_files"], ["src/test/java/.../ExistingTest.java"])

    def test_no_fabricated_coverage_when_unavailable(self) -> None:
        report = {
            "status": "TEST_NOT_EXECUTED",
            "summary": {},
            "coverage": {
                "businessLogicLineCoverage": None,
                "jacocoLineCoverage": None,
                "jacocoCoverageAvailable": False,
                "jacocoCoverageReason": "JaCoCo XML report not found.",
            },
        }

        overlay = build_report_overlay(report)

        self.assertIsNone(overlay["bl_coverage"])
        self.assertIsNone(overlay["test_pipeline"]["coverage_result"]["line_coverage_pct"])
        self.assertFalse(overlay["test_pipeline"]["coverage_result"]["available"])
        self.assertEqual(
            overlay["test_pipeline"]["coverage_result"]["reason"], "JaCoCo XML report not found."
        )


if __name__ == "__main__":
    unittest.main()
