# Multi-Source Candidate Data Transformer

A deterministic Python pipeline that ingests candidate data from multiple sources (CSV, ATS JSON, PDF/DOCX resumes, recruiter notes) and produces one canonical profile per candidate — deduplicated, normalised, with full provenance and confidence scoring.

---

## Setup

```bash
cd candidate-transformer
pip install -e .
```

---

## Run

```bash
# Default schema — print to terminal
python -m transformer --inputs samples/

# Default schema — save to file
python -m transformer --inputs samples/ --out outputs/output_default.json

# Recruiter view (6 fields, no provenance)
python -m transformer --inputs samples/ --config configs/recruiter_view.json --out outputs/output_custom.json

# Detailed view (9 fields, full provenance)
python -m transformer --inputs samples/ --config configs/detailed_view.json --out outputs/output_detailed.json

# Include broken/malformed fixtures — shows graceful degradation
python -m transformer --inputs samples/ --include-broken --verbose

# Run tests
pytest
```

---

## Output files

| File | Description |
|---|---|
| `outputs/output_default.json` | All 14 profiles, full default schema (15 fields) |
| `outputs/output_custom.json` | Recruiter view — 6 fields, no provenance |
| `outputs/output_detailed.json` | Detailed view — 9 fields, full provenance per field |

---

## Project layout

```
samples/
  structured/          # recruiter_export.csv, ats_blob.json
  unstructured/
    resumes/           # PDF + DOCX resumes (one per candidate)
    notes/             # .txt recruiter notes
  broken/              # malformed.json, empty.csv (graceful-degradation fixtures)

configs/
  recruiter_view.json  # 6-field projection, include_provenance: false
  detailed_view.json   # 9-field projection, include_provenance: true
  bad_config.json      # intentional typo — demonstrates config validation error

outputs/               # generated output files (committed for reference)

tests/                 # pytest test suite (420 tests)
gold/                  # gold profile JSON files used by test_gold_profiles.py
```
