"""Parses JaCoCo's ``target/site/jacoco/jacoco.xml`` (never the HTML report)
into real coverage percentages.

Produces two views, per Step 9/10 of the spec:
  * overall project line coverage ("JaCoCo Coverage" card)
  * line coverage restricted to business-logic classes only ("BL Business
    Logic Coverage" card) -- Services/domain/validators/logic-bearing
    utilities/converters, using the class types the OpenRewrite inventory
    scan already computed. DTO-only, entity-only, configuration, and
    generated/interface-only classes are excluded from that figure.

If the report is missing or unparsable, both views report ``available=False``
with a real reason string -- never a fabricated percentage.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, fromstring

from app.domain.models.unit_test_report import CoverageMetrics
from app.infrastructure.testing.build_tool_paths import jacoco_report_path

_COUNTER_TYPES = ("INSTRUCTION", "LINE", "BRANCH", "METHOD", "CLASS")


def parse_jacoco_report(
    project_dir: Path, business_logic_qualified_names: set[str] | None = None, build_tool: str = "MAVEN"
) -> tuple[CoverageMetrics, CoverageMetrics]:
    """Return ``(overall, business_logic_only)`` coverage for one JaCoCo XML report."""
    xml_path = jacoco_report_path(project_dir, build_tool)
    if not xml_path.is_file():
        unavailable = CoverageMetrics(
            available=False,
            reason=f"JaCoCo XML report not found at {xml_path.relative_to(project_dir)}.",
        )
        return unavailable, unavailable

    text = xml_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        unavailable = CoverageMetrics(available=False, reason="JaCoCo XML report was empty.")
        return unavailable, unavailable

    # Strip the <!DOCTYPE ...> preamble jacoco.xml always includes -- some
    # XML parser configurations choke trying to resolve its external DTD
    # reference even though nothing in the document actually needs it.
    start = text.find("<report")
    if start == -1:
        unavailable = CoverageMetrics(available=False, reason="JaCoCo XML report was malformed (no <report> root).")
        return unavailable, unavailable
    try:
        root = fromstring(text[start:])
    except ParseError as exc:
        unavailable = CoverageMetrics(available=False, reason=f"JaCoCo XML report could not be parsed: {exc}")
        return unavailable, unavailable

    overall = _metrics_from_counters(root.findall("counter"))

    if not business_logic_qualified_names:
        return overall, CoverageMetrics(
            available=False, reason="No business-logic classes were identified for this project."
        )

    bl_covered = bl_missed = 0
    matched_any = False
    for package in root.findall("package"):
        for class_el in package.findall("class"):
            fqcn = (class_el.get("name") or "").replace("/", ".")
            if fqcn not in business_logic_qualified_names:
                continue
            matched_any = True
            missed, covered = _counter_values(class_el, "LINE")
            bl_missed += missed
            bl_covered += covered

    if not matched_any or (bl_covered + bl_missed) == 0:
        bl_metrics = CoverageMetrics(
            available=False,
            reason="None of the identified business-logic classes appear in the coverage report.",
        )
    else:
        total = bl_covered + bl_missed
        bl_metrics = CoverageMetrics(
            available=True,
            line_coverage_pct=round(bl_covered / total * 100, 1),
            lines_covered=bl_covered,
            lines_missed=bl_missed,
        )
    return overall, bl_metrics


def _metrics_from_counters(counters: list[Element]) -> CoverageMetrics:
    by_type = {c.get("type"): (_to_int(c.get("missed")), _to_int(c.get("covered"))) for c in counters}
    if "LINE" not in by_type:
        return CoverageMetrics(available=False, reason="JaCoCo report contained no LINE counter.")

    def pct(counter_type: str) -> float | None:
        if counter_type not in by_type:
            return None
        missed, covered = by_type[counter_type]
        total = missed + covered
        return round(covered / total * 100, 1) if total else None

    line_missed, line_covered = by_type["LINE"]
    return CoverageMetrics(
        available=True,
        instruction_coverage_pct=pct("INSTRUCTION"),
        line_coverage_pct=pct("LINE"),
        branch_coverage_pct=pct("BRANCH"),
        method_coverage_pct=pct("METHOD"),
        class_coverage_pct=pct("CLASS"),
        lines_covered=line_covered,
        lines_missed=line_missed,
    )


def _counter_values(class_el: Element, counter_type: str) -> tuple[int, int]:
    for counter in class_el.findall("counter"):
        if counter.get("type") == counter_type:
            return _to_int(counter.get("missed")), _to_int(counter.get("covered"))
    return 0, 0


def _to_int(value: str | None) -> int:
    try:
        return int(value) if value else 0
    except ValueError:
        return 0
