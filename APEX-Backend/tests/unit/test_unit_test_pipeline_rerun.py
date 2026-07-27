"""Scenario: Re-run Tests must never regenerate or duplicate test files --
only analyze() (inventory rescan) + run() (execute), never generate()."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.application.pipelines.unit_test_pipeline import UnitTestPipeline
from app.application.services.status_service import MigrationReportStore
from app.application.use_cases.generate_unit_tests import GenerationResult
from app.core.config import settings
from app.domain.enums.unit_test_status import (
    GENERATION_STATUS_NO_CANDIDATES,
    UnitTestStatus,
)
from app.infrastructure.persistence.job_repository import JobRepository
from app.infrastructure.workspace.workspace_paths import WorkspacePaths


class RerunNeverRegeneratesTests(unittest.TestCase):
    def test_rerun_calls_analyze_and_run_but_never_generate(self) -> None:
        job_id = "job_rerun_test"
        with tempfile.TemporaryDirectory() as tmp:
            storage_dir = Path(tmp)
            original_storage_dir = settings.storage_dir
            settings.storage_dir = storage_dir
            try:
                paths = WorkspacePaths(job_id, storage_dir=storage_dir)
                paths.migrated_repo_dir.mkdir(parents=True)
                MigrationReportStore(paths).write({
                    "jobId": job_id, "buildTool": "MAVEN", "targetJavaVersion": "17",
                })

                job_repository = JobRepository(storage_dir=storage_dir)
                job_repository.save_unit_test_report(job_id, {
                    "jobId": job_id, "inventory": {
                        "projectDir": str(paths.migrated_repo_dir),
                        "productionFileCount": 1, "testFileCount": 1,
                        "productionClasses": [], "testClasses": [], "parseErrors": [],
                    },
                })

                analyze_mock = MagicMock()
                analyze_mock.execute.return_value = {
                    "inventory": {
                        "projectDir": str(paths.migrated_repo_dir),
                        "productionFileCount": 1, "testFileCount": 1,
                        "productionClasses": [], "testClasses": [], "parseErrors": [],
                    }
                }
                generate_mock = MagicMock()
                generate_mock.execute.side_effect = AssertionError(
                    "generate() must never be called by rerun()"
                )
                run_mock = MagicMock()
                run_mock.execute.return_value = {"jobId": job_id, "status": "COMPLETED", "summary": {}}

                pipeline = UnitTestPipeline(
                    job_repository=job_repository,
                    analyze_use_case=analyze_mock,
                    generate_use_case=generate_mock,
                    run_use_case=run_mock,
                )

                result = pipeline.rerun(job_id)
            finally:
                settings.storage_dir = original_storage_dir

        analyze_mock.execute.assert_called_once()
        run_mock.execute.assert_called_once()
        generate_mock.execute.assert_not_called()
        self.assertEqual(result["status"], "COMPLETED")


class GenerateStatusTests(unittest.TestCase):
    def test_generate_marks_report_in_progress_before_llm_generation(self) -> None:
        job_id = "job_generation_status_test"
        with tempfile.TemporaryDirectory() as tmp:
            storage_dir = Path(tmp)
            original_storage_dir = settings.storage_dir
            settings.storage_dir = storage_dir
            try:
                paths = WorkspacePaths(job_id, storage_dir=storage_dir)
                paths.migrated_repo_dir.mkdir(parents=True)
                MigrationReportStore(paths).write({
                    "jobId": job_id, "buildTool": "MAVEN", "targetJavaVersion": "17",
                })

                job_repository = JobRepository(storage_dir=storage_dir)
                inventory = {
                    "projectDir": str(paths.migrated_repo_dir),
                    "productionFileCount": 1,
                    "testFileCount": 1,
                    "productionClasses": [],
                    "testClasses": [],
                    "parseErrors": [],
                }

                analyze_mock = MagicMock()
                analyze_mock.execute.return_value = {
                    "jobId": job_id,
                    "status": UnitTestStatus.TEST_ANALYSIS_COMPLETED.value,
                    "inventory": inventory,
                    "summary": {"existingTestFiles": 1, "existingTestCases": 1},
                }

                def generate_side_effect(*args, **kwargs):
                    saved = job_repository.read_unit_test_report(job_id) or {}
                    self.assertEqual(
                        saved.get("status"),
                        UnitTestStatus.TEST_GENERATION_IN_PROGRESS.value,
                    )
                    self.assertIsNone(saved.get("completedAt"))
                    return GenerationResult(generation_status=GENERATION_STATUS_NO_CANDIDATES)

                generate_mock = MagicMock()
                generate_mock.execute.side_effect = generate_side_effect
                run_mock = MagicMock()

                pipeline = UnitTestPipeline(
                    job_repository=job_repository,
                    analyze_use_case=analyze_mock,
                    generate_use_case=generate_mock,
                    run_use_case=run_mock,
                )

                result = pipeline.generate(job_id)
            finally:
                settings.storage_dir = original_storage_dir

        generate_mock.execute.assert_called_once()
        run_mock.execute.assert_not_called()
        self.assertEqual(result["generationStatus"], GENERATION_STATUS_NO_CANDIDATES)
        self.assertEqual(result["status"], UnitTestStatus.TEST_ANALYSIS_COMPLETED.value)


if __name__ == "__main__":
    unittest.main()
