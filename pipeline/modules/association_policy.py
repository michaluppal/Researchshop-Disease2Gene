"""Association type and result-group policy for pipeline outputs."""

from __future__ import annotations

from typing import Dict, Iterable


ASSOCIATION_GROUP_ORDER = {
    "Primary Genetic Association": 0,
    "Biomarker/Response Signal": 1,
    "Mechanistic/Pathway Signal": 2,
    "Animal Model Signal": 3,
    "Figure-Derived Signal": 4,
    "Other Candidate Signal": 5,
    "Review Needed": 6,
}


def association_group_for_type(association_type: str) -> str:
    type_name = str(association_type or "").strip()
    if type_name in {"variant_association", "susceptibility_gene"}:
        return "Primary Genetic Association"
    if type_name == "mechanistic_pathway_gene":
        return "Mechanistic/Pathway Signal"
    if type_name == "animal_model_gene":
        return "Animal Model Signal"
    if type_name in {"biomarker_response_gene", "mechanistic_or_biomarker_gene", "biomarker_gene"}:
        return "Biomarker/Response Signal"
    if type_name == "figure_derived_gene":
        return "Figure-Derived Signal"
    if type_name in {"review_needed", "deterministic_candidate"}:
        return "Review Needed"
    return "Other Candidate Signal"


def count_association_groups(items: Iterable[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        group = str(item.get("association_group") or "").strip()
        if not group:
            group = association_group_for_type(str(item.get("association_type") or ""))
        counts[group] = counts.get(group, 0) + 1
    return counts
