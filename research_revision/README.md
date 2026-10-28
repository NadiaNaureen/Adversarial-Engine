# Paper revision evaluation

This folder contains the experiment supporting the revised six-page paper. The application and its persistent index are not modified by evaluation. All records are generated synthetic identities. Do not combine these results with the historical 40-target summary.

## Protocol and scope

Read `protocol.md` and `cloud_protocol_amendment.md` before interpreting results. The main experiment uses five independently generated 10,000-person indexes, 1,200 validation target variants, and 1,800 test variants. Target identity variants stay in one split. A target's true identity may be absent even if its attributes happen to coincide with another person.

The full-index cloud assessment subset contains 120 validation and 120 test variants across five seeds, but only 20 base identities per split. It uses locally retrieved candidates from the full 10,000-person indexes. The semantic component pilot compares local retrieval, Gemini retrieval, and Gemini retrieval plus nomination on five identical matched 150-person indexes. These pilot indexes include all present validation/test identities and are not population-scale semantic evidence. Rate limits required the amended scope. Never rank pilot results directly against the full-index table.

## Commands

Use the project's virtual environment from the project root. Cloud commands require the configured Gemini key and network access; they respect the observed free-tier quotas. Cached completed calls are reused. Do not run multiple assessment processes concurrently, because their schedulers would not share a rate limit.

```powershell
.\.venv\Scripts\python.exe -m research_revision.evaluate
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot --hash-only
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot --embeddings-only
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot
.\.venv\Scripts\python.exe -m research_revision.finalize
.\.venv\Scripts\python.exe -m unittest research_revision.test_evaluation -v
```

`evaluate --cloud` retains the original large semantic protocol for environments with sufficient quota; it was not completed here. Use the amended `cloud_pilot` workflow to reproduce the manuscript. Its hash and semantic modes share the implemented field scorer but use a standardized benchmark prompt and exact cosine retrieval, not a byte-identical dashboard run.

The scientific commands above resolve paths relative to the extracted project. The Word authoring and rendering helpers retain this workspace's reference/output paths; they are authoring utilities, not portable scientific rerun commands. The final editable paper is supplied separately.

## Evidence

- `results/<seed>/dataset.json`: synthetic population, targets, truth, splits.
- `configuration.json`: validation-selected local and FS parameters; mitigation settings.
- `raw_validation.json`, `raw_test.json`, `raw_mitigations.json`: candidate lists, scores, margins, and outcomes before operating thresholds.
- `predictions.csv`: one row per test target and baseline method.
- `mitigation_predictions.csv`, `utility.csv`: all seven release policies and their information loss and minimum k.
- `pilot_hash_*.json`, `pilot_semantic_*.json`: raw Gemini assessment, usage, validity and selected-candidate verification.
- `cloud_predictions.csv`, `pilot_configuration.json`: matched cloud test outcomes and frozen validation settings.
- `summary.json`, `paper_numbers.json`: machine-generated paper inputs.
- `reference_metadata.json` in this folder: publisher-deposited reference metadata.
- `reference_audit.md`: all 21 original citations checked and corrected.
- `results/pricing_basis.json`: dated paid-tier text-token estimate; actual billing is unavailable.

The historical 32.5% MATCH count could include wrong-person present links, but original predictions were unavailable. It is superseded rather than silently changed to 27.5%. Every new outcome table includes wrong-present links and reconciles exactly.

## Checks and interpretation

Six focused evaluation checks and 19 existing retrieval/anonymization checks passed. The pre-existing `tests/test_research.py` imports a missing legacy `research` package, so it is not evidence that the entire historical suite passes. This revision adds a separately executable runner and its own checks instead of pretending the missing package was recovered.

Minimum k uses age, postal code, occupation, and gender on the released 60-person cohort. Medical flag is excluded from k but included in the strong linkage attacker. Utility loss is a defined synthetic-data measure, not a downstream predictive task. Model prose and timing may vary between executions. No calibrated identification probability, differential privacy guarantee, universal superiority, or real-world population estimate follows from these experiments.
