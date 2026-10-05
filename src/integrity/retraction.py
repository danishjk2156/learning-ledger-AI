"""
Retraction Gate — check if a paper has been retracted or corrected.

Two-layer approach:
  1. Local: Retraction Watch CSV imported into SQLite (offline, fast)
  2. Online: Crossref REST API `update-to` field (live, authoritative)
"""

import csv
import os
import sqlite3
import requests
from functools import lru_cache

DB_PATH = ".ledger/retraction.db"
CROSSREF_BASE = "https://api.crossref.org/works"
CSV_PATH = "retraction-watch-data/retraction_watch.csv"


def init_retraction_db(csv_path: str = CSV_PATH) -> sqlite3.Connection:
    """
    Build local SQLite index from Retraction Watch CSV.

    This should be called once on startup. The CSV is ~300MB and updated daily
    by Crossref. The SQLite DB enables fast O(1) lookups.

    Args:
        csv_path: Path to the retraction_watch.csv file.

    Returns:
        SQLite connection.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retractions (
            doi TEXT PRIMARY KEY,
            title TEXT,
            reason TEXT,
            date TEXT
        )
    """
    )

    if os.path.exists(csv_path):
        print(f"[Retraction] Importing from {csv_path}...")
        imported = 0
        try:
            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                # Log columns on first run to verify schema
                if reader.fieldnames:
                    print(f"[Retraction] CSV columns: {reader.fieldnames}")

                for row in reader:
                    # Try common column name variants
                    doi = (
                        row.get("OriginalPaperDOI", "")
                        or row.get("original_paper_doi", "")
                        or row.get("DOI", "")
                    ).strip()

                    if doi:
                        title = row.get("Title", row.get("title", ""))
                        reason = row.get("Reason", row.get("reason", ""))
                        date = row.get(
                            "RetractionDate",
                            row.get("retraction_date", ""),
                        )
                        conn.execute(
                            "INSERT OR REPLACE INTO retractions VALUES (?, ?, ?, ?)",
                            (doi, title, reason, date),
                        )
                        imported += 1

            conn.commit()
            print(f"[Retraction] Imported {imported} retracted DOIs.")
        except Exception as e:
            print(f"[Retraction] Warning: CSV import failed: {e}")
    else:
        print(
            f"[Retraction] CSV not found at {csv_path}. "
            "Run: git clone https://gitlab.com/crossref/retraction-watch-data"
        )

    return conn


@lru_cache(maxsize=4096)
def check_retraction(doi: str) -> dict:
    """
    Check if a paper is retracted.

    Checks local Retraction Watch DB first (offline, fast),
    then falls back to Crossref API (online, authoritative).

    Args:
        doi: The paper's DOI.

    Returns:
        Dict with: status ('retracted'|'corrected'|'ok'|'unknown'),
                   reason, date, source.
    """
    if not doi:
        return {"status": "unknown"}

    # Local check (offline)
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT reason, date FROM retractions WHERE doi = ?", (doi,)
        ).fetchone()
        conn.close()

        if row:
            return {
                "status": "retracted",
                "reason": row[0],
                "date": row[1],
                "source": "retraction_watch_local",
            }
    except sqlite3.OperationalError:
        pass  # DB not initialized yet

    # Online check via Crossref REST API
    try:
        r = requests.get(
            f"{CROSSREF_BASE}/{doi}",
            headers={"User-Agent": "LearningLedger/1.0 (mailto:user@example.com)"},
            timeout=8,
        )
        if r.status_code == 200:
            updates = r.json().get("message", {}).get("update-to", [])
            for u in updates:
                update_type = u.get("type", "").lower()
                if update_type == "retraction":
                    return {
                        "status": "retracted",
                        "reason": u.get("label", "Retraction"),
                        "date": u.get("updated"),
                        "source": "crossref_api",
                    }
                if update_type == "correction":
                    return {
                        "status": "corrected",
                        "reason": u.get("label", "Correction"),
                        "date": u.get("updated"),
                        "source": "crossref_api",
                    }
            return {"status": "ok"}
    except requests.RequestException:
        pass

    return {"status": "unknown"}
