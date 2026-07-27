"""Prompt builders for LLM-backed features."""

from __future__ import annotations

from typing import Any

from app.domain.models.unit_test_report import ClassInventoryEntry

JAVA_VERSION_RECOMMENDATION_SYSTEM_PROMPT = """You are a senior Java platform engineer advising on JDK upgrade strategy \
for enterprise Spring/Java applications. You always answer with a single, strict \
JSON object and nothing else - no markdown fences, no commentary outside the JSON.

The JSON object must have exactly these keys:
- "recommended_target_version": string, one of the allowed target versions given by the user.
- "confidence": string, one of "High", "Medium", "Low".
- "rationale": array of 2-4 short strings explaining WHY that version is the right target.
- "benefits": array of 2-5 short strings describing concrete upgrade benefits (performance, \
language features, security, tooling, long-term support, etc).
- "compatibility_considerations": array of 1-4 short strings describing real compatibility risks \
or migration considerations for this specific jump (e.g. removed APIs, dependency upgrades needed, \
framework version requirements).
- "alternative_options": array of objects (possibly empty) for the OTHER allowed target versions, \
each with "version" (string), "risk" (short string: "Low"/"Medium"/"High"), and "reason" (short string \
explaining when someone would pick this instead).

Only recommend a version from the allowed target list you are given - never the current/source version, \
and never a version outside that list."""


def build_java_version_recommendation_prompt(
    *,
    source_java_version: str,
    build_tool: str | None,
    dependencies: list[dict[str, Any]],
    has_tests: bool,
    api_endpoint_count: int,
    risk_level: str | None,
    allowed_target_versions: list[str],
    already_at_latest: bool,
) -> str:
    dependency_lines = [
        f"- {dep.get('artifact_id') or dep.get('artifactId') or 'unknown'}"
        f" ({dep.get('group_id') or dep.get('groupId') or 'unknown'})"
        f" {dep.get('current_version') or dep.get('version') or ''}".strip()
        for dep in dependencies[:25]
        if isinstance(dep, dict)
    ]
    dependency_block = "\n".join(dependency_lines) if dependency_lines else "No dependencies detected."

    situation = (
        f"This project is already on Java {source_java_version}, the newest version this platform "
        "currently supports recommending. There is no higher version to move to - recommend staying "
        f"on Java {source_java_version} and explain why that is still the right choice."
        if already_at_latest
        else (
            f"The project's detected/current Java version is: {source_java_version}. "
            f"Allowed target versions to choose from (must pick exactly one): {', '.join(allowed_target_versions)}."
        )
    )

    return f"""Analyze this Java project and recommend a target Java version for migration.

{situation}

Project metadata detected from the real repository:
- Build tool: {build_tool or 'unknown'}
- Has automated tests: {'yes' if has_tests else 'no'}
- Detected REST API endpoint count: {api_endpoint_count}
- Migration risk level: {risk_level or 'unknown'}
- Dependencies detected ({len(dependency_lines)} shown, max 25):
{dependency_block}

Respond with only the JSON object described in the system prompt."""


UNIT_TEST_GENERATION_SYSTEM_PROMPT = """You are a senior Java engineer writing high-quality JUnit 5 unit tests for a \
single production class. You always answer with a single, strict JSON object and nothing else - no markdown \
fences, no commentary outside the JSON.

The JSON object must have exactly these keys:
- "testClassName": string, the generated test class name (production class name + "Test").
- "packageName": string, must exactly match the production class's package.
- "targetPath": string, the test source file path relative to the project root \
(e.g. "src/test/java/com/example/service/UserServiceTest.java").
- "framework": string, one of "JUNIT_5".
- "testCases": array of objects, each with "methodName" (string), "type" (one of "POSITIVE", "NEGATIVE", \
"BOUNDARY", "EXCEPTION"), "targetMethod" (string, must be one of the production method names given to you), \
"scenario" (short string describing the input/state), and "expectedResult" (short string describing the \
expected outcome).
- "sourceCode": string, the COMPLETE compilable Java source of the test class (package declaration, imports, \
class, and every method from testCases implemented with real JUnit 5 assertions and, when dependencies are \
given, real Mockito mocks/verifications).

Strict rules for "sourceCode":
- Use JUnit 5 (org.junit.jupiter.api.*) and Mockito (org.mockito.*) only. Never JUnit 4 or TestNG.
- Mock every constructor/field-injected dependency you were given; never call a real external service, \
database, or network endpoint.
- Never hardcode secrets, credentials, or API keys.
- Every test method must contain at least one real, meaningful assertion tied to the method's actual \
behavior. Never write `assertTrue(true)`, `assertFalse(false)`, or any other assertion that always passes \
regardless of the code under test.
- Do not write tests that only call getters/setters with no behavior.
- Do not duplicate two test methods covering the exact same branch/scenario.
- Only test methods and behavior that exist on the production class you were given -- never invent methods.
- Keep the number of test methods within the requested maximum.
"""


