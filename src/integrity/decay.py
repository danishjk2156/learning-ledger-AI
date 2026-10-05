"""
Confidence Decay — model how much to trust a finding over time.

Combines:
  1. Time-based decay: older papers in fast-moving fields decay faster
  2. Jev Noul: "does this finding still hold given current context?"

Field velocity controls how fast findings age:
  - ML papers age fast (0.5/year) → a 2-year-old claim loses ~50% trust
  - Math papers age slowly (0.05/year) → a 20-year-old theorem is still fine
"""

from datetime import datetime, timezone
from typesafe_sdk import Noul

# How fast findings age per field (higher = faster decay)
FIELD_VELOCITY = {
    "machine_learning": 0.5,
    "artificial_intelligence": 0.45,
    "computer_science": 0.35,
    "genetics": 0.4,
    "medicine": 0.3,
    "biology": 0.25,
    "chemistry": 0.2,
    "physics": 0.15,
    "engineering": 0.15,
    "economics": 0.1,
    "mathematics": 0.05,
    "history": 0.02,
}


class ConfidenceDecay:
    """Calculate how much to trust a finding over time."""

    def __init__(self, jev_client):
        """
        Args:
            jev_client: TypeSafeClient instance for Jev calls.
        """
        self.jev = jev_client

    def score(self, metadata: dict, current_context: str = "") -> dict:
        """
        Score how much to trust a finding.

        Args:
            metadata: Dict with publication_date, field, cited_by_count.
            current_context: Optional recent context to evaluate against.

        Returns:
            Dict with decay_factor, jev_confidence, age_years, recommendation.
        """
        pub_date = metadata.get("publication_date")
        if not pub_date:
            return {"decay": "unknown", "confidence": 0.5, "recommendation": "review"}

        # Parse publication date
        try:
            if "T" in pub_date:
                pub = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            else:
                pub = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return {"decay": "unknown", "confidence": 0.5, "recommendation": "review"}

        now = datetime.now(timezone.utc)
        age_years = (now - pub).days / 365.25

        # Time-based decay
        field = metadata.get("field", "general")
        velocity = FIELD_VELOCITY.get(field, 0.2)
        decay_factor = 1.0 / (1.0 + velocity * age_years)

        # Jev Noul: does this still hold?
        jev_confidence = 0.5  # default if Jev fails
        if current_context:
            try:
                result = self.jev.system_one(
                    state={
                        "paper_year": pub.year,
                        "age_years": round(age_years, 1),
                        "field": field,
                        "citation_count": metadata.get("cited_by_count", 0),
                        "current_context": current_context[:1000],
                    },
                    questions={
                        "still_holds": Noul(
                            instructions=(
                                "Does this paper's finding still hold "
                                "given the current context and passage of time?"
                            )
                        )
                    },
                )
                jev_confidence = result.nouls["still_holds"].noul
            except Exception as e:
                print(f"[Decay] Jev call failed: {e}")

        # Combined confidence: weighted average of decay and Jev
        combined = 0.4 * decay_factor + 0.6 * jev_confidence

        return {
            "decay_factor": round(decay_factor, 3),
            "jev_confidence": round(jev_confidence, 3),
            "combined_confidence": round(combined, 3),
            "age_years": round(age_years, 1),
            "field": field,
            "recommendation": (
                "verify"
                if combined < 0.4
                else "review"
                if combined < 0.65
                else "trust"
            ),
        }
