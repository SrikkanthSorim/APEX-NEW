"""Centralized user-facing migration log sanitizer.

Every migration log line, recipe name, and progress message that reaches an
API response, the WebSocket/polling layer, a downloadable report, or the
Migration Log UI passes through this module first. It strips OpenRewrite
package/recipe names, Maven/Gradle plugin internals, absolute workspace
paths, temporary file names, and credentials, and replaces the resulting
technical noise with short, professional progress messages.

Nothing here disables or reduces backend logging: callers are expected to
keep writing the original, unsanitized text to their own log file /
``logging`` output for developer troubleshooting (see
``MigrationReportStore.append_logs``), and only pass the *sanitized* result
to anything the user can see. This is the one place that mapping lives, so
no other module should hand-roll its own OpenRewrite-stripping regex.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# --------------------------------------------------------------------------- #
# Redaction — applied to every line before anything else, so a technical
# rule below can never accidentally leave a credential or an absolute path
# behind in the text it keeps.
# --------------------------------------------------------------------------- #

_CREDENTIAL_IN_URL = re.compile(r"(https?://)[^/\s@]+(?::[^/\s@]*)?@")
_TOKEN_LIKE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|(?:[A-Za-z0-9_\-]{20,}\.){2}[A-Za-z0-9_\-]{10,})\b"
)
_TEMP_ARTIFACT = re.compile(r"\.javaapex-[\w.\-]*")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s\"'<>]+")
_UNIX_PATH = re.compile(r"(?<![\w/])/(?:[\w.\-]+/)+[\w.\-]+")

_RECIPE_FQN = re.compile(r"\borg\.openrewrite\.[\w$]+(?:\.[\w$]+)*")
_OPENREWRITE_WORD = re.compile(r"\bopen\s*rewrite\b", re.IGNORECASE)


def _redact(line: str) -> str:
    line = _CREDENTIAL_IN_URL.sub(r"\1", line)
    line = _TOKEN_LIKE.sub("[redacted]", line)
    line = _TEMP_ARTIFACT.sub("a temporary migration file", line)
    line = _UUID.sub("", line)
    line = _WINDOWS_PATH.sub("the project directory", line)
    line = _UNIX_PATH.sub("the project directory", line)
    return line


# --------------------------------------------------------------------------- #
# Recipe-name humanization — generic (no hardcoded Java version / repo),
# used both standalone (`recipes_executed`) and inline inside prose.
# --------------------------------------------------------------------------- #

_RECIPE_CLASS_LABELS: dict[str, str] = {
    "UpgradeJavaVersion": "Java version configuration",
    "JavaxMigrationToJakarta": "Jakarta namespace migration",
    "UpgradeDependencyVersion": "Dependency version upgrade",
    "RemoveUnusedImports": "Removed unused imports",
    "OrderImports": "Organized imports",
    "JUnit5BestPractices": "JUnit 5 test framework upgrade",
}


def _split_pascal_case(text: str) -> str:
    text = text.replace("_", " ")
    text = re.sub(r"(?<!^)(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_BARE_IDENTIFIER = re.compile(r"^[\w.$]+$")


def humanize_recipe_name(entry: str) -> str:
    """Turn one OpenRewrite recipe reference into a short, friendly label.

    Works generically off the class-name shape rather than a per-recipe
    lookup for every case, so it never needs updating for a new Java
    version or a new recipe added to the catalog.
    """
    name = (entry or "").strip()
    if not name:
        return "Migration step"

    if not _BARE_IDENTIFIER.match(name):
        # Not a plain recipe class name (e.g. a build-repair note that
        # mentions a coordinate/version) -- scrub it like any other prose
        # instead of tearing it apart at the last '.'.
        return _generic_clean(name) or name

    class_name = name.rsplit(".", 1)[-1] if "." in name else name
    class_name = class_name.strip("{}").split(":", 1)[0].strip()

    if class_name in _RECIPE_CLASS_LABELS:
        return _RECIPE_CLASS_LABELS[class_name]

    match = re.match(r"UpgradeToJava(\d+)$", class_name)
    if match:
        return f"Upgrade to Java {match.group(1)}"

    match = re.match(r"UpgradeSpringBoot_(\d+)_(\d+)$", class_name)
    if match:
        return f"Spring Boot {match.group(1)}.{match.group(2)} upgrade"

    if not class_name or not re.search(r"[A-Za-z]", class_name):
        return "Migration step"

    return _split_pascal_case(class_name) or "Migration step"


def humanize_recipe_names(entries: Iterable[str]) -> list[str]:
    """Humanize + de-duplicate a list of recipe references, preserving order."""
    return list(dict.fromkeys(humanize_recipe_name(entry) for entry in entries if str(entry).strip()))


def _replace_recipe_refs(text: str) -> str:
    return _RECIPE_FQN.sub(lambda m: humanize_recipe_name(m.group(0)), text)


# --------------------------------------------------------------------------- #
# Known stage / progress line mappings — the exact vocabulary requested for
# the Migration Log UI. Checked in order; first match wins.
# --------------------------------------------------------------------------- #

def _stage(message: str):
    return lambda _m: message


_STAGE_RULES: list[tuple[re.Pattern, "object"]] = [
    (re.compile(r"scanning for projects", re.IGNORECASE), _stage("Analyzing project structure")),
    (re.compile(r"^\[INFO]\s*Building\s", re.IGNORECASE), _stage("Preparing project build")),
    (
        re.compile(r"selected java recipe for target\s+(\d+)", re.IGNORECASE),
        lambda m: f"Preparing Java version upgrade to {m.group(1)}",
    ),
    (
        re.compile(r"asserting exact target java version\s+(\d+)", re.IGNORECASE),
        lambda m: "Applying Java version configuration",
    ),
    (
        re.compile(r"source java .* already meets target", re.IGNORECASE),
        _stage("Project already meets the target Java version; no upgrade needed."),
    ),
    (re.compile(r"selected conditional recipe jakarta-ee", re.IGNORECASE), _stage("Applying Jakarta namespace migration")),
    (re.compile(r"selected conditional recipe junit4-to-5", re.IGNORECASE), _stage("Updating test framework configuration")),
    (re.compile(r"selected spring boot upgrade recipe", re.IGNORECASE), _stage("Upgrading Spring Boot configuration")),
    (re.compile(r"dependency currency bump for", re.IGNORECASE), _stage("Updating dependency versions")),
    (re.compile(r"selected cleanup recipe", re.IGNORECASE), _stage("Cleaning up source code")),
    (
        re.compile(r"^={3,}\s*migration phase:\s*(.+?)\s*={3,}$", re.IGNORECASE),
        lambda m: f"Starting: {m.group(1)}",
    ),
    (re.compile(r"^={3,}\s*quality gates\s*={3,}$", re.IGNORECASE), _stage("Running code quality and dependency scans")),
    (
        re.compile(r"^={3,}\s*build success\s*\((\w+)\)\s*={3,}$", re.IGNORECASE),
        lambda m: "Build verification succeeded",
    ),
    (
        re.compile(r"^={3,}\s*build failed\s*\((\w+)\)\s*={3,}$", re.IGNORECASE),
        lambda m: "Build verification found issues",
    ),
    (
        re.compile(r"^={3,}\s*build skipped\s*\((\w+)\)\s*={3,}$", re.IGNORECASE),
        _stage("Build verification skipped for this environment"),
    ),
    (re.compile(r"using active recipe|:rewriterun\b", re.IGNORECASE), _stage("Applying source-code changes")),
    (re.compile(r"^build successful\b", re.IGNORECASE), _stage("Build verification succeeded")),
    (re.compile(r"^build failed\b", re.IGNORECASE), _stage("Build verification found issues")),
    (
        re.compile(r"retrying with additional migration recipe", re.IGNORECASE),
        _stage("Retrying migration with additional fixes"),
    ),
]

# --------------------------------------------------------------------------- #
# Noise — dropped outright rather than shown as a (possibly empty) message.
# --------------------------------------------------------------------------- #

_NOISE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^[-=_]{3,}$"),
    re.compile(r"^\s*at\s+[\w.$<>]+\("),  # stack trace frame
    re.compile(r"^caused by:\s*$", re.IGNORECASE),
    re.compile(r"^\[INFO]\s*-{3,}\s*$"),
    re.compile(r"^\[INFO]\s*---\s", re.IGNORECASE),  # maven plugin-goal banner
    re.compile(r"^>\s*task\s+:[\w:\-]+\s*$", re.IGNORECASE),  # gradle task line, not a failure
    re.compile(r"^org\.openrewrite\.recipe:[\w.\-]+:[\w.\-]+$"),  # bare artifact coordinate
    re.compile(r"^downloading from|^downloaded from|^progress \(|^uploading", re.IGNORECASE),
]


def _is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in _NOISE_PATTERNS)


# --------------------------------------------------------------------------- #
# Error simplification — errors are never hidden, only reworded so the
# underlying OpenRewrite/Maven/Gradle exception class isn't exposed.
# --------------------------------------------------------------------------- #

_KNOWN_ERROR_MAPPINGS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"MavenDownloadingException|could not resolve dependencies|could not find artifact", re.IGNORECASE),
        "Unable to download a required Maven dependency. Check repository access and network configuration.",
    ),
    (
        re.compile(r"UnknownHostException|ConnectException|could not resolve host|network is unreachable", re.IGNORECASE),
        "A network or repository connectivity issue prevented a required dependency from downloading.",
    ),
    (
        re.compile(r"OutOfMemoryError", re.IGNORECASE),
        "The build ran out of memory. Consider increasing the available memory for the build process.",
    ),
]


def _looks_like_error(line: str) -> bool:
    upper = line.upper()
    return "[ERROR]" in upper or "BUILD FAILURE" in upper or "BUILD FAILED" in upper or " FAILED" in upper


def _simplify_error(line: str) -> str:
    for pattern, replacement in _KNOWN_ERROR_MAPPINGS:
        if pattern.search(line):
            return replacement
    cleaned = _generic_clean(line)
    return cleaned or "A build error occurred. See the migration report for details."


# --------------------------------------------------------------------------- #
# Generic fallback cleanup — for anything not covered by a specific rule
# above (build-modernization notes, diagnostician reasons, unmapped tool
# output). Strips recipe class names / the OpenRewrite brand word / secrets
# / paths, but otherwise preserves the sentence.
# --------------------------------------------------------------------------- #

def _generic_clean(line: str) -> str:
    text = _redact(line)
    text = _replace_recipe_refs(text)
    # "OpenRewrite" reads naturally as "migration" in the sentences this
    # brand word actually shows up in ("OpenRewrite recipe(s)/plugin/failed/
    # could not run" -> "migration recipe(s)/plugin/failed/could not run").
    text = _OPENREWRITE_WORD.sub("migration", text)
    text = re.sub(r"^\[(INFO|WARN|WARNING|DEBUG)]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" :-\t")
    if text and text[0].isalpha():
        text = text[0].upper() + text[1:]
    return text


def _match_stage(line: str) -> str | None:
    for pattern, formatter in _STAGE_RULES:
        match = pattern.search(line)
        if match:
            return formatter(match)
    return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def sanitize_line(raw: str) -> str | None:
    """Sanitize one raw log line. Returns ``None`` for lines that should be
    dropped entirely (noise) — never for a genuine error/warning.
    """
    line = (raw or "").rstrip()
    if not line.strip():
        return None
    if _is_noise(line):
        return None

    staged = _match_stage(line)
    if staged is not None:
        return staged

    if _looks_like_error(line):
        return _simplify_error(line)

    cleaned = _generic_clean(line)
    return cleaned or None


def sanitize_lines(lines: Iterable[str]) -> list[str]:
    """Sanitize a batch of raw log lines into de-duplicated, user-facing
    progress/error messages, preserving first-seen order.
    """
    result: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        cleaned = sanitize_line(raw)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def sanitize_text(raw: str | None) -> str:
    """Sanitize a single, always-kept piece of prose (summaries, reasons,
    notes). Unlike :func:`sanitize_line`, this never drops content — it only
    removes technical internals from it.
    """
    if not raw or not raw.strip():
        return raw or ""
    if _looks_like_error(raw):
        return _simplify_error(raw)
    return _generic_clean(raw) or raw.strip()
