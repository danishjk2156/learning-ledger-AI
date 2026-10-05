"""
Notification — tell the user what they need to unlearn.

Formats flagged claims into a human-readable report.
"""


def notify_user(flagged: list[dict]) -> str:
    """
    Format and display flagged claims.

    Args:
        flagged: List of dicts with claim_id, claim, reason, action.

    Returns:
        Formatted notification string.
    """
    if not flagged:
        msg = "✅ All your claims are still valid. Nothing to unlearn."
        print(msg)
        return msg

    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(
        f"  ⚠️  {len(flagged)} thing(s) you learned are now uncertain:"
    )
    lines.append("=" * 60)
    lines.append("")

    action_icons = {
        "UNLEARN": "🚫",
        "REVISE": "⚠️",
        "REVIEW": "🔍",
    }

    for i, f in enumerate(flagged, 1):
        icon = action_icons.get(f["action"], "❓")
        lines.append(f'  {i}. {icon} "{f["claim"]}"')
        lines.append(f'     Reason: {f["reason"]}')
        lines.append(f'     Action: {f["action"]}')
        lines.append(f'     ID: {f["claim_id"]}')
        lines.append("")

    lines.append("  Actions available:")
    lines.append("    🚫 UNLEARN — Paper was retracted. Remove this from your knowledge.")
    lines.append("    ⚠️  REVISE  — Evidence weakened. Update your understanding.")
    lines.append("    🔍 REVIEW  — Upstream dependency flagged. Check the chain.")
    lines.append("")

    report = "\n".join(lines)
    print(report)
    return report


def format_claim_summary(claims: list[dict]) -> str:
    """
    Format a list of claims as a readable summary.

    Args:
        claims: List of claim dicts from the ledger.

    Returns:
        Formatted string.
    """
    if not claims:
        return "📭 No claims recorded yet."

    lines = [f"📚 {len(claims)} claim(s) in your ledger:\n"]

    status_icons = {
        "active": "✅",
        "suspect": "⚠️",
        "retracted": "🚫",
    }

    for c in claims:
        icon = status_icons.get(c.get("status", ""), "❓")
        conf = c.get("confidence", 0)
        lines.append(f'  {icon} [{c["claim_id"]}] {c["claim"]}')
        lines.append(
            f'     Source: {c.get("source_title", "unknown")} | '
            f'Confidence: {conf:.0%} | Status: {c.get("status", "unknown")}'
        )
        if c.get("doi"):
            lines.append(f'     DOI: {c["doi"]}')
        lines.append("")

    return "\n".join(lines)
