"""Scores a :class:`ModuleChunk` for microservice eligibility.

Two scoring rubrics (matching the product's flowchart step "9-11. Run
Chunk-Level Eligibility Analysis"):

* **Option 1 - With Database** (chunk owns a repository): Business Domain
  Clarity, Database Boundary Ownership, Coupling with Other Modules and API
  Independence, each weighted 25%.
* **Option 2 - No Database** (chunk owns no repository): Business Cohesion
  (50%), Coupling with Other Modules (30%), API Independence (20%).

Every input (cohesion %, coupling %, isolation) is computed from the real
dependency graph produced by :mod:`java_class_scanner`/:mod:`chunk_builder` —
nothing here is a fixed or sampled value.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.analyzers.microservice.chunk_builder import ModuleChunk
from app.infrastructure.analyzers.microservice.java_class_scanner import JavaClassInfo


def label_for_score(score: float) -> str:
    if score >= 81:
        return "Highly Suitable"
    if score >= 70:
        return "Good Candidate"
    if score >= 51:
        return "Refactor Required"
    return "Not Suitable"


@dataclass(frozen=True)
class ScoredChunk:
    chunk: ModuleChunk
    score: int
    label: str
    criteria_option: str
    reason: str
    criteria: list[dict]

    def to_dict(self) -> dict:
        return {
            "chunk_name": self.chunk.chunk_name,
            "controller": self.chunk.controller.class_name,
            "services": [c.class_name for c in self.chunk.services],
            "entities": [c.class_name for c in self.chunk.entities],
            "repositories": [c.class_name for c in self.chunk.repositories],
            "score": self.score,
            "label": self.label,
            "criteria_option": self.criteria_option,
            "reason": self.reason,
            "criteria": self.criteria,
        }


def score_chunk(chunk: ModuleChunk, all_classes_by_name: dict[str, JavaClassInfo]) -> ScoredChunk:
    members = chunk.member_names
    supporting_members = [*chunk.services, *chunk.repositories, *chunk.entities]

    internal_edges = 0
    external_edges = 0
    for cls in chunk.all_members:
        for dep in cls.dependencies:
            if dep == cls.class_name or dep not in all_classes_by_name:
                continue
            if dep in members:
                internal_edges += 1
            else:
                external_edges += 1

    total_edges = internal_edges + external_edges
    coupling_score = round(100 * internal_edges / total_edges) if total_edges else 100

    if supporting_members:
        base = chunk.base_name.lower()
        matches = sum(
            1
            for member in supporting_members
            if base in member.class_name.lower() or member.package == chunk.controller.package
        )
        business_clarity = round(100 * matches / len(supporting_members))
        clarity_justification = (
            f"{matches}/{len(supporting_members)} supporting component(s) share the "
            f"'{chunk.base_name}' name or package with {chunk.controller.class_name}."
        )
    else:
        business_clarity = 40
        clarity_justification = (
            f"No supporting services/entities were reachable from {chunk.controller.class_name}'s "
            "dependency graph."
        )

    cross_controller_deps = sum(
        1
        for dep in chunk.controller.dependencies
        if (dep_cls := all_classes_by_name.get(dep)) is not None and dep_cls.class_name.endswith("Controller")
    )
    api_independence = max(0, 100 - 25 * cross_controller_deps)
    api_justification = (
        f"{cross_controller_deps} direct reference(s) from {chunk.controller.class_name} to another controller."
        if cross_controller_deps
        else f"No direct references from {chunk.controller.class_name} to another controller."
    )

    coupling_justification = (
        f"{internal_edges} dependency reference(s) stay within the module vs "
        f"{external_edges} pointing outside it."
    )

    if chunk.repositories:
        shared_repositories = [
            repo
            for repo in chunk.repositories
            if any(
                repo.class_name in other.dependencies
                for name, other in all_classes_by_name.items()
                if name not in members
            )
        ]
        db_score = 100 if not shared_repositories else 55
        db_justification = (
            f"{len(chunk.repositories)} repository(ies) detected; "
            + (
                "none are referenced outside this module."
                if not shared_repositories
                else f"{len(shared_repositories)} of them are also referenced outside this module."
            )
        )

        criteria = [
            {
                "name": "Business Domain Clarity",
                "max_score": 25,
                "score_percent": business_clarity,
                "justification": clarity_justification,
            },
            {
                "name": "Database Boundary Ownership",
                "max_score": 25,
                "score_percent": db_score,
                "justification": db_justification,
            },
            {
                "name": "Coupling with Other Modules",
                "max_score": 25,
                "score_percent": coupling_score,
                "justification": coupling_justification,
            },
            {
                "name": "API Independence",
                "max_score": 25,
                "score_percent": api_independence,
                "justification": api_justification,
            },
        ]
        criteria_option = "OPTION_1"
    else:
        criteria = [
            {
                "name": "Business Cohesion",
                "max_score": 50,
                "score_percent": business_clarity,
                "justification": clarity_justification,
            },
            {
                "name": "Coupling with Other Modules",
                "max_score": 30,
                "score_percent": coupling_score,
                "justification": coupling_justification,
            },
            {
                "name": "API Independence",
                "max_score": 20,
                "score_percent": api_independence,
                "justification": api_justification,
            },
        ]
        criteria_option = "OPTION_2"

    overall = round(sum(c["score_percent"] * c["max_score"] for c in criteria) / 100)
    label = label_for_score(overall)
    reason = (
        f"{chunk.chunk_name} combines 1 controller, {len(chunk.services)} service(s), "
        f"{len(chunk.entities)} entity(ies) and {len(chunk.repositories)} repository(ies) "
        f"with {coupling_score}% internal cohesion."
    )

    return ScoredChunk(
        chunk=chunk,
        score=overall,
        label=label,
        criteria_option=criteria_option,
        reason=reason,
        criteria=criteria,
    )
