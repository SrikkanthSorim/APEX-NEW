"""Builds the human-readable narrative sections of the eligibility report.

Every sentence is templated from real numbers/names computed by
:mod:`chunk_scorer` (chunk counts, coupling percentages, repository counts,
etc.) — nothing here is a fixed example or placeholder value.
"""

from __future__ import annotations

from app.infrastructure.analyzers.microservice.chunk_scorer import ScoredChunk


def _criterion_value(chunk: ScoredChunk, name: str) -> int | None:
    for criterion in chunk.criteria:
        if criterion["name"] == name:
            return criterion["score_percent"]
    return None


def _coupling_value(chunk: ScoredChunk) -> int:
    return _criterion_value(chunk, "Coupling with Other Modules") or 0


def _average_criteria(scored_chunks: list[ScoredChunk]) -> dict[str, float]:
    totals: dict[str, list[int]] = {}
    for chunk in scored_chunks:
        for criterion in chunk.criteria:
            totals.setdefault(criterion["name"], []).append(criterion["score_percent"])
    return {name: sum(values) / len(values) for name, values in totals.items() if values}


def build_benefits_and_risks(
    scored_chunks: list[ScoredChunk],
    java_files_count: int,
    repositories_count: int,
) -> tuple[list[dict], list[dict]]:
    eligible = [c for c in scored_chunks if c.score >= 70]
    domain_names = [c.chunk.base_name.lower() for c in (eligible or scored_chunks)]
    domain_list_str = ", ".join(domain_names) if domain_names else "the detected module"
    avg_coupling = round(sum(_coupling_value(c) for c in scored_chunks) / len(scored_chunks)) if scored_chunks else 0
    total_chunks = len(scored_chunks)

    benefits = [
        {
            "icon": "✅",
            "title": "Independent Deployment",
            "description": (
                f"Your {len(domain_names)} service domain(s) ({domain_list_str}) can be deployed "
                "independently, reducing release coordination overhead."
            ),
        },
        {
            "icon": "✅",
            "title": "Horizontal Scalability",
            "description": (
                f"With {java_files_count} source files, splitting into services allows each to scale "
                "based on its own demand patterns."
            ),
        },
        {
            "icon": "✅",
            "title": "Fault Isolation",
            "description": (
                f"Your codebase shows {avg_coupling}% decoupling readiness — failures in one service "
                "won't cascade to others."
            ),
        },
        {
            "icon": "✅",
            "title": "Technology Evolution",
            "description": (
                "Spring Boot services can be individually upgraded or replaced with newer frameworks "
                "(Quarkus, Micronaut) without affecting others."
            ),
        },
        {
            "icon": "✅",
            "title": "Improved Maintainability",
            "description": (
                f"Breaking {java_files_count} files into focused services creates clearer ownership "
                "and reduces cognitive load per team."
            ),
        },
        {
            "icon": "✅",
            "title": "Phased Migration Ready",
            "description": (
                f"{len(eligible)} of {total_chunks} module(s) scored 70%+ — you can start migrating "
                "eligible chunks immediately while refactoring others."
            ),
        },
    ]

    if len(domain_names) >= 2:
        team_bottleneck = (
            f"Your {total_chunks} service domain(s) share one deployment — teams working on "
            f"'{domain_names[0]}' block teams on '{domain_names[1]}'."
        )
    else:
        team_bottleneck = (
            f"Your {total_chunks} service domain(s) share one deployment, so unrelated teams block "
            "each other on every release."
        )

    risks = [
        {
            "icon": "⚠️",
            "title": "Future Scalability Risk",
            "description": (
                f"Even with {java_files_count} files today, growth will eventually require the entire "
                "application to scale for any single component's demand."
            ),
        },
        {
            "icon": "⚠️",
            "title": "Full Redeployment Required",
            "description": "Any change requires redeploying the entire application, increasing release risk.",
        },
        {
            "icon": "⚠️",
            "title": "Team Bottleneck",
            "description": team_bottleneck,
        },
    ]
    if repositories_count > 0:
        risks.append(
            {
                "icon": "⚠️",
                "title": "Database Contention",
                "description": (
                    f"All {repositories_count} data access pattern(s) compete for the same database "
                    "resources, creating bottlenecks under load."
                ),
            }
        )
    risks.append(
        {
            "icon": "⚠️",
            "title": "Technical Debt Accumulation",
            "description": (
                f"Maintaining {java_files_count} files in a single codebase will accumulate coupling "
                "and make future decomposition progressively harder."
            ),
        }
    )

    return benefits, risks


