"""Deterministic synthetic privacy-test data with known linkage ground truth."""
import random

from .models import ArsenalRecord, TargetRecord

FIRST_NAMES = ["Asha", "Rohan", "Nila", "Vikram", "Kabir", "Meera", "Arjun", "Isha", "Dev", "Tara", "Kiran", "Leena"]
LAST_NAMES = ["Raman", "Mehta", "Thomas", "Shah", "Bose", "Iyer", "Kapoor", "Nair", "Singh", "Das", "Rao", "Malhotra"]
OCCUPATIONS = ["Civil engineer", "Marine biologist", "School counselor", "Data analyst", "Pharmacist", "Architect", "Teacher", "Nurse", "Accountant", "Researcher"]
ZIP_CODES = ["110001", "400001", "560001", "600001", "682001", "700001", "500001", "380001", "302001", "781001"]
MEDICAL_FLAGS = ["none", "asthma", "diabetes", "hypertension", "allergy"]
GENDERS = ["woman", "man", "nonbinary"]


def _profile(rng: random.Random, used: set[tuple]) -> dict:
    while True:
        record = {
            "age": rng.randint(22, 68), "zip_code": rng.choice(ZIP_CODES),
            "occupation": rng.choice(OCCUPATIONS), "gender": rng.choice(GENDERS),
            "medical_flag": rng.choice(MEDICAL_FLAGS),
        }
        key = tuple(record.values())
        if key not in used:
            used.add(key)
            return record


def generate_synthetic_data(record_count: int, planted_match_rate: float, seed: int) -> dict:
    """Create only synthetic profiles; exact target-Arsenal links are recorded separately."""
    rng = random.Random(seed)
    used: set[tuple] = set()
    arsenal = []
    for number in range(1, record_count + 1):
        profile = _profile(rng, used)
        arsenal.append(ArsenalRecord(
            id=f"a-{number:04d}", name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}", **profile
        ))
    match_count = round(record_count * planted_match_rate)
    matched_arsenal_indices = rng.sample(range(record_count), match_count)
    targets, ground_truth = [], {}
    for number in range(1, record_count + 1):
        target_id = f"t-{number:04d}"
        if number <= match_count:
            source = arsenal[matched_arsenal_indices[number - 1]]
            targets.append(TargetRecord(id=target_id, **source.model_dump(exclude={"id", "name"})))
            ground_truth[target_id] = source.id
        else:
            targets.append(TargetRecord(id=target_id, **_profile(rng, used)))
            ground_truth[target_id] = None
    return {
        "arsenal_records": [record.model_dump() for record in arsenal],
        "target_records": [record.model_dump() for record in targets],
        "ground_truth": ground_truth,
        "summary": {"record_count": record_count, "planted_matches": match_count, "absent_identity_targets": record_count - match_count, "seed": seed},
    }
