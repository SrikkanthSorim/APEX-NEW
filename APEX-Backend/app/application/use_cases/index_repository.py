"""Index (or re-index) a repository's discovery report into the vector store.

Turns a ``discovery-report.json`` into semantic chunks, embeds them, and upserts
them into the shared Qdrant collection tagged with repository metadata. Re-index
first deletes the repository's existing points so stale chunks never linger.

All work here is synchronous/CPU-bound (embedding, embedded Qdrant); async
callers should invoke via ``run_in_threadpool``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.infrastructure.rag import chunker, embedder, repo_index_locator, vector_store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexOutcome:
    repository_url: str
    repository_name: str | None
    job_id: str | None
    chunk_count: int


class RepositoryNotFoundForIndexingError(Exception):
    """No discovery report could be located for the given job id / repo url."""


class IndexRepositoryUseCase:
    def index_report(self, report: dict[str, Any]) -> IndexOutcome:
        """Index an already-loaded discovery report dict."""
        repo_url = str(report.get("repoUrl") or "").strip()
        if not repo_url:
            raise RepositoryNotFoundForIndexingError("Discovery report has no repository URL.")

        chunks = chunker.build_chunks(report)

        # Also index the post-migration outcome (modified files, code changes,
        # dependency upgrades) when a migration report exists for this job, so
        # the chatbot can answer questions about what the migration changed.
        job_id = str(report.get("jobId") or "").strip()
        if job_id:
            migration_report = repo_index_locator.find_migration_report_by_job_id(job_id)
            if migration_report:
                chunks = chunks + chunker.build_migration_chunks(migration_report)

        texts = [c.text for c in chunks]
        vectors = embedder.embed_documents(texts)

        base_metadata = {
            "repository_url": repo_url,
            "repository_name": report.get("repoName"),
            "branch": report.get("defaultBranch"),
            "project_type": report.get("projectType"),
            "java_version": report.get("currentJavaVersion"),
            "framework": _primary_framework(report),
            "job_id": report.get("jobId"),
            "analysis_timestamp": report.get("createdAt"),
        }

        payloads = []
        ids = []
        for index, chunk in enumerate(chunks):
            payloads.append(
                {**base_metadata, "chunk_type": chunk.chunk_type, "text": chunk.text}
            )
            ids.append(vector_store.point_id(repo_url, chunk.chunk_type, index))

        # Replace any previous index for this repository.
        vector_store.delete_repository(repo_url)
        vector_store.upsert(vectors, payloads, ids)

        logger.info(
            "Indexed %d knowledge chunks for repository %s (job %s).",
            len(chunks),
            repo_url,
            report.get("jobId"),
        )
        return IndexOutcome(
            repository_url=repo_url,
            repository_name=report.get("repoName"),
            job_id=report.get("jobId"),
            chunk_count=len(chunks),
        )

    def index_by_job_id(self, job_id: str) -> IndexOutcome:
        report = repo_index_locator.find_report_by_job_id(job_id)
        if not report:
            raise RepositoryNotFoundForIndexingError(
                f"No discovery report found for job '{job_id}'."
            )
        return self.index_report(report)

    def index_by_repo_url(self, repo_url: str) -> IndexOutcome:
        report = repo_index_locator.find_latest_report_by_url(repo_url)
        if not report:
            raise RepositoryNotFoundForIndexingError(
                f"No discovery report found for repository '{repo_url}'."
            )
        return self.index_report(report)


def _primary_framework(report: dict[str, Any]) -> str | None:
    if report.get("springBootVersion"):
        return "spring-boot"
    frameworks = report.get("frameworks") or []
    return str(frameworks[0]) if frameworks else None
