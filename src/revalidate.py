"""
Re-validation Job — re-checks all active claims for integrity.

Three checks per claim:
  1. Is the paper retracted or corrected? (Retraction Watch + Crossref)
  2. Does the quote still support the claim? (Jev Noul re-check)
  3. Are upstream dependencies flagged? (Cascade check)

Designed to run weekly or on-demand.
"""

import json
import sqlite3
import time
from datetime import datetime

from .integrity.retraction import check_retraction
from .integrity.version import check_versions
from .ledger import DB

MAX_RETRIES = 3


def revalidate_ledger(jev) -> list[dict]:
    """
    Re-validate all active claims in the ledger.

    Args:
        jev: DecisionGate instance for claim support re-checks.

    Returns:
        List of flagged claims, each with claim_id, claim, reason, action.
    """
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT claim_id, claim, doi, quote, depends_on, status "
        "FROM claims WHERE status = 'active'"
    ).fetchall()

    if not rows:
        print("[Revalidate] No active claims to check.")
        conn.close()
        return []

    print(f"[Revalidate] Checking {len(rows)} active claims...")
    flagged = []

    for claim_id, claim, doi, quote, depends_on, status in rows:
        # ── Check 1: Is the paper retracted? ──
        if doi:
            ret = check_retraction(doi)
            if ret["status"] == "retracted":
                flagged.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim,
                        "reason": f"Paper RETRACTED: {ret.get('reason', 'Unknown')}",
                        "action": "UNLEARN",
                    }
                )
                conn.execute(
                    "UPDATE claims SET status = ?, checked_at = ? WHERE claim_id = ?",
                    ("retracted", datetime.now().isoformat(), claim_id),
                )
                continue

            if ret["status"] == "corrected":
                flagged.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim,
                        "reason": f"Paper CORRECTED: {ret.get('reason', 'Unknown')}",
                        "action": "REVIEW",
                    }
                )

            # Also check OpenAlex for retraction
            versions = check_versions(doi)
            if versions.get("is_retracted"):
                flagged.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim,
                        "reason": "Paper marked retracted on OpenAlex",
                        "action": "UNLEARN",
                    }
                )
                conn.execute(
                    "UPDATE claims SET status = ?, checked_at = ? WHERE claim_id = ?",
                    ("retracted", datetime.now().isoformat(), claim_id),
                )
                continue

        # ── Check 2: Does the quote still support the claim? ──
        if quote:
            support = None
            for attempt in range(MAX_RETRIES):
                try:
                    support = jev.claim_support(claim, quote)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        wait = 2**attempt
                        print(
                            f"[Revalidate] Jev retry {attempt+1} for {claim_id} "
                            f"(waiting {wait}s): {e}"
                        )
                        time.sleep(wait)
                    else:
                        print(
                            f"[Revalidate] Jev failed for {claim_id} after "
                            f"{MAX_RETRIES} attempts: {e}"
                        )

            if support is not None and support < 0.5:
                flagged.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim,
                        "reason": f"Quote support dropped to {support:.0%}",
                        "action": "REVISE",
                    }
                )
                conn.execute(
                    "UPDATE claims SET confidence = ?, checked_at = ? "
                    "WHERE claim_id = ?",
                    (support, datetime.now().isoformat(), claim_id),
                )
                continue

        # ── Check 3: Are upstream dependencies flagged? ──
        deps = json.loads(depends_on or "[]")
        for dep_id in deps:
            if any(f["claim_id"] == dep_id for f in flagged):
                flagged.append(
                    {
                        "claim_id": claim_id,
                        "claim": claim,
                        "reason": f"Depends on flagged claim {dep_id}",
                        "action": "REVIEW",
                    }
                )
                break

        # Mark as checked
        conn.execute(
            "UPDATE claims SET checked_at = ? WHERE claim_id = ?",
            (datetime.now().isoformat(), claim_id),
        )

    conn.commit()
    conn.close()

    print(f"[Revalidate] Done. {len(flagged)} claim(s) flagged.")
    return flagged
