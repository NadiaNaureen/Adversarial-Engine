import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.anonymization import compare, variants
from app.config import Settings
from app.demo import ARSENAL, TARGETS
from app.models import ReleasedRecord
from app.rag import GeminiRAG, narrative


def test_previews_and_semantic_matching():
    target = TARGETS[0]
    assert narrative(ReleasedRecord(**target.model_dump())) == narrative(target)
    plans = list(variants(target))
    age = plans[0]["preview"]
    assert age.age == "30-39"
    assert GeminiRAG._field_matches(age, ARSENAL[0].model_dump(), "age")
    assert not GeminiRAG._field_matches(age, {"age": 42}, "age")
    postal = plans[1]["preview"]
    assert postal.zip_code == "560*"
    assert GeminiRAG._field_matches(postal, {"zip_code": "560999"}, "zip_code")
    assert not GeminiRAG._field_matches(postal, {"zip_code": "110001"}, "zip_code")
    combined = plans[-1]["preview"]
    assert "medical" not in narrative(combined) and "occupation" not in narrative(combined)
    assert not GeminiRAG._field_matches(combined, {"medical_flag": None}, "medical_flag")
    assert target.age == 34 and target.medical_flag == "asthma"


def test_local_comparison_preserves_index_and_cost(tmp_path):
    rag = GeminiRAG(Settings(_env_file=None, rag_mode="local", chroma_path=tmp_path))
    rag.index(ARSENAL)
    before = rag._collection().get()
    result = compare(rag, TARGETS[0], 4)
    assert len(result["recommendations"]) == 5
    assert before == rag._collection().get()
    for plan in result["recommendations"]:
        assert plan["comparable"]
        assert plan["reduction_points"] == round(100 * (result["baseline"]["risk_score"] - plan["result"]["risk_score"]), 2)
        assert "id" not in plan["preview"]
        assert all(value is not None for value in plan["preview"].values())
    combined = next(p for p in result["recommendations"] if p["id"] == "combined")
    assert combined["result"]["decision"] == "match"  # Remaining evidence can still link this demo record.
    assert combined["result"]["risk_score"] == combined["result"]["linkage_score"]
    assert combined["result"]["risk_score"] != .3
    rag.llm.close()


def outcome(score=.5, mode="gemini", rationale="Evidence"):
    return {"risk_score": score, "tokens_spent": 123, "assessment_mode": mode,
            "assessment": {"rationale": rationale}}


def test_failures_and_increases_are_not_claimed_as_reductions():
    rag = Mock()
    rag.audit_one.side_effect = [outcome(), outcome(.6), outcome(.2, "local_fallback"),
                                RuntimeError("unavailable"), outcome(.2, rationale="Model response was not valid structured output."), outcome(.3)]
    result = compare(rag, TARGETS[0], 4)
    plans = {p["id"]: p for p in result["recommendations"]}
    assert plans["age_band"]["reduction_points"] == -10
    assert plans["postal_prefix"]["reduction_points"] is None
    assert plans["medical_suppression"]["reduction_points"] is None
    assert plans["occupation_suppression"]["reduction_points"] is None
    assert plans["combined"]["reduction_points"] == 20
    for call in rag.audit_one.call_args_list[1:]:
        assert call.kwargs == {}  # Costs no longer enter linkage evidence.


def test_api_persists_comparison_and_handles_old_report(tmp_path, monkeypatch):
    import app.main as main
    settings = Settings(_env_file=None, rag_mode="local", chroma_path=tmp_path / "vectors", reports_path=tmp_path / "reports")
    rag = GeminiRAG(settings)
    rag.index(ARSENAL)
    report = rag.persist_report([rag.audit_one(TARGETS[0], 4)])
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "service", lambda: rag)
    with TestClient(main.app) as client:
        response = client.post("/api/anonymize", json={"report_id": report["report_id"], "record_index": 0})
        assert response.status_code == 200
        data = response.json()
        saved = settings.reports_path / "anonymization" / (data["comparison_id"] + ".json")
        assert json.loads(saved.read_text()) == data
        assert client.post("/api/anonymize", json={"report_id": "../bad", "record_index": 0}).status_code == 422
        assert client.post("/api/anonymize", json={"report_id": report["report_id"], "record_index": 99}).status_code == 404
        old = rag.persist_report([{"risk_score": .5}])
        assert client.post("/api/anonymize", json={"report_id": old["report_id"], "record_index": 0}).status_code == 400
    rag.llm.close()
