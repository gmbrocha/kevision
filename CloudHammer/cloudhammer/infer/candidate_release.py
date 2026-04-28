from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


RELEASE_ACTIONS = {
    "release_candidate",
    "needs_split_review",
    "review_candidate",
    "low_priority_review",
    "quarantine_likely_false_positive",
    "quarantine_human_rejected",
}


@dataclass(frozen=True)
class ReleaseDecision:
    action: str
    reason: str
    include_in_default_release: bool
    requires_human_review: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_action": self.action,
            "release_reason": self.reason,
            "include_in_default_release": self.include_in_default_release,
            "requires_human_review": self.requires_human_review,
        }


def decide_candidate_release(row: dict[str, Any]) -> ReleaseDecision:
    """Classify one whole-cloud candidate for release/export routing.

    Human review takes precedence over policy buckets. The policy bucket is used
    only when a candidate has no reviewed status.
    """

    review_status = row.get("review_status")
    policy_bucket = str(row.get("policy_bucket") or "")

    if review_status == "accept":
        return ReleaseDecision(
            action="release_candidate",
            reason="human_accept",
            include_in_default_release=True,
            requires_human_review=False,
        )

    if review_status == "overmerged":
        return ReleaseDecision(
            action="needs_split_review",
            reason="human_overmerged",
            include_in_default_release=False,
            requires_human_review=True,
        )

    if review_status in {"false_positive", "partial", "uncertain"}:
        return ReleaseDecision(
            action="quarantine_human_rejected",
            reason=f"human_{review_status}",
            include_in_default_release=False,
            requires_human_review=False,
        )

    if policy_bucket == "auto_deliverable_candidate":
        return ReleaseDecision(
            action="release_candidate",
            reason="policy_auto_deliverable_candidate",
            include_in_default_release=True,
            requires_human_review=False,
        )

    if policy_bucket == "needs_split_review":
        return ReleaseDecision(
            action="needs_split_review",
            reason="policy_needs_split_review",
            include_in_default_release=False,
            requires_human_review=True,
        )

    if policy_bucket == "likely_false_positive":
        return ReleaseDecision(
            action="quarantine_likely_false_positive",
            reason="policy_likely_false_positive",
            include_in_default_release=False,
            requires_human_review=False,
        )

    if policy_bucket == "low_priority_review":
        return ReleaseDecision(
            action="low_priority_review",
            reason="policy_low_priority_review",
            include_in_default_release=False,
            requires_human_review=True,
        )

    return ReleaseDecision(
        action="review_candidate",
        reason="policy_review_candidate",
        include_in_default_release=False,
        requires_human_review=True,
    )


def attach_release_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        enriched.update(decide_candidate_release(enriched).to_dict())
        output.append(enriched)
    return output


def summarize_release_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_candidates": len(rows),
        "release_candidates": sum(1 for row in rows if row.get("release_action") == "release_candidate"),
        "needs_split_review": sum(1 for row in rows if row.get("release_action") == "needs_split_review"),
        "review_candidates": sum(1 for row in rows if row.get("release_action") == "review_candidate"),
        "low_priority_review": sum(1 for row in rows if row.get("release_action") == "low_priority_review"),
        "quarantined_candidates": sum(
            1
            for row in rows
            if row.get("release_action") in {"quarantine_likely_false_positive", "quarantine_human_rejected"}
        ),
        "by_release_action": dict(Counter(str(row.get("release_action") or "unknown") for row in rows)),
        "by_release_reason": dict(Counter(str(row.get("release_reason") or "unknown") for row in rows)),
        "by_policy_bucket": dict(Counter(str(row.get("policy_bucket") or "unknown") for row in rows)),
        "by_review_status": dict(Counter(str(row.get("review_status") or "unreviewed") for row in rows)),
    }
