"""Auditable linkage heuristics. Scores are not calibrated probabilities."""
import math
from difflib import SequenceMatcher

FIELDS = ("age", "zip_code", "occupation", "gender", "medical_flag")
MISSING = {"", "unknown", "?", "null"}


def observed(value):
    return value is not None and str(value).strip().casefold() not in MISSING


def agreement(value, other, field, fuzzy=False):
    if not observed(value) or not observed(other):
        return None
    left, right = str(value).strip().casefold(), str(other).strip().casefold()
    if field == "age" and "-" in left:
        try:
            low, high = map(int, left.split("-"))
            return float(low <= int(right) <= high)
        except ValueError:
            return 0.0
    if field == "zip_code" and left.endswith("*"):
        return float(right.startswith(left[:-1]))
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio() if fuzzy and field == "occupation" else 0.0


def score_candidates(target, candidates, population=None, fuzzy=False):
    """Frequency-weighted compatibility with explicit contradictions and coverage.

    Frequencies use the full index, never labels. No independence or probability
    claim is made. A generalized value's frequency includes all compatible values.
    """
    values = target.model_dump() if hasattr(target, "model_dump") else target
    population = population if population is not None else [c["metadata"] for c in candidates]
    weights = {}
    for field in FIELDS:
        value = values.get(field)
        frequency = sum(agreement(value, row.get(field), field) == 1 for row in population)
        weights[field] = 1 + min(3.0, math.log((len(population) + 1) / (frequency + 1)))
    ranked = []
    for candidate in candidates:
        support = contradiction = available = 0.0
        comparisons = []
        for field in FIELDS:
            value, other = values.get(field), candidate["metadata"].get(field)
            match = agreement(value, other, field, fuzzy)
            status = "missing" if match is None else "compatible" if match == 1 else "partial" if match > 0 else "contradiction"
            comparisons.append({"field": field, "target": value, "candidate": other, "status": status})
            if match is not None:
                available += 1
                support += weights[field] * match
                contradiction += weights[field] * (1 - match)
        denominator = support + contradiction
        score = max(0.0, (support - contradiction) / denominator) if denominator else 0.0
        # Continuous evidence coverage, not a four-field acceptance cliff.
        score *= math.sqrt(available / len(FIELDS))
        ranked.append({**candidate, "linkage_score": round(score, 6), "comparisons": comparisons})
    return sorted(ranked, key=lambda c: (-c["linkage_score"], str(c["id"])))


def decide(ranked, threshold=.65, margin=.08, selected_id=None, use_margin=True):
    selected = next((c for c in ranked if c["id"] == selected_id), None) if selected_id is not None else next(iter(ranked), None)
    if selected is None:
        return {"decision": "insufficient_evidence", "candidate_id": None, "linkage_score": 0.0, "margin": 0.0}
    competitor = max((c["linkage_score"] for c in ranked if c["id"] != selected["id"]), default=0.0)
    gap = selected["linkage_score"] - competitor
    decision = "insufficient_evidence" if selected["linkage_score"] < threshold else "ambiguous" if use_margin and gap <= margin else "match"
    return {"decision": decision, "candidate_id": selected["id"] if decision == "match" else None,
            "proposed_candidate_id": selected["id"], "linkage_score": selected["linkage_score"], "margin": round(gap, 6)}
