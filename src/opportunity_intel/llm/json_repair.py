"""Central JSON extraction and repair utility for LLM outputs.

All agents must import ``parse_llm_json`` from here instead of
implementing their own ``_parse_json`` functions. This is the single
source of truth for handling:

  - Clean JSON strings returned directly by the model
  - JSON wrapped in markdown fences (```json ... ```)
  - JSON embedded inside prose (e.g. "Here is the result: {...}")
  - Trailing explanation text after a valid JSON block

Raises ``json.JSONDecodeError`` only when all recovery attempts fail.
"""

from __future__ import annotations

import json
import re

# Matches opening ``` or ```json fences and their closing ```
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _strip_fence(text: str) -> str | None:
    """Return the content inside the first markdown code fence, or None."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return None


def _extract_balanced_block(text: str, start_char: str) -> str | None:
    """Find the first occurrence of start_char and extract the balanced block.

    Works for both ``{`` (objects) and ``[`` (arrays).
    """
    end_char = "}" if start_char == "{" else "]"
    idx = text.find(start_char)
    if idx == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for pos in range(idx, len(text)):
        ch = text[pos]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == start_char:
            depth += 1
        elif ch == end_char:
            depth -= 1
            if depth == 0:
                return text[idx : pos + 1]
    return None


def parse_llm_json(text: str) -> dict | list:
    """Parse JSON from LLM output using multiple recovery strategies.

    Strategy order:
    1. Direct ``json.loads`` on the stripped text.
    2. Strip markdown fences, then ``json.loads``.
    3. Extract the first balanced block (``{…}`` or ``[…]``) from the text,
       choosing whichever delimiter appears first, then ``json.loads``.

    Raises ``json.JSONDecodeError`` only if all strategies fail.
    """
    if not text or not text.strip():
        raise json.JSONDecodeError("Empty LLM response", "", 0)

    cleaned = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    defenced = _strip_fence(cleaned)
    if defenced:
        try:
            return json.loads(defenced)
        except json.JSONDecodeError:
            pass

    # Strategies 3 & 4: extract the first balanced block from prose.
    # Try whichever delimiter appears earliest in the text so that an array
    # like '[{"a":1}] trailing text' is parsed as a list, not as the inner dict.
    obj_pos = cleaned.find("{")
    arr_pos = cleaned.find("[")

    # Build an ordered list of (delimiter, fallback_delimiter)
    if obj_pos == -1 and arr_pos == -1:
        first_delimiters: list[str] = []
    elif obj_pos == -1:
        first_delimiters = ["[", "{"]
    elif arr_pos == -1:
        first_delimiters = ["{", "["]
    elif arr_pos < obj_pos:
        first_delimiters = ["[", "{"]
    else:
        first_delimiters = ["{", "["]

    for delim in first_delimiters:
        block = _extract_balanced_block(cleaned, delim)
        if block:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass

    # All strategies exhausted — raise a meaningful error
    preview = cleaned[:120].replace("\n", " ")
    raise json.JSONDecodeError(
        f"Could not parse JSON from LLM output. Preview: {preview!r}",
        cleaned,
        0,
    )