def build_unit_test_generation_prompt(
    *,
    class_entry: ClassInventoryEntry,
    production_source: str,
    java_version: str,
    spring_boot_version: str | None,
    build_tool: str,
    test_framework: str = "JUNIT_5",
    mock_framework: str = "Mockito",
    max_test_cases: int,
    existing_test_style: str | None = None,
) -> str:
    """Bounded per-class context for LLM test generation (Step 5).

    Sends only this one production class's source + the OpenRewrite-derived
    metadata about it -- never the whole repository.
    """
    methods_block = "\n".join(
        f"- {m.visibility} {m.return_type} {m.name}("
        + ", ".join(f"{p.get('type')} {p.get('name')}" for p in m.parameters)
        + f") [branches={m.branch_count}, throwsExceptions={m.throws_exceptions}]"
        for m in class_entry.methods
    ) or "(no public/protected methods detected)"

    dependencies_block = ", ".join(class_entry.dependencies) if class_entry.dependencies else "(none detected)"

    style_block = (
        f"\n\nMatch this project's existing test style where reasonable:\n{existing_test_style[:1500]}"
        if existing_test_style
        else ""
    )

    return f"""Generate JUnit 5 unit tests for this production class.

Project context:
- Build tool: {build_tool}
- Java version: {java_version}
- Spring Boot version: {spring_boot_version or "not a Spring Boot project"}
- Test framework: {test_framework}
- Mock framework: {mock_framework}
- Maximum test methods to generate: {max_test_cases}

Production class metadata (from static analysis, not guesswork):
- Class: {class_entry.class_name}
- Package: {class_entry.package_name}
- Classification: {class_entry.class_type}
- Constructor/field dependencies: {dependencies_block}
- Methods:
{methods_block}

Complete production class source:
```java
{production_source}
```
{style_block}

Generate positive, negative, boundary, and exception-path tests as appropriate for the methods above -- only \
for behavior that genuinely exists in this source. Respond with only the JSON object described in the system \
prompt."""


UNIT_TEST_REPAIR_SYSTEM_PROMPT = """You are a senior Java engineer fixing a JUnit 5 test class that failed to \
compile. You always answer with a single, strict JSON object and nothing else - no markdown fences, no \
commentary outside the JSON.

The JSON object must have exactly these keys, in the same shape as before: "testClassName", "packageName", \
"targetPath", "framework", "testCases", "sourceCode". Keep the same test intent and scenarios; only fix what \
is necessary to make the code compile and run correctly. Never remove real assertions and never replace them \
with `assertTrue(true)` or similar placeholders. Never modify or reference production source code -- only fix \
the test class itself."""


def build_unit_test_repair_prompt(
    *, previous_source: str, compiler_diagnostics: str, class_entry: ClassInventoryEntry
) -> str:
    """Step 8's controlled repair loop: send only the failed source + real
    compiler diagnostics + the same bounded production-class metadata --
    never the whole repository, and never more than the diagnostics needed
    to fix the specific failure.
    """
    return f"""The following generated JUnit 5 test class for `{class_entry.class_name}` \
(package `{class_entry.package_name}`) failed to compile. Fix it.

Previous generated source:
```java
{previous_source}
```

Compiler diagnostics:
```
{compiler_diagnostics[:3000]}
```

Respond with only the corrected JSON object described in the system prompt."""
