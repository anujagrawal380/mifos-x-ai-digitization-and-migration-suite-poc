# Mifos X - AI Digitization & Migration Suite

AI-powered toolkit for financial institutions adopting or migrating to Mifos X.

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
   (deskew, denoise, threshold)
         │
         ▼
   Tesseract OCR                ← ocr.py
   (extracts raw text + per-word confidence)
         │
         ▼
   Vision LLM                   ← llm.py
   (Gemini Flash or Ollama)
   Sees both the image AND OCR text.
   Corrects OCR errors, handles handwriting.
   Outputs structured JSON:
   { client: { name, dob, nationalId, ... },
     loan:   { principal, rate, schedule, ... },
     meta:   { confidence, uncertainFields, language } }
         │
         ▼
   Human Verification UI        ← app.py
   Uncertain fields highlighted.
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
         │
         ▼
   Review UI                    ← app.py
   Shows: detected columns, filter params,
   generated SQL (editable), side-by-side preview.
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

```bash
# 1. System dependencies
brew install tesseract poppler        # macOS
# sudo apt-get install tesseract-ocr poppler-utils   # Linux

# 2. Python dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env — set GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)
# OR set LLM_BACKEND=ollama and run: ollama pull llama3.2-vision

# 4. Generate sample demo data
python generate_sample_form.py
python convert_samples.py

# 5. Start Fineract (optional — all AI features work offline)
docker run -p 8443:8443 apache/fineract
docker compose up -d

# 6. Run the app
streamlit run app.py
```

---

## LLM Backends

| Backend | Cost | How to enable |
|---------|------|---------------|
| Gemini 1.5 Flash | Free (15 req/min, 1M tokens/day) | Set `GEMINI_API_KEY` in `.env` |
| Ollama llama3.2-vision | Free, fully local, no internet | `ollama pull llama3.2-vision` |

---

## Project Structure

```
app.py                  — Streamlit UI (3 pages, sidebar config, audit log)
ocr.py                  — Image preprocessing + Tesseract OCR
llm.py                  — LLM field extraction → structured JSON
fineract.py             — Apache Fineract REST API client
report_template.py      — Report structure analysis + definition generator
migration.py            — CSV column mapping + transformation + bulk import
generate_sample_form.py — Generates realistic paper form PDFs for demo
convert_samples.py      — Converts PDF forms to PNG images

sample_forms/
├── typed_form_1/2/3.png         — Ghana, Nigeria, India (printed forms)
├── handwritten_form_1/2/3.png   — Bilingual French/English (field office style)
└── sample_report_template.png   — Legacy portfolio report for migration demo
```
