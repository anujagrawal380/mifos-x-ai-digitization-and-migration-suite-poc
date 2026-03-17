# Mifos X — AI Digitization & Migration Suite

AI-powered toolkit for financial institutions adopting or migrating to Mifos X.

**Live demo:** [mifos-ai-suite.streamlit.app](https://mifos-x-ai-digitization-and-migration-suite-poc.streamlit.app)

---

## What it does

Financial institutions face three common barriers when moving to Mifos X:

1. **Paper records** — years of client and loan data locked in physical ledgers
2. **Report templates** — existing reporting formats that need to work in Mifos
3. **Legacy system data** — structured data trapped in old software exports

This suite uses AI to remove all three barriers with minimal manual effort.

---

## Use Cases & Flow

### 1. Paper Record Digitizer

Converts scanned or photographed paper forms into live records in Mifos X.

```
[Photo / scan of paper form]
         │
         ▼
   Image Preprocessing          ← ocr.py
   (deskew, denoise, adaptive threshold)
         │
         ▼
   Tesseract OCR                ← ocr.py
   (extracts raw text + per-word confidence)
         │
         ▼
   Vision LLM                   ← llm.py
   (Groq llama-4-scout, Gemini 2.0 Flash, or Ollama)
   Sees both the image AND OCR text.
   Corrects OCR errors, handles handwriting.
   Outputs structured JSON:
   { client: { name, dob, nationalId, ... },
     loan:   { principal, rate, schedule, ... },
     meta:   { confidence, uncertainFields, language } }
         │
         ▼
   Human Verification UI        ← app.py
   Uncertain fields highlighted in orange.
   Branch and loan product populated
   from live Fineract API.
   Duplicate client check runs automatically.
         │
         ▼
   Apache Fineract REST API     ← fineract.py
   POST /clients  → creates client record
   POST /loans    → submits loan application
   GET  /loans/{id} → confirms + fetches repayment schedule
         │
         ▼
   Audit log saved
   (what AI filled vs what human corrected)
```

---

### 2. Report Template Migrator

Takes an image or printout of a report from any legacy system and generates
a Mifos X compatible report definition that can be registered with one click.

```
[Image of existing report template]
         │
         ▼
   Tesseract OCR                ← ocr.py
   (extracts labels, column headers, filter fields)
         │
         ▼
   Vision LLM                   ← report_template.py
   Analyzes layout and semantics.
   Identifies: report type, columns, filter parameters,
   data sources, summary fields.
   Outputs:
   { reportName, reportType, columns, filters,
     suggestedSQL, mifosApiEndpoints, confidence }
         │
         ▼
   Report Definition Builder    ← report_template.py
   Maps analysis → Fineract POST /reports schema.
   Generates SQL using Fineract table names
   (m_client, m_loan, m_office, etc.)
   Maps filter types to Fineract parameter IDs.
         │
         ▼
   Review UI                    ← app.py
   Shows: detected columns, filter params,
   generated SQL, full JSON payload preview.
         │
         ▼
   Apache Fineract REST API     ← fineract.py
   POST /reports → registers report in Mifos
   GET  /reports → verifies registration
```

---

### 3. Legacy System Data Migration

Maps a CSV export from any legacy MFI software to the Fineract schema,
then imports all records in bulk with a dry-run option.

```
[CSV export from legacy system]
   (arbitrary column names, mixed formats,
    currency symbols, date formats, gender codes)
         │
         ▼
   LLM Column Mapper            ← migration.py
   Inspects headers + sample rows.
   Maps each source column → Fineract field.
   Suggests transformations:
   e.g. "DOB: DD/MM/YYYY → YYYY-MM-DD"
        "Sex: M/F → Male/Female"
        "Loan_Amt: strip currency symbol → float"
         │
         ▼
   Editable Mapping Table       ← app.py
   User can correct any mapping before import.
   Confidence score shown per column.
   Warnings for ambiguous or unmapped columns.
         │
         ▼
   Transformation Engine        ← migration.py
   Applies all mappings and type conversions.
   Produces a clean DataFrame ready for import.
         │
         ▼
   Bulk Import                  ← fineract.py
   Dry-run mode: validates payloads, no API calls.
   Live mode: POST /clients for each record.
   Progress bar + per-row result table.
   Export results as CSV.
         │
         ▼
   Audit log saved
```

---

## Mifos X APIs Used

| Endpoint | Used in | Purpose |
|----------|---------|---------|
| `GET /actuator/health` | All pages | Connection check |
| `GET /offices` | Digitizer | Populate live branch selector |
| `GET /loanproducts` | Digitizer | Populate live loan product selector |
| `GET /search?resource=clients` | Digitizer | Duplicate client detection |
| `POST /clients` | Digitizer, Migration | Create client record |
| `POST /loans` | Digitizer | Submit loan application |
| `GET /loans/{id}` | Digitizer | Verify loan + fetch repayment schedule |
| `POST /reports` | Report Migrator | Register generated report definition |
| `GET /reports` | Report Migrator | List existing reports |

---

## Setup

### Local development

```bash
# 1. System dependencies
brew install tesseract poppler        # macOS
# sudo apt-get install tesseract-ocr poppler-utils   # Linux

# 2. Python dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — add GROQ_API_KEY (free at https://console.groq.com)
# OR set LLM_BACKEND=gemini and add GEMINI_API_KEY
# OR set LLM_BACKEND=ollama and run: ollama pull llama3.2-vision

# 4. Start Fineract (optional — all AI features work without it)
docker compose up -d

# 5. Run the app
streamlit run app.py
```

### Connect your own Fineract instance

In the app sidebar, set the **Base URL**, **User**, and **Password**, then click **Test Connection**. The app works fully offline without Fineract — Submit/Register buttons are disabled until connected.

---

## LLM Backends

| Backend | Cost | Vision | How to enable |
|---------|------|--------|---------------|
| **Groq** (default) | Free — 30 req/min, 14,400/day | ✅ llama-4-scout-17b | `GROQ_API_KEY` in `.env` — get free key at [console.groq.com](https://console.groq.com) |
| Gemini 2.0 Flash | Free tier (new project required) | ✅ | `GEMINI_API_KEY` in `.env` — [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Ollama | Free, fully local, offline | ✅ llama3.2-vision | `ollama pull llama3.2-vision` |

---

## Project Structure

```
app.py                  — Streamlit UI (3 pages, sidebar config, audit log)
ocr.py                  — Image preprocessing + Tesseract OCR
llm.py                  — LLM field extraction (Groq / Gemini / Ollama)
fineract.py             — Apache Fineract REST API client (9 endpoints)
report_template.py      — Report structure analysis + definition generator
migration.py            — CSV column mapping + transformation + bulk import
generate_sample_form.py — Generates realistic paper form PDFs for demo
convert_samples.py      — Converts PDF forms to PNG images
docker-compose.yml      — Fineract + MariaDB stack
Dockerfile.mariadb      — MariaDB image with init SQL baked in
packages.txt            — System dependencies for Streamlit Cloud

sample_forms/
├── typed_form_1/2/3.png         — Ghana, Nigeria, India (printed forms)
└── handwritten_form_1/2/3.png   — Bilingual French/English (field office style)
```

---

## Deployment

### Streamlit Cloud (AI features — free)
1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → connect repo → main file: `app.py`
3. Add secrets:
```toml
GROQ_API_KEY = "gsk_..."
LLM_BACKEND = "groq"
FINERACT_BASE_URL = "https://your-fineract-host:8443/fineract-provider/api/v1"
FINERACT_USERNAME = "mifos"
FINERACT_PASSWORD = "password"
FINERACT_VERIFY_SSL = "false"
```

### Fineract backend (Docker)
```bash
docker compose up -d
# Then create a loan product (required before submitting loans):
curl -sk -u mifos:password \
  -H "fineract-platform-tenantid: default" \
  -H "Content-Type: application/json" \
  https://localhost:8443/fineract-provider/api/v1/loanproducts \
  -d '{"name":"General Loan","shortName":"GEN","currencyCode":"USD","digitsAfterDecimal":2,"inMultiplesOf":0,"principal":1000,"numberOfRepayments":12,"repaymentEvery":1,"repaymentFrequencyType":2,"interestRatePerPeriod":10,"interestRateFrequencyType":2,"amortizationType":1,"interestType":0,"interestCalculationPeriodType":1,"transactionProcessingStrategyCode":"mifos-standard-strategy","daysInYearType":365,"daysInMonthType":30,"isInterestRecalculationEnabled":false,"accountingRule":1,"locale":"en","dateFormat":"dd MMMM yyyy"}'
```
