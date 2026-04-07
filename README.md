# Ctrl+Alt+Heal

### Find what the chart says but the codes don't.

A SHARP-compliant MCP server for clinical gap detection — identifying missed diagnosis codes by analyzing patient records from any FHIR R4 server.

## What it does

Ctrl+Alt+Heal exposes clinical gap detection as reusable MCP tools that any healthcare AI agent can invoke. It reads a patient's complete clinical record via FHIR REST API and identifies conditions that are documented but never coded.

### MCP Tools

| Tool | Description |
|------|-------------|
| `detect_coding_gaps` | Run full gap detection pipeline on a patient |
| `get_patient_summary` | Structured clinical summary (demographics, labs, meds, conditions) |
| `validate_gap` | Validate a gap against MEAT criteria (Monitoring, Evaluation, Assessment, Treatment) |
| `list_detected_gaps` | Query cached gaps with filters |
| `draft_physician_query` | Generate audit-ready physician query for a gap |

### Detection Pipeline

- **TIER 1 (Structured):** LOINC lab thresholds → ICD-10 mapping (HbA1c ≥ 6.5 → E11.65)
- **TIER 2 (Phenotype):** PheKB-style rules combining meds + labs + note patterns
- **TIER 3 (NER):** Clinical note pattern matching with negation and section detection

## SHARP Compliance

The server implements the [SHARP-on-MCP](https://www.sharponmcp.com/) specification:

- Advertises `fhir_context_required: true` in initialize response
- Reads `X-FHIR-Server-URL`, `X-FHIR-Access-Token`, `X-Patient-ID` headers
- Connects to any FHIR R4 server (HAPI, Epic, Cerner)

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/ctrl-alt-heal.git
cd ctrl-alt-heal

# Install
pip install -r requirements.txt

# Run (with a public HAPI FHIR server)
export FHIR_SERVER_URL=https://hapi.fhir.org/baseR4
python mcp_server.py
```

Server starts at `http://localhost:8000/mcp`

## Deploy to GCP Cloud Run

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT/ctrl-alt-heal
gcloud run deploy ctrl-alt-heal \
  --image gcr.io/YOUR_PROJECT/ctrl-alt-heal \
  --port 8000 \
  --allow-unauthenticated
```

## Test with curl

```bash
# Initialize
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-FHIR-Server-URL: https://hapi.fhir.org/baseR4" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'

# List tools
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# Detect gaps for a patient
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "X-FHIR-Server-URL: https://hapi.fhir.org/baseR4" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"detect_coding_gaps","arguments":{"patient_id":"PATIENT_ID_HERE"}}}'
```

## Architecture

```
Prompt Opinion Platform
    │ SHARP Headers (X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID)
    ▼
MCP Server (this repo)
    │ Tools: detect_gaps, get_patient, validate_gap, list_gaps, draft_query
    ▼
Gap Detection Pipeline
    │ TIER 1: Lab thresholds  │ TIER 2: Phenotype rules  │ TIER 3: Note NER
    ▼
FHIR R4 Server (any: HAPI, Epic, Cerner)
    │ Patient, Observation, Condition, DocumentReference, MedicationRequest, Encounter, Procedure
```

## Built With

Python · FastAPI · FHIR R4 · SHARP-on-MCP · LOINC · ICD-10-CM · PheKB · HAPI FHIR · Synthea

## License

MIT
