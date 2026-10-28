"""GEMINI-backed retrieval and constrained RAG assessment."""
import json
import logging
import math
import re
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.api import ClientAPI
from chromadb.errors import NotFoundError
from openai import APIConnectionError, APIStatusError, APITimeoutError, BadRequestError, OpenAI
from pydantic import ValidationError

from .config import Settings
from .models import ArsenalRecord, Assessment, TargetRecord, ReleasedRecord

from .linkage import agreement, score_candidates, decide

logger = logging.getLogger(__name__)


def narrative(record: TargetRecord | ArsenalRecord) -> str:
    if isinstance(record, ReleasedRecord):
        profile = " ".join(value for value in (
            f"{record.age}-year-old" if record.age is not None else "",
            record.gender or "",
        ) if value)
        parts = [f"Profile: {profile}"] if profile else []
        for label, value in (("occupation", record.occupation), ("ZIP code", record.zip_code), ("medical flag", record.medical_flag)):
            if value is not None:
                parts.append(f"{label}: {value}")
        return ("; ".join(parts) or "All profile fields suppressed") + "."
    name = f"Name: {record.name}. " if isinstance(record, ArsenalRecord) else ""
    return (f"{name}Profile: {record.age}-year-old {record.gender}; occupation: {record.occupation}; "
            f"ZIP code: {record.zip_code}; medical flag: {record.medical_flag}.")


