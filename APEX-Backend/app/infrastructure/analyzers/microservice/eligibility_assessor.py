"""Orchestrates the Microservice Eligibility Assessment over a cloned repo.

Pipeline: scan real ``.java`` sources -> classify roles -> group into
per-controller chunks (real dependency graph, not naming guesses) -> score
each chunk against the product's two rubrics -> aggregate + narrate. The
returned dict matches the shape the Discovery page's
``MicroserviceAssessment`` component already renders.
"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.analyzers.microservice import narrative_builder
from app.infrastructure.analyzers.microservice.chunk_builder import build_chunks, classify_role
from app.infrastructure.analyzers.microservice.chunk_scorer import ScoredChunk, label_for_score, score_chunk
from app.infrastructure.analyzers.microservice.java_class_scanner import JavaClassScanner


class MicroserviceEligibilityAssessor:
    def __init__(self, scanner: JavaClassScanner | None = None) -> None:
        self._scanner = scanner or JavaClassScanner()

    def assess(self, repo_root: Path, project_name: str = "Repository") -> dict:
        classes = self._scanner.scan(repo_root)
        by_name = {cls.class_name: cls for cls in classes}
        roles = {cls.class_name: classify_role(cls) for cls in classes}

        controllers_count = sum(1 for role in roles.values() if role == "controller")
        services_count = sum(1 for role in roles.values() if role == "service")
        repositories_count = sum(1 for role in roles.values() if role == "repository")
        entities_count = sum(1 for role in roles.values() if role == "entity")

        chunks = build_chunks(classes)
        scored_chunks: list[ScoredChunk] = [score_chunk(chunk, by_name) for chunk in chunks]

        total_chunks = len(scored_chunks)
        eligible_chunks = sum(1 for c in scored_chunks if c.score >= 70)
        refactor_chunks = sum(1 for c in scored_chunks if 51 <= c.score < 70)
        not_suitable_chunks = sum(1 for c in scored_chunks if c.score < 51)

        weights = [len(c.chunk.all_members) or 1 for c in scored_chunks]
        total_weight = sum(weights)
        overall_score = (
            round(sum(c.score * w for c, w in zip(scored_chunks, weights)) / total_weight)
            if total_weight
            else 0
        )
        eligible_chunk_ratio = round(100 * eligible_chunks / total_chunks) if total_chunks else 0

        chunk_summary = {
            "total_chunks": total_chunks,
            "eligible_chunks": eligible_chunks,
            "refactor_chunks": refactor_chunks,
            "not_suitable_chunks": not_suitable_chunks,
            "eligible_chunk_ratio": eligible_chunk_ratio,
            "overall_weighted_score": overall_score,
            "scoring_method": "Weighted Score (by component count)",
        }

        eligibility_label = label_for_score(overall_score) if total_chunks else "Not Suitable"
        eligible = overall_score >= 70

        benefits, risks = ([], [])
        changes_needed: list[dict] = []
        not_recommended_reasons: list[dict] = []
        if scored_chunks:
            if eligible:
                benefits, risks = narrative_builder.build_benefits_and_risks(
                    scored_chunks, len(classes), repositories_count
                )
            elif overall_score >= 51:
                changes_needed = narrative_builder.build_changes_needed(scored_chunks)
            else:
                not_recommended_reasons = narrative_builder.build_not_recommended_reasons(
                    scored_chunks, total_chunks
                )

        suggested_services = narrative_builder.build_suggested_services(scored_chunks)
        folder_structure = narrative_builder.build_folder_structure(scored_chunks)
        reasoning = narrative_builder.build_reasoning(overall_score, total_chunks, eligible_chunks, scored_chunks)

        return {
            "projectName": project_name,
            "project_name": project_name,
            "score": overall_score,
            "eligibility": eligibility_label,
            "eligibility_label": eligibility_label,
            "eligible": eligible,
            "recommendedArchitecture": "Microservices" if eligible else "Modular Monolith",
            "reasoning": reasoning,
            "summary": reasoning,
            "criteria_option": "OPTION_1_WITH_DATABASE" if repositories_count else "OPTION_2_NO_DATABASE",
            "java_files_count": len(classes),
            "controllers_count": controllers_count,
            "services_count": services_count,
            "entities_count": entities_count,
            "repositories_count": repositories_count,
            "chunk_results": [c.to_dict() for c in scored_chunks],
            "chunk_summary": chunk_summary,
            "benefits_if_converted": benefits,
            "risks_if_not_converted": risks,
            "changes_needed": changes_needed,
            "not_recommended_reasons": not_recommended_reasons,
            "suggested_services": suggested_services,
            "folder_structure": folder_structure,
            "strengths": [b["title"] for b in benefits],
            "risks": [r["title"] for r in risks],
            "observations": [c.reason for c in scored_chunks],
            "reportGeneratedAt": None,
        }
