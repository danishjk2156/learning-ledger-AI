"""
Access Resolver — finds open-access PDFs for DOIs.

Routes: Unpaywall → OpenAlex → paywalled.
Updated for OpenAlex API key requirement (Feb 2026).
"""

import os
import requests
from functools import lru_cache

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
OPENALEX_BASE = "https://api.openalex.org/works"


@lru_cache(maxsize=2048)
def resolve_oa(doi: str) -> dict:
    """
    Try every open-access route for a DOI.

    Checks Unpaywall first (fast, reliable), then OpenAlex (broader coverage).
    Returns a dict with status, pdf_url, and source.

    Args:
        doi: The DOI string (e.g., "10.1038/s41586-020-2649-2").

    Returns:
        Dict with keys: status ('oa'|'paywalled'|'no_doi'), pdf_url, source.
    """
    if not doi:
        return {"status": "no_doi"}

    email = os.getenv("UNPAYWALL_EMAIL", "user@example.com")
    openalex_key = os.getenv("OPENALEX_API_KEY", "")

    # Route 1: Unpaywall (free, email-only auth)
    try:
        r = requests.get(
            f"{UNPAYWALL_BASE}/{doi}",
            params={"email": email},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("is_oa"):
                best = data.get("best_oa_location") or {}
                return {
                    "status": "oa",
                    "pdf_url": best.get("url_for_pdf") or best.get("url"),
                    "host_type": best.get("host_type"),
                    "version": best.get("version"),
                    "source": "unpaywall",
                }
    except requests.RequestException:
        pass

    # Route 2: OpenAlex (successor to Unpaywall, broader data)
    try:
        params = {}
        if openalex_key:
            params["api_key"] = openalex_key

        r = requests.get(
            f"{OPENALEX_BASE}/https://doi.org/{doi}",
            params=params,
            headers={"User-Agent": "LearningLedger/1.0"},
            timeout=5,
        )
        if r.status_code == 200:
            work = r.json()
            oa = work.get("open_access", {})
            if oa.get("is_oa"):
                best = work.get("best_oa_location") or {}
                return {
                    "status": "oa",
                    "pdf_url": best.get("pdf_url") or best.get("landing_page_url"),
                    "host_type": best.get("source", {}).get("type"),
                    "version": best.get("version"),
                    "source": "openalex",
                }
    except requests.RequestException:
        pass

    return {"status": "paywalled", "doi": doi}


def download_pdf(url: str, save_path: str) -> bool:
    """
    Download a PDF from a URL.

    Args:
        url: URL of the PDF.
        save_path: Local path to save the file.

    Returns:
        True if download succeeded.
    """
    if not url:
        return False
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except requests.RequestException:
        pass
    return False