class GeminiRAG:
    def __init__(self, settings: Settings):
        self.settings = settings
        mode = settings.rag_mode.strip().lower()
        if mode not in {"local", "gemini"}:
            raise ValueError("RAG_MODE must be either 'local' or 'gemini'.")
        self.mode = mode
        # Isolate vectors by provider/model; old indexes remain untouched.
        embedding_id = "local-256" if mode == "local" else settings.gemini_embedding_model
        self.collection_name = "arsenal_" + mode + "_" + hashlib.sha256(("profile-only-v2|" + embedding_id).encode()).hexdigest()[:16]
        self.gemini_chat_unavailable = False
        self.client: ClientAPI = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.llm = OpenAI(
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key or "missing-key",
            timeout=settings.gemini_request_timeout_seconds,
            max_retries=0,
        )

    def _require_key(self) -> None:
        if not self.settings.gemini_api_key or self.settings.gemini_api_key.startswith("your-gemini"):
            raise ValueError("GEMINI_API_KEY is missing. Copy .env.example to .env and add an Google AI Studio API key.")

    @staticmethod
    def _local_embeddings(texts: list[str], dimensions: int = 256) -> list[list[float]]:
        """Create stable, local lexical vectors for the synthetic tabular demo.

        These vectors keep the app usable when an external embedding API is
        blocked. Names are excluded so a named Arsenal record and its
        de-identified target are compared only on the supplied profile fields.
        """
        vectors = []
        for text in texts:
            profile = re.sub(r"^Name:.*?\.\s*", "", text, flags=re.IGNORECASE)
            words = re.findall(r"[a-z0-9]+", profile.lower())
            tokens = words + [f"{left}_{right}" for left, right in zip(words, words[1:])]
            vector = [0.0] * dimensions
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                slot = int.from_bytes(digest, "big") % dimensions
                vector[slot] += 1.0
            length = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / length for value in vector] if length else vector)
        return vectors

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if self.mode == "local":
            return self._local_embeddings(texts)
        self._require_key()
        try:
            response = self.llm.embeddings.create(
                model=self.settings.gemini_embedding_model,
                input=texts,
                encoding_format="float",
            )
        except APITimeoutError as exc:
            raise ValueError(
                "GEMINI embedding request timed out after "
                f"{self.settings.gemini_request_timeout_seconds:.0f} seconds. "
                "Check your network and Google AI Studio model access, then try again."
            ) from exc
        except APIConnectionError as exc:
            raise ValueError(
                "Could not connect to Google AI Studio for embeddings. Check your network connection."
            ) from exc
        items = response.data
        if len(items) != len(texts):
            raise ValueError("Gemini returned an unexpected number of embeddings. Please retry indexing.")
        # The compatibility response may omit an index (including index zero).
        # Use response position for missing indexes, while respecting explicit ones.
        indexed = [
            (position if item.index is None else item.index, item.embedding)
            for position, item in enumerate(items)
        ]
        indexes = [index for index, _ in indexed]
        if any(type(index) is not int for index in indexes) or sorted(indexes) != list(range(len(texts))):
            raise ValueError("Gemini returned ambiguous embedding indexes. Please retry indexing.")
        return [embedding for _, embedding in sorted(indexed, key=lambda pair: pair[0])]

    @staticmethod
    def _field_matches(target, metadata, field):
        return agreement(getattr(target, field), metadata.get(field), field) == 1

    @staticmethod
    def _local_assessment(target, candidates):
        ranked = score_candidates(target, candidates)
        result = decide(ranked)
        best = ranked[0] if ranked else None
        return Assessment(candidate_id=best["id"] if best else None,
            predicted_identity=str(best["metadata"].get("name", best["id"])) if best else "NO_MATCH",
            confidence=result["linkage_score"], decision=result["decision"],
            rationale="Frequency-weighted field evidence; final decision is verified against the index.")

    def _collection(self):
        return self.client.get_or_create_collection(name=self.collection_name, metadata={"hnsw:space": "cosine"})

    def index(self, records: list[ArsenalRecord]) -> int:
        documents = [narrative(record) for record in records]
        embeddings = self._embed([narrative(ReleasedRecord(**record.model_dump(exclude={"name"}))) for record in records], "passage")
        # A snapshot replaces the old Arsenal. Do not retain the old Collection
        # handle: Chroma 1.x may cache it after deletion on Windows.
        try:
            self.client.delete_collection(self.collection_name)
        except (ValueError, NotFoundError):
            # First index: there is no collection to remove.
            pass
        collection = self.client.create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )
        collection.add(
            ids=[record.id for record in records],
            documents=documents,
            embeddings=embeddings,
            metadatas=[record.model_dump() for record in records],
        )
        return collection.count()

    def retrieve(self, record: TargetRecord, top_k: int) -> list[dict]:
        collection = self._collection()
        if not collection.count():
            raise ValueError("The Arsenal is empty. Index records before running an audit.")
        result = collection.query(
            query_embeddings=self._embed([narrative(record)], "query"),
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        candidates = []
        for identifier, document, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            candidates.append({"id": identifier, "document": document, "metadata": metadata, "similarity": round(max(0.0, 1 - distance), 4)})
        return candidates

    @staticmethod
    def _parse_assessment(raw: str) -> Assessment:
        """Accept JSON mode output and gracefully handle Markdown fenced JSON."""
        clean = raw.strip()
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
        try:
            return Assessment.model_validate_json(clean)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("GEMINI returned invalid assessment JSON: %s; raw=%r", exc, raw)
            return Assessment(
                predicted_identity="NO_MATCH", confidence=0, evidence=[],
                rationale="Model response was not valid structured output.",
            )

    def _assess(self, target: TargetRecord, candidates: list[dict]) -> tuple[Assessment, int, str, str]:
        if self.mode == "local":
            assessment = self._local_assessment(target, candidates)
            return assessment, 0, "LOCAL_RULE_BASED_ASSESSMENT", "local"
        if self.gemini_chat_unavailable:
            assessment = self._local_assessment(target, candidates)
            return assessment, 0, "LOCAL_FALLBACK_AFTER_EARLIER_GEMINI_FAILURE", "local_fallback"
        self._require_key()
        context = json.dumps(candidates, ensure_ascii=False)
        prompt = f"""You are an authorised privacy red-team assessor working only on synthetic records.
Assess whether a target profile can be linked to ONE retrieved candidate. Treat retrieval as leads, not proof.
Return NO_MATCH unless evidence is strong. Do not invent facts. Return JSON only with exactly:
candidate_id (retrieved candidate ID or null), predicted_identity (candidate name or NO_MATCH), confidence (0..1), evidence (list of short factual field comparisons), rationale (short), decision (match, ambiguous, or insufficient_evidence).

Suppressed fields are absent evidence, not matches. Age ranges and postal prefixes can still match candidates within them; generalization alone does not prove anonymity.
Target: {narrative(target)}
Retrieved candidates: {context}"""
        request = dict(
            model=self.settings.gemini_model, temperature=0, max_tokens=400,
            messages=[{"role": "system", "content": "Return exactly one JSON object and nothing else. Do not reveal analysis, reasoning steps, or Markdown. Begin with { and end with }. Never claim certainty from semantic similarity alone."}, {"role": "user", "content": prompt}],
        )
        try:
            try:
                # Prefer GEMINI's OpenAI-compatible JSON-object response mode.
                response = self.llm.chat.completions.create(
                    **request, response_format={"type": "json_object"},
                    timeout=self.settings.gemini_chat_timeout_seconds,
                )
            except BadRequestError:
                logger.info("GEMINI model does not support JSON mode; using strict prompt fallback.")
                response = self.llm.chat.completions.create(
                    **request, timeout=self.settings.gemini_chat_timeout_seconds
                )
        except (APITimeoutError, APIConnectionError, APIStatusError) as exc:
            if not self.settings.gemini_fallback_to_local:
                raise ValueError(f"GEMINI chat assessment failed: {exc}") from exc
            self.gemini_chat_unavailable = True
            logger.warning("GEMINI chat assessment failed; using local evidence fallback: %s", exc)
            assessment = self._local_assessment(target, candidates)
            return assessment, 0, f"LOCAL_FALLBACK_AFTER_GEMINI_{type(exc).__name__}", "local_fallback"
        raw = response.choices[0].message.content or "{}"
        assessment = self._parse_assessment(raw)
        usage = response.usage
        return assessment, int((usage.prompt_tokens if usage else 0) + (usage.completion_tokens if usage else 0)), raw, "gemini"

    @staticmethod
    def _uniqueness_discount(candidates: list[dict]) -> float:
        if len(candidates) < 2:
            return 1.0
        margin = max(0.0, candidates[0]["similarity"] - candidates[1]["similarity"])
        # A 0.15 margin earns the full discount multiplier; ties collapse confidence.
        return min(1.0, margin / 0.15)

    @staticmethod
    def _tier(risk: float) -> str:
        if risk >= .80: return "Critical"
        if risk >= .60: return "High"
        if risk >= .35: return "Moderate"
        return "Low"

    def audit_one(self, target, top_k, comparison_tokens=None):
        started = time.perf_counter()
        candidates = self.retrieve(target, top_k)
        assessment, tokens, raw_output, assessment_mode = self._assess(target, candidates)
        population = self._collection().get(include=["metadatas"])["metadatas"]
        ranked = score_candidates(target, candidates, population)
        selected_id = ranked[0]["id"] if ranked and assessment_mode != "gemini" else assessment.candidate_id
        valid = assessment.rationale != "Model response was not valid structured output."
        if assessment_mode == "gemini" and assessment.decision == "match" and assessment.candidate_id is None:
            valid = False
        if assessment_mode == "gemini" and assessment.decision == "insufficient_evidence":
            selected_id = None
        if selected_id is not None and selected_id not in {c["id"] for c in candidates}:
            valid = False
        result = decide(ranked, selected_id=selected_id) if selected_id is not None and valid else decide([])
        if assessment_mode == "gemini" and assessment.decision == "ambiguous" and result["decision"] == "match":
            result.update(decision="ambiguous", candidate_id=None)
        selected = next((c for c in ranked if c["id"] == selected_id), None)
        verified = selected["comparisons"] if selected else []
        evidence = [f"{r['field']}: {r['status']} (target={r['target']!r}, candidate={r['candidate']!r})" for r in verified]
        score = round(result["linkage_score"], 4)
        discount = min(1.0, max(0.0, result["margin"]) / .08)
        assessment = assessment.model_copy(update={"candidate_id": result["candidate_id"],
            "predicted_identity": str(selected["metadata"].get("name", selected["id"])) if result["candidate_id"] else "NO_MATCH",
            "confidence": score, "decision": result["decision"], "evidence": evidence})
        return {
            "scoring_version": "field-evidence-v2", "score_kind": "heuristic_not_probability",
            "decision": result["decision"], "candidate_id": result["candidate_id"],
            "proposed_candidate_id": result.get("proposed_candidate_id"), "candidate_margin": result["margin"],
            "linkage_score": score, "verified_comparisons": verified, "assessment_valid": valid,
            "latency_seconds": round(time.perf_counter() - started, 6), "monetary_cost": None,
            "target_record": target.model_dump(), "top_k": top_k, "target_id": target.id,
            "engine_mode": self.mode, "assessment_mode": assessment_mode, "narrative": narrative(target),
            "assessment": assessment.model_dump(), "retrieved_candidates": candidates,
            "uniqueness_discount": round(discount, 4), "tokens_spent": tokens,
            "risk_score": score, "risk_tier": self._tier(score), "model_raw_output": raw_output,
        }

    def persist_report(self, results: list[dict]) -> dict:
        self.settings.reports_path.mkdir(parents=True, exist_ok=True)
        report = {"report_id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "records": results}
        Path(self.settings.reports_path, f"{report['report_id']}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
