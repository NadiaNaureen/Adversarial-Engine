from typing import Literal
from pydantic import BaseModel, Field, field_validator


class TargetRecord(BaseModel):
    id: str
    age: int = Field(ge=0, le=120)
    zip_code: str
    occupation: str
    gender: str
    medical_flag: str = "unknown"


class ArsenalRecord(TargetRecord):
    name: str


class IndexRequest(BaseModel):
    arsenal_records: list[ArsenalRecord] = Field(min_length=1)


class AuditRequest(BaseModel):
    target_records: list[TargetRecord] = Field(min_length=1)
    top_k: int = Field(default=4, ge=2, le=10)


class SyntheticRequest(BaseModel):
    record_count: int = Field(default=40, ge=4, le=500)
    planted_match_rate: float = Field(default=.4, ge=0, le=1)
    seed: int = Field(default=42, ge=0)


class Assessment(BaseModel):
    candidate_id: str | None = None
    decision: Literal["match", "ambiguous", "insufficient_evidence"] = "insufficient_evidence"
    predicted_identity: str = "NO_MATCH"
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    rationale: str = ""


class Tier(str):
    pass


class ReleasedRecord(BaseModel):
    """Internal release preview; null means the field is suppressed."""
    id: str
    age: int | str | None
    zip_code: str | None
    occupation: str | None
    gender: str | None
    medical_flag: str | None


    @field_validator("age")
    @classmethod
    def valid_age(cls, value):
        if value is None:
            return value
        if isinstance(value, int):
            if not 0 <= value <= 120:
                raise ValueError("Age must be between 0 and 120.")
            return value
        import re
        if not re.fullmatch(r"[0-9]{1,3}-[0-9]{1,3}", value):
            raise ValueError("Generalized age must be a low-high interval.")
        low, high = map(int, value.split("-"))
        if not 0 <= low <= high <= 120:
            raise ValueError("Invalid age interval.")
        return value


# Released records can contain generalized ages, but never malformed intervals.
class AnonymizationRequest(BaseModel):
    report_id: str = Field(pattern=r"^[a-zA-Z0-9-]+$")
    record_index: int = Field(ge=0)
