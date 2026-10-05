"""
Version Tracker — check paper lifecycle via OpenAlex.

Returns retraction status, publication date, type (article/preprint),
and citation count. Uses the OpenAlex API with optional API key.
"""

import os
import requests
from functools import lru_cache

OPENALEX_BASE = "https://api.openalex.org/works"


@lru_cache(maxsize=1024)
def check_versions(doi: str) -> dict:
    """
    Get paper lifecycle metadata from OpenAlex.

    Args:
        doi: The paper's DOI.

    Returns:
        Dict with: status, is_retracted, publication_date, type,
                   cited_by_count.
    """
    if not doi:
        return {"status": "unknown"}

    try:
        params = {}
        api_key = os.getenv("OPENALEX_API_KEY")
        if api_key:
            params["api_key"] = api_key

        r = requests.get(
            f"{OPENALEX_BASE}/https://doi.org/{doi}",
            params=params,
            headers={"User-Agent": "LearningLedger/1.0"},
            timeout=8,
        )

        if r.status_code != 200:
            return {"status": "unknown", "http_code": r.status_code}

        work = r.json()
        return {
            "status": "ok",
            "is_retracted": work.get("is_retracted", False),
            "publication_date": work.get("publication_date"),
            "type": work.get("type"),  # "article", "preprint", etc.
            "cited_by_count": work.get("cited_by_count", 0),
            "title": work.get("title", ""),
            "doi": doi,
        }

    except requests.RequestException:
        return {"status": "unknown"}
