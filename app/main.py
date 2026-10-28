import json
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .demo import ARSENAL, TARGETS
from .models import ArsenalRecord, AuditRequest, IndexRequest, SyntheticRequest, TargetRecord
from .rag import GeminiRAG
from .anonymization import compare
from .models import AnonymizationRequest
from uuid import uuid4
from .synthetic import generate_synthetic_data
from .tabular import parse_upload

app = FastAPI(title="Adversarial Re-identification RAG Engine", version="1.0.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def service() -> GeminiRAG:
    return GeminiRAG(settings)


@app.get("/", include_in_schema=False)
def root(): return FileResponse("app/static/index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "rag_mode": settings.rag_mode.strip().lower(), "gemini_configured": bool(settings.gemini_api_key and not settings.gemini_api_key.startswith("your-gemini")), "chat_model": settings.gemini_model, "embedding_model": settings.gemini_embedding_model, "request_timeout_seconds": settings.gemini_request_timeout_seconds}

@app.post("/api/demo/load")
def load_demo():
    return {"arsenal_records": [r.model_dump() for r in ARSENAL], "target_records": [r.model_dump() for r in TARGETS]}


@app.post("/api/upload/arsenal")
async def upload_arsenal(file: UploadFile = File(...)):
    records = await parse_upload(file, ArsenalRecord)
    return {"arsenal_records": [record.model_dump() for record in records]}


@app.post("/api/upload/targets")
async def upload_targets(file: UploadFile = File(...)):
    records = await parse_upload(file, TargetRecord)
    return {"target_records": [record.model_dump() for record in records]}


@app.post("/api/synthetic/generate")
def generate_synthetic(request: SyntheticRequest):
    return generate_synthetic_data(request.record_count, request.planted_match_rate, request.seed)

@app.post("/api/index")
def index(request: IndexRequest):
    try: return {"indexed_records": service().index(request.arsenal_records)}
    except ValueError as exc: raise HTTPException(400, str(exc))
    except Exception as exc: raise HTTPException(502, f"GEMINI indexing request failed: {exc}")

@app.post("/api/audit")
def audit(request: AuditRequest):
    try:
        rag = service()
        return rag.persist_report([rag.audit_one(record, request.top_k) for record in request.target_records])
    except ValueError as exc: raise HTTPException(400, str(exc))
    except Exception as exc: raise HTTPException(502, f"GEMINI RAG assessment failed: {exc}")

@app.get("/api/reports")
def reports():
    if not settings.reports_path.exists(): return []
    return [{"report_id": p.stem, "created_at": p.stat().st_mtime} for p in sorted(settings.reports_path.glob("*.json"), reverse=True)]

@app.get("/api/reports/{report_id}")
def report(report_id: str):
    if not report_id.replace("-", "").isalnum(): raise HTTPException(400, "Invalid report id")
    path = Path(settings.reports_path, f"{report_id}.json")
    if not path.exists(): raise HTTPException(404, "Report not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/anonymize")
def anonymize(request: AnonymizationRequest):
    source = settings.reports_path / f"{request.report_id}.json"
    if not source.exists():
        raise HTTPException(404, "Audit report not found. Run an audit first.")
    report_data = json.loads(source.read_text(encoding="utf-8"))
    records = report_data.get("records", [])
    if request.record_index >= len(records):
        raise HTTPException(404, "Record not found in this report.")
    original = records[request.record_index]
    if "target_record" not in original:
        raise HTTPException(400, "Run a new audit to enable anonymization for this older report.")
    try:
        result = compare(service(), TargetRecord.model_validate(original["target_record"]), original.get("top_k", 4))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, "Anonymization evaluation failed. Check the server connection and retry.") from exc
    result["original_audit_score"] = original["risk_score"]
    result["source_report_id"] = request.report_id
    result["comparison_id"] = str(uuid4())
    directory = settings.reports_path / "anonymization"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{result['comparison_id']}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
