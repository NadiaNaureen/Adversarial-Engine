# Adversarial Re-identification RAG Engine

An authorised, synthetic-data privacy red-team application. It tests how easily a de-identified record can be linked to a simulated external knowledge base (the **Arsenal**). It is not designed for real personal data or breached data.

## What changed from the prototype

This is a retrieval-augmented assessment design:

- Gemini `gemini-embedding-001` generates passage and query embeddings.
- ChromaDB persists Arsenal vectors locally in `chroma_data/`.
- Gemini chat completion receives only the top retrieved candidates and returns a schema-validated assessment.
- Candidate-ID validation, programmatic field comparisons, and an explicit ambiguity decision reduce unsupported identity claims.
- Each audit persists an evidence-rich JSON report in `reports/`.

## Running without Gemini delays

The application defaults to `RAG_MODE=gemini`, using cloud embeddings and chat assessment. Set `RAG_MODE=local` for a fast offline synthetic demo with local vectors and evidence-only assessment.

In Gemini mode, a failed chat request automatically falls back to local evidence assessment after 20 seconds. Reports label this as `local_fallback`; its token count is `0`. A report is labelled `gemini` only when Gemini returned a completed response and its token count is real.

## Setup

Requires Python 3.11+ and an Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

The default assessment model is `gemini-3.5-flash-lite`. Configure it with `GEMINI_MODEL`; configure embeddings with `GEMINI_EMBEDDING_MODEL`. Both use Google's [OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai) through the existing SDK.
Embedding requests fail after 120 seconds rather than leaving the dashboard waiting indefinitely. Set `GEMINI_REQUEST_TIMEOUT_SECONDS` in `.env` if your network needs a longer limit.

```powershell
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Always use `python -m uvicorn`, rather than a globally installed `uvicorn`; this guarantees it runs from the activated `.venv` where ChromaDB is installed.

Open `http://127.0.0.1:8000`. Click **Load synthetic demo data**, then **Index Arsenal**, then **Run audit**. The first indexing operation calls Gemini's embedding API; re-indexing the same source replaces the collection deterministically.

After migration, index your Arsenal again. Collections are isolated by mode and embedding model so previous vectors cannot be mixed with Gemini vectors. Existing reports remain available.

## API

- `GET /api/health` - runtime and configuration status (never reveals the key).
- `POST /api/demo/load` - loads harmless synthetic target and Arsenal records.
- `POST /api/index` - indexes `arsenal_records` into persistent ChromaDB.
- `POST /api/audit` - runs retrieval, LLM assessment, scoring, and JSON report persistence.
- `GET /api/reports` and `GET /api/reports/{report_id}` - audit history.

## Data contract

`/api/index` accepts `{ "arsenal_records": [{"id", "name", "age", "zip_code", "occupation", "gender", "medical_flag"}] }`.

`/api/audit` accepts `{ "target_records": [{"id", "age", "zip_code", "occupation", "gender", "medical_flag"}], "top_k": 4 }`.

Use only synthetic data or data you have explicit authorization to test. The model is instructed to return `NO_MATCH` unless evidence supports a candidate; reports are risk assessments, not proof of identity.

## CSV and Excel upload

The dashboard accepts `.csv`, `.xlsx`, and `.xlsm` files. Upload one **Arsenal** file (requires `name`) and one de-identified **target** file. Target column headers are `id, age, zip_code, occupation, gender, medical_flag`; the Arsenal file also requires `name`. Store ZIP codes as text so leading zeroes are retained.


## Record-specific anonymization experiments

After running an audit, click **Find anonymization options** on a record. The app tests ten-year age bands, postal prefixes, medical-field suppression, occupation suppression, and a combined transformation. Each option includes the actual field changes, a record-specific explanation, information lost, re-audit evidence, and a downloadable transformed JSON record (without the original ID or suppressed fields). Original input and the Arsenal are unchanged.

The original is re-audited against the current index to establish a fresh baseline. All five variants use the same field-evidence scoring formula. Token cost is separate. Differences are score points on a 0-100 scale, not calibrated probabilities or observed attack success. Increases and unchanged scores are retained; fallback, invalid responses, and errors are not reported as successful reductions. Local mode respects age-range and postal-prefix compatibility instead of treating generalized values as automatic mismatches. Gemini mode performs six embedding calls and up to six assessments, plus existing JSON-mode retries. Model variability and incomplete background knowledge limit interpretation.

POST /api/anonymize accepts report_id and record_index. New audit reports retain target values for reproducibility. Comparison reports are saved under reports/anonymization and contain original data; the separate transformed-record download excludes those originals. Run a new audit for reports created before this feature.

Techniques are based on [ICO guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/) and [NIST SP 800-188](https://csrc.nist.gov/pubs/sp/800/188/final). Generalization broadens released values; suppression removes fields. These experiments do not establish dataset-wide k-anonymity, l-diversity, differential privacy, or guaranteed anonymity. Postal prefixes are string generalizations, not verified geographic boundaries. Hashing an identifier alone does not remove linkage through the remaining fields.


## Research evaluation (scoring version 2)

The dashboard reports `match`, `ambiguous`, or `insufficient_evidence`. The score
is verified field evidence, **not an identification probability**. Strong evidence
can remain ambiguous when several candidates agree. Failure to identify does not
prove anonymity. Tokens and latency are separate; monetary cost is unavailable
unless measured externally. The legacy `risk_score` and `confidence` fields are
compatibility aliases for the heuristic evidence score. Earlier reports retain
their original scoring and must not be pooled with version 2 reports.

The reproducible October 2026 paper revision is in
[research_revision/README.md](research_revision/README.md). It contains five
10,000-candidate synthetic populations, identity-disjoint validation/test
targets, noisy conditions, baselines, prediction exports, and separately scoped
live Gemini experiments. Results are in `research_revision/results/`.
The earlier README's `research/` and `reports/benchmarks/` paths are absent from
this checkout and must not be cited as completed evidence. No real-world UCI
experiment is claimed by this revision.

```powershell
.\.venv\Scripts\python.exe -m research_revision.evaluate
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot --hash-only
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot --embeddings-only
.\.venv\Scripts\python.exe -m research_revision.cloud_pilot
.\.venv\Scripts\python.exe -m research_revision.finalize
.\.venv\Scripts\python.exe -m unittest research_revision.test_evaluation -v
```


## Expanded local evaluation for the second review

`second_review_work/` contains the expanded local evaluation used in the revised
paper: five populations of 10,000 synthetic identities, 200 present and 200
absent validation identities per seed, and 300 present and 300 absent test
identities per seed. Six conditions produce 12,000 validation variants and
18,000 test variants. The small cloud cohorts in `research_revision/` are
unchanged.

From the project root, with the dependencies installed, run:

```powershell
python second_review_work/run_expanded.py
python second_review_work/supplement.py
```

The first command reuses completed per-seed outputs when present. The supplement
adds policy-specific adaptive re-audits and descriptive matched-FPR comparisons.
`second_review_work/results/<seed>/` retains datasets, configurations, prediction
exports, comparison curves, and adaptive outcomes. The earlier experiment in
`research_revision/` remains available separately. Manuscript authoring scripts
may contain local output paths; they are not required to run the application.

API keys, local environments, the persistent application database, audit reports,
and manuscript/rendering outputs are excluded from this repository.
