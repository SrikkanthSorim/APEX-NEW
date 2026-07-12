"""Migration preview compatibility endpoint.

The frontend calls this unversioned route while the user is on the Migration
step. It returns a safe planned-change preview without running the migration.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.migration_execution_schema import MigrationPreviewRequest

router = APIRouter(tags=["migration-preview"])


def _repo_name(request: MigrationPreviewRequest) -> str:
    if request.target_repo_name.strip():
        return request.target_repo_name.strip()
    repo_url = request.source_repo_url.strip().rstrip("/")
    if not repo_url:
        return "repository"
    return repo_url.split("/")[-1].removesuffix(".git") or "repository"


def _conversion_label(conversion: str) -> str:
    normalized = conversion.replace("_", " ").replace("-", " ").strip()
    return normalized.title() if normalized else "Migration Update"


@router.post("/migration/preview", summary="Preview planned migration changes.")
async def preview_migration(payload: MigrationPreviewRequest) -> JSONResponse:
    """Return a frontend-compatible preview for the current migration choices."""
    repository = _repo_name(payload)
    conversions = payload.conversion_types or ["java_version"]

    file_changes: dict[str, list[dict[str, object]]] = {}
    planned_changes: list[dict[str, object]] = []

    if payload.source_java_version or payload.target_java_version:
        planned_changes.append(
            {
                "type": "java_version",
                "pattern": payload.source_java_version or None,
                "replacement": payload.target_java_version or None,
                "description": (
                    f"Plan Java compatibility updates from Java "
                    f"{payload.source_java_version or 'detected source'} to Java "
                    f"{payload.target_java_version or 'selected target'}"
                ),
                "occurrences": 1,
            }
        )

    for conversion in conversions:
        if conversion == "java_version":
            continue
        planned_changes.append(
            {
                "type": conversion,
                "description": f"Apply {_conversion_label(conversion)} migration rules",
                "occurrences": 1,
            }
        )

    if payload.fix_business_logic:
        planned_changes.append(
            {
                "type": "business_logic",
                "description": "Review and apply business-logic-safe compatibility fixes",
                "occurrences": 1,
            }
        )

    if payload.run_tests:
        planned_changes.append(
            {
                "type": "test_validation",
                "description": "Run selected validation tests after migration",
                "occurrences": 1,
            }
        )

    if payload.run_sonar:
        planned_changes.append(
            {
                "type": "quality_gate",
                "description": "Run SonarQube quality gate after build validation",
                "occurrences": 1,
            }
        )

    if payload.run_fossa:
        planned_changes.append(
            {
                "type": "quality_gate",
                "description": "Run FOSSA dependency and license quality gate",
                "occurrences": 1,
            }
        )

    if planned_changes:
        build_file = "pom.xml" if (payload.build_tool or "").lower() == "maven" else "build.gradle"
        file_changes[build_file] = planned_changes

    files_to_modify = list(file_changes.keys())
    response = {
        "repository": repository,
        "platform": payload.platform or "github",
        "source_version": payload.source_java_version,
        "target_version": payload.target_java_version,
        "conversions": conversions,
        "business_logic_fixes": payload.fix_business_logic,
        "summary": {
            "files_to_modify": len(files_to_modify),
            "files_to_create": 0,
            "files_to_remove": 0,
            "total_changes": len(planned_changes),
        },
        "changes": {
            "files_to_modify": files_to_modify,
            "files_to_create": [],
            "files_to_remove": [],
            "file_changes": file_changes,
            "dependencies_to_update": [],
            "issues_to_fix": [],
        },
        "file_diffs": [],
    }
    return JSONResponse(status_code=200, content=response)
