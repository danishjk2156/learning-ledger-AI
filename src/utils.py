"""
Utility functions for Learning Ledger.
Includes robust JSON parsing with validation, retry, and code fence stripping.
"""

import json
import re
import time
from typing import Any, Union


def safe_parse_json(response_text: str, max_retries: int = 3, fallback: Any = None) -> Union[dict, list, Any]:
    """
    Parse JSON with validation and retry on failure.
    Strips markdown code fences (```json ... ```) and cleans raw strings.
    Never crashes with Unexpected token 'I' or similar decode errors.

    Args:
        response_text: Raw string response from API or LLM.
        max_retries: Number of parse attempts with cleaning.
        fallback: Optional fallback to return if parsing fails.

    Returns:
        Parsed JSON dict/list, or fallback dict if parsing fails.
    """
    if not response_text or not isinstance(response_text, str):
        return fallback if fallback is not None else {"error": "Empty or non-string response", "parse_failed": True}

    cleaned = response_text.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Also search for embedded JSON object or array if text contains surrounding prose
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    candidates = [cleaned]
    if match and match.group(0) != cleaned:
        candidates.append(match.group(0))

    for candidate in candidates:
        for attempt in range(max_retries):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                    continue

    if fallback is not None:
        return fallback

    return {"raw_text": response_text, "parse_failed": True}
