"""Strip internal migration-tooling identifiers from user-facing text.

The platform runs OpenRewrite under the hood, but that must never be exposed to
end users. This module redacts the tool name and its recipe coordinates (e.g.
``org.openrewrite.java.migrate.UpgradeToJava21``) from any text that could reach
a user — chatbot context/answers, generated docs, API payloads.

Pure and dependency-free: input string in, sanitized string out.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

_ENGINE_NAME = "the JavaApex migration engine"

# Recipe coordinates: dotted identifiers under the org.openrewrite namespace.
_COORDINATE_RE = re.compile(r"\borg\.openrewrite\.[\w.$]+", re.IGNORECASE)
# The tool name itself, however spaced/hyphenated ("OpenRewrite", "open rewrite").
_TOOL_RE = re.compile(r"\bopen[\s-]?rewrite\b", re.IGNORECASE)

# Safety cap: if a single unbroken token grows past this without any whitespace,
# flush it anyway so a pathological no-space stream can't buffer forever.
_MAX_BUFFER = 2000


def sanitize(text: str) -> str:
    """Redact OpenRewrite tool name and recipe coordinates from ``text``."""
    if not text:
        return text
    text = _COORDINATE_RE.sub("an automated migration transformation", text)
    return _TOOL_RE.sub(_ENGINE_NAME, text)


async def sanitize_stream(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """Sanitize a stream of text deltas without ever splitting a token.

    A coordinate/tool name may straddle two deltas (e.g. ``"org.open"`` +
    ``"rewrite.X"``). Since both patterns are contiguous non-whitespace tokens, we
    buffer, emit only up to the last whitespace (a guaranteed-safe boundary), and
    keep the trailing partial token until more arrives — flushing the remainder at
    the end. This redacts patterns of any length spanning delta boundaries.
    """
    buffer = ""
    async for chunk in chunks:
        buffer += chunk
        split = buffer.rfind(" ")
        if split == -1 and len(buffer) >= _MAX_BUFFER:
            split = len(buffer) - 1  # no space yet but too long — flush anyway
        if split != -1:
            emit, buffer = buffer[: split + 1], buffer[split + 1 :]
            if emit:
                yield sanitize(emit)
    if buffer:
        yield sanitize(buffer)
