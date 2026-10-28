from .models import ArsenalRecord, TargetRecord

ARSENAL = [
    ArsenalRecord(id="a-001", name="Asha Raman", age=34, zip_code="560001", occupation="Orthopedic surgeon", gender="woman", medical_flag="asthma"),
    ArsenalRecord(id="a-002", name="Rohan Mehta", age=42, zip_code="110001", occupation="Civil engineer", gender="man", medical_flag="diabetes"),
    ArsenalRecord(id="a-003", name="Nila Thomas", age=29, zip_code="682001", occupation="Marine biologist", gender="woman", medical_flag="none"),
    ArsenalRecord(id="a-004", name="Vikram Shah", age=34, zip_code="560001", occupation="Orthopedic surgeon", gender="man", medical_flag="none"),
    ArsenalRecord(id="a-005", name="Kabir Bose", age=51, zip_code="700001", occupation="Archivist", gender="man", medical_flag="hypertension"),
]

TARGETS = [
    TargetRecord(id="t-001", age=34, zip_code="560001", occupation="Orthopedic surgeon", gender="woman", medical_flag="asthma"),
    TargetRecord(id="t-002", age=42, zip_code="110001", occupation="Civil engineer", gender="man", medical_flag="diabetes"),
    TargetRecord(id="t-003", age=29, zip_code="682001", occupation="Marine biologist", gender="woman", medical_flag="none"),
    TargetRecord(id="t-004", age=38, zip_code="400001", occupation="School counselor", gender="woman", medical_flag="none"),
]

