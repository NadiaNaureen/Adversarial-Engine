"""Record-level generalization/suppression experiments, not privacy guarantees."""
from .models import ReleasedRecord, TargetRecord

SOURCES = [
    {"title": "ICO: effective anonymisation", "url": "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/"},
    {"title": "NIST SP 800-188: de-identification", "url": "https://csrc.nist.gov/pubs/sp/800/188/final"},
]


def variants(target: TargetRecord):
    original = target.model_dump()
    age_band = f"{target.age // 10 * 10}-{min(120, target.age // 10 * 10 + 9)}"
    prefix = target.zip_code[:3] + "*" if len(target.zip_code) > 3 else None
    plans = [
        ("age_band", "Generalize age to a ten-year band", {"age": age_band},
         f"Age {target.age} becomes {age_band}; nearby ages can now satisfy the same age clue.", "Exact-age analysis is lost; age-group analysis remains."),
        ("postal_prefix", "Generalize the postal code", {"zip_code": prefix},
         f"Postal code {target.zip_code} becomes a prefix shared by more locations (or is suppressed if already short). Other clues may still identify this record.", "Fine location analysis is lost; a prefix is not a verified administrative region."),
        ("medical_suppression", "Suppress the medical flag", {"medical_flag": None},
         f"Remove the medical value {target.medical_flag!r} from the released record so it cannot be used as a direct matching clue.", "Condition-specific analysis is unavailable; other fields may still allow inference."),
        ("occupation_suppression", "Suppress the occupation", {"occupation": None},
         f"Remove {target.occupation!r}, which can narrow the candidate pool when combined with age and location.", "Occupation-based analysis is unavailable."),
        ("combined", "Combine generalization and suppression", {"age": age_band, "zip_code": prefix, "occupation": None, "medical_flag": None},
         "Weaken age and location together and remove occupation and medical clues; changing only one field can leave the remaining combination distinctive.", "Retains age bands, postal prefixes and gender, but loses detailed occupation and health analysis."),
    ]
    for identifier, title, changes, why, loss in plans:
        yield {"id": identifier, "title": title, "why": why, "utility_tradeoff": loss,
               "changes": [{"field": field, "before": original[field], "after": value} for field, value in changes.items()],
               "preview": ReleasedRecord(**(original | changes))}


def compare(rag, target: TargetRecord, top_k: int):
    # Re-run the original against the current index; cost is separate from evidence.
    baseline = rag.audit_one(target, top_k)
    recommendations = []
    for plan in variants(target):
        preview = plan.pop("preview")
        plan["preview"] = preview.model_dump(exclude={"id"}, exclude_none=True)
        try:
            result = rag.audit_one(preview, top_k)
            valid = (result.get("assessment_valid", True) and baseline.get("assessment_valid", True)
                     and result["assessment_mode"] == baseline["assessment_mode"]
                     and result["assessment_mode"] in {"local", "gemini"}
                     and all(row["assessment"]["rationale"] != "Model response was not valid structured output."
                             for row in (baseline, result)))
            plan["result"] = result
            plan["comparable"] = valid
            plan["reduction_points"] = round(100 * (baseline["risk_score"] - result["risk_score"]), 2) if valid else None
            plan["status"] = ("Measured reduction" if plan["reduction_points"] > 0 else "No measured reduction") if valid else "Inconclusive: assessment failed or changed mode"
        except Exception:
            plan.update(comparable=False, reduction_points=None, status="Evaluation failed; retry this comparison later.")
        recommendations.append(plan)
    recommendations.sort(key=lambda item: (item["reduction_points"] is not None, item["reduction_points"] or 0), reverse=True)
    return {"target_id": target.id, "baseline": baseline, "recommendations": recommendations,
            "sources": SOURCES,
            "method": "Original and transformed records are re-audited against the current Arsenal. Cost is reported separately. Differences are heuristic score points on a 0-100 scale, not probabilities or measured attack success. Ground-truth evaluation is available in the benchmark runner. Single model runs can vary; fallback or invalid responses are inconclusive.",
            "limitations": "These record-level transformations do not establish dataset-wide k-anonymity, l-diversity, or differential privacy. Remaining fields may still identify a person. An unsuccessful or ambiguous attack is not proof of anonymity. Downloads omit the record ID and suppressed fields; local audit reports retain originals for comparison."}
