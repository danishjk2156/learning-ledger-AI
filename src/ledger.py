"""
Learning Ledger — the core claim storage.

Records what you learned, tied to the exact quote, DOI, and source.
Each claim is immediately verified by Jev before storing.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime

DB = ".ledger/ledger.db"


def init_ledger() -> sqlite3.Connection:
    """
    Initialize the ledger database.

    Creates the claims table if it doesn't exist.

    Returns:
        SQLite connection.
    """
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS claims (
            claim_id TEXT PRIMARY KEY,
            claim TEXT NOT NULL,
            doi TEXT,
            source_title TEXT,
            quote TEXT,
            page INTEGER,
            learned_at TEXT,
            confidence REAL,
            status TEXT DEFAULT 'active',
            depends_on TEXT,
            checked_at TEXT,
            note TEXT
        )
    """
    )
    conn.commit()
    return conn


def record_claim(claim: str, source: dict, jev, llm) -> dict:
    """
    Record a learned claim in the ledger.

    Immediately checks if the quote supports the claim via Jev.
    If ambiguous, asks the LLM for a second opinion.

    Args:
        claim: What the user learned, in their own words.
        source: Dict with 'quote', 'doi', 'title', 'page'.
        jev: DecisionGate instance.
        llm: LLMClient instance.

    Returns:
        Dict with the stored claim entry.
    """
    # Use 12-char SHA-256 hash (not 6-char MD5) to avoid collisions
    claim_id = hashlib.sha256(
        f"{claim}:{source.get('doi', '')}".encode()
    ).hexdigest()[:12]

    quote = source.get("quote", "")

    # Jev: does the quote actually support this claim?
    try:
        support = jev.claim_support(claim, quote)
    except Exception as e:
        print(f"[Ledger] Jev check failed ({e}), defaulting to 0.5")
        support = 0.5

    note = None

    # If ambiguous (0.4–0.8), ask the LLM for a second opinion
    if 0.4 < support < 0.8 and quote:
        try:
            note = llm.generate(
                prompt=(
                    f'Quote from paper: "{quote}"\n\n'
                    f"Claim: {claim}\n\n"
                    f"Does the quote directly support this claim? "
                    f"Answer YES or NO, then explain why in one sentence."
                ),
                system="You are a careful research assistant. Be precise.",
            )
        except Exception as e:
            note = f"LLM verification failed: {e}"

    entry = {
        "claim_id": claim_id,
        "claim": claim,
        "doi": source.get("doi", ""),
        "source_title": source.get("title", ""),
        "quote": quote,
        "page": source.get("page", 0),
        "learned_at": datetime.now().isoformat(),
        "confidence": round(support, 3),
        "status": "active" if support > 0.5 else "suspect",
        "depends_on": json.dumps(source.get("depends_on", [])),
        "checked_at": datetime.now().isoformat(),
        "note": note,
    }

    conn = sqlite3.connect(DB)
    conn.execute(
        """
        INSERT OR REPLACE INTO claims
        (claim_id, claim, doi, source_title, quote, page,
         learned_at, confidence, status, depends_on, checked_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            entry["claim_id"],
            entry["claim"],
            entry["doi"],
            entry["source_title"],
            entry["quote"],
            entry["page"],
            entry["learned_at"],
            entry["confidence"],
            entry["status"],
            entry["depends_on"],
            entry["checked_at"],
            entry["note"],
        ),
    )
    conn.commit()
    conn.close()

    # Warn if claim overstates the source
    if support < 0.5:
        print(f"\n⚠️  Warning: the paper says something weaker than your claim.")
        print(f'   Paper says: "{quote[:100]}..."')
        print(f"   You claim:  {claim}")
        print(f"   Confidence: {support:.0%}\n")

    return entry


def get_all_claims(status: str = None) -> list[dict]:
    """
    Get all claims from the ledger.

    Args:
        status: Filter by status ('active', 'suspect', 'retracted').
                None returns all claims.

    Returns:
        List of claim dicts.
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    if status:
        rows = conn.execute(
            "SELECT * FROM claims WHERE status = ? ORDER BY learned_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM claims ORDER BY learned_at DESC"
        ).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_claim(claim_id: str) -> dict | None:
    """Get a single claim by ID."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_claim_status(claim_id: str, status: str, note: str = None):
    """Update a claim's status."""
    conn = sqlite3.connect(DB)
    if note:
        conn.execute(
            "UPDATE claims SET status = ?, note = ?, checked_at = ? WHERE claim_id = ?",
            (status, note, datetime.now().isoformat(), claim_id),
        )
    else:
        conn.execute(
            "UPDATE claims SET status = ?, checked_at = ? WHERE claim_id = ?",
            (status, datetime.now().isoformat(), claim_id),
        )
    conn.commit()
    conn.close()