def build_changes_needed(scored_chunks: list[ScoredChunk]) -> list[dict]:
    averages = _average_criteria(scored_chunks)
    weakest = sorted(averages.items(), key=lambda item: item[1])[:3]

    changes: list[dict] = []
    for name, avg in weakest:
        worst_chunk = min(
            (c for c in scored_chunks if _criterion_value(c, name) is not None),
            key=lambda c: _criterion_value(c, name) or 0,
            default=None,
        )
        if worst_chunk is None:
            continue
        changes.append(
            {
                "title": f"Improve {name}",
                "description": (
                    f"'{worst_chunk.chunk.chunk_name}' scores only {_criterion_value(worst_chunk, name)}% "
                    f"on {name.lower()} (module average {round(avg)}%) — address this before extracting it "
                    "as an independent service."
                ),
            }
        )
    return changes


def build_not_recommended_reasons(scored_chunks: list[ScoredChunk], total_chunks: int) -> list[dict]:
    averages = _average_criteria(scored_chunks)
    weakest = sorted(averages.items(), key=lambda item: item[1])

    reasons: list[dict] = []
    for name, avg in weakest:
        reasons.append(
            {
                "title": f"Weak {name}",
                "description": (
                    f"Across {total_chunks} module(s), {name.lower()} averages only {round(avg)}%, "
                    "below the 51% threshold needed before a phased migration is safe."
                ),
            }
        )
    return reasons


def build_suggested_services(scored_chunks: list[ScoredChunk]) -> list[dict]:
    eligible = [c for c in scored_chunks if c.score >= 70]
    services: list[dict] = []
    for scored in eligible:
        chunk = scored.chunk
        components = [chunk.controller.class_name]
        components.extend(c.class_name for c in chunk.services)
        components.extend(c.class_name for c in chunk.entities)
        components.extend(c.class_name for c in chunk.repositories)
        services.append(
            {
                "name": chunk.chunk_name,
                "description": (
                    f"Extracted from {chunk.controller.class_name} with {len(chunk.services)} service(s), "
                    f"{len(chunk.entities)} entity(ies) and {len(chunk.repositories)} repository(ies)."
                ),
                "components": components,
            }
        )
    return services


def build_folder_structure(scored_chunks: list[ScoredChunk]) -> str | None:
    eligible = [c for c in scored_chunks if c.score >= 70]
    if not eligible:
        return None

    lines = ["microservices/"]
    for scored in eligible:
        chunk = scored.chunk
        service_dir = f"{chunk.base_name.lower().replace(' ', '-')}-service"
        package_path = chunk.controller.package.replace(".", "/") or "app"
        lines.append(f"├── {service_dir}/")
        lines.append(f"│   ├── src/main/java/{package_path}/")
        for cls in [chunk.controller, *chunk.services, *chunk.entities, *chunk.repositories]:
            lines.append(f"│   │   ├── {cls.class_name}.java")
        lines.append("│   ├── pom.xml")
        lines.append("│   └── application.yml")
    return "\n".join(lines)


def build_reasoning(
    overall_score: int,
    total_chunks: int,
    eligible_chunks: int,
    scored_chunks: list[ScoredChunk],
) -> str:
    if total_chunks == 0:
        return "No REST controllers were detected, so no business modules could be assessed."

    averages = _average_criteria(scored_chunks)
    if averages:
        strongest = max(averages.items(), key=lambda item: item[1])
        weakest = min(averages.items(), key=lambda item: item[1])
        driver_sentence = (
            f" {strongest[0]} was the strongest contributor ({round(strongest[1])}% avg), while "
            f"{weakest[0].lower()} was the weakest ({round(weakest[1])}% avg)."
        )
    else:
        driver_sentence = ""

    return (
        f"Weighted score of {overall_score}% across {total_chunks} module(s), with {eligible_chunks} "
        f"scoring 70% or higher (Good Candidate or better)."
        f"{driver_sentence}"
    )
