from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidatePolicyParams:
    false_positive_confidence: float = 0.45
    low_priority_confidence: float = 0.65
    auto_candidate_min_confidence: float = 0.80
    auto_candidate_max_confidence: float = 0.95
    auto_candidate_max_members: int = 5
    min_auto_fill_ratio: float = 0.15
    split_risk_min_members: int = 9
    split_risk_low_fill_ratio: float = 0.15
    split_risk_low_fill_min_members: int = 2


def _float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None or value == "":
        return default
    return float(value)


def _int(row: dict[str, Any], key: str, default: int = 0) -> int:
    value = row.get(key)
    if value is None or value == "":
        return default
    return int(value)


def classify_whole_cloud_candidate(
    row: dict[str, Any],
    params: CandidatePolicyParams | None = None,
) -> dict[str, Any]:
    """Assign a review/export policy bucket to one whole-cloud candidate.

    These rules are deliberately conservative. They are calibrated from the
    2026-04-28 reviewed whole-cloud pass, where very low confidence was nearly
    always junk, mid/high confidence with modest member count was usually good,
    and very large/high-member groups were often overmerged.
    """
    params = params or CandidatePolicyParams()
    confidence = _float(row, "whole_cloud_confidence", _float(row, "confidence"))
    member_count = _int(row, "member_count", 1)
    fill_ratio = _float(row, "group_fill_ratio", 1.0)

    if confidence < params.false_positive_confidence:
        return {
            "policy_bucket": "likely_false_positive",
            "policy_reason": f"whole_cloud_confidence<{params.false_positive_confidence:.2f}",
            "deliverable_candidate": False,
            "needs_human_review": False,
            "needs_split_review": False,
        }

    if (
        member_count >= params.split_risk_min_members
        or (
            member_count >= params.split_risk_low_fill_min_members
            and fill_ratio < params.split_risk_low_fill_ratio
        )
    ):
        return {
            "policy_bucket": "needs_split_review",
            "policy_reason": (
                f"member_count>={params.split_risk_min_members} "
                f"or fill_ratio<{params.split_risk_low_fill_ratio:.2f}"
            ),
            "deliverable_candidate": False,
            "needs_human_review": True,
            "needs_split_review": True,
        }

    if (
        params.auto_candidate_min_confidence <= confidence < params.auto_candidate_max_confidence
        and member_count <= params.auto_candidate_max_members
        and fill_ratio >= params.min_auto_fill_ratio
    ):
        return {
            "policy_bucket": "auto_deliverable_candidate",
            "policy_reason": (
                f"{params.auto_candidate_min_confidence:.2f}<=confidence"
                f"<{params.auto_candidate_max_confidence:.2f}, "
                f"member_count<={params.auto_candidate_max_members}, "
                f"fill_ratio>={params.min_auto_fill_ratio:.2f}"
            ),
            "deliverable_candidate": True,
            "needs_human_review": False,
            "needs_split_review": False,
        }

    if confidence < params.low_priority_confidence:
        return {
            "policy_bucket": "low_priority_review",
            "policy_reason": f"confidence<{params.low_priority_confidence:.2f}",
            "deliverable_candidate": False,
            "needs_human_review": True,
            "needs_split_review": False,
        }

    return {
        "policy_bucket": "review_candidate",
        "policy_reason": "falls outside high-trust and high-risk rules",
        "deliverable_candidate": False,
        "needs_human_review": True,
        "needs_split_review": False,
    }
