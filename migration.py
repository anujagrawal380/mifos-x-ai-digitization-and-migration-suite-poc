"""
migration.py — Use Case 3: AI-assisted data migration from legacy system → Mifos X.

Given a CSV/Excel export from any legacy MFI system, the LLM:
  1. Inspects the column headers + sample rows
  2. Maps each column to the Fineract API schema
  3. Returns a validated mapping + batch import plan

Supports clients, loans, and savings accounts.
"""

import json
import re
import os
import io
import csv
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("LLM_BACKEND", "gemini").lower()

MAPPING_PROMPT = """You are a data migration specialist for Mifos X (Apache Fineract).

A financial institution is migrating from a legacy system. You are given:
1. Column headers from their CSV export
2. A few sample rows

Your job: map each source column to the correct Fineract API field.

Fineract client fields: firstname, lastname, middlename, dateOfBirth (YYYY-MM-DD),
  gender (Male/Female), mobileNo, externalId, address, officeId

Fineract loan fields: principal, numberOfRepayments, repaymentFrequency (weekly/monthly),
  interestRate, disbursementDate (YYYY-MM-DD), loanProductId, submittedOnDate

Return ONLY valid JSON:
{{
  "detectedEntity": "client" | "loan" | "mixed" | "unknown",
  "mappings": [
    {{
      "sourceColumn": string,
      "fineractField": string | null,
      "transformation": string | null,
      "confidence": float,
      "notes": string | null
    }}
  ],
  "unmappedColumns": [string],
  "estimatedRecords": integer,
  "warnings": [string],
  "overallConfidence": float
}}

transformation examples:
  - "uppercase first letter" for names
  - "parse date DD/MM/YYYY → YYYY-MM-DD"
  - "remove currency symbol, parse as float"
  - "map M→Male, F→Female"
  - null if no transformation needed

Source columns: {columns}

Sample rows:
{sample_rows}
"""


def analyze_csv_mapping(df: pd.DataFrame) -> dict:
    """Use LLM to map CSV columns to Fineract fields."""
    columns = list(df.columns)
    sample = df.head(3).to_dict(orient="records")
    sample_str = json.dumps(sample, indent=2, default=str)

    prompt = MAPPING_PROMPT.format(
        columns=json.dumps(columns),
        sample_rows=sample_str
    )

    if BACKEND == "gemini":
        return _call_gemini_text(prompt)
    elif BACKEND == "groq":
        return _call_groq_text(prompt)
    elif BACKEND == "ollama":
        return _call_ollama_text(prompt)
    else:
        raise ValueError(f"Unknown backend: {BACKEND}")


def _call_gemini_text(prompt: str) -> dict:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return _parse_response(response.text)


def _call_groq_text(prompt: str) -> dict:
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set — get a free key at console.groq.com")
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # text-only, high quality, free tier
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2048,
    )
    return _parse_response(response.choices[0].message.content)


def _call_ollama_text(prompt: str) -> dict:
    import ollama
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model_name = os.getenv("OLLAMA_MODEL", "llama3.2-vision")
    client = ollama.Client(host=host)
    response = client.chat(
        model=model_name,
        messages=[{"role": "user", "content": prompt}]
    )
    return _parse_response(response["message"]["content"])


def _parse_response(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON:\n{text[:500]}")


def apply_mappings(df: pd.DataFrame, mappings: list[dict]) -> pd.DataFrame:
    """
    Apply the AI-generated field mappings and transformations to produce
    a clean DataFrame ready for Fineract import.
    """
    result = {}
    for m in mappings:
        src = m["sourceColumn"]
        dst = m.get("fineractField")
        transform = m.get("transformation") or ""

        if not dst or src not in df.columns:
            continue

        series = df[src].copy()

        # Apply common transformations
        t = transform.lower()
        if "date" in t and ("dd/mm" in t or "parse" in t):
            series = pd.to_datetime(series, dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
        elif "currency" in t or "float" in t or "parse as float" in t:
            series = series.astype(str).str.replace(r"[^\d.]", "", regex=True)
            series = pd.to_numeric(series, errors="coerce")
        elif "uppercase first" in t or "capitalize" in t:
            series = series.astype(str).str.strip().str.title()
        elif "m→male" in t or "m->male" in t or "gender" in t:
            series = series.astype(str).str.upper().map(
                {"M": "Male", "F": "Female", "MALE": "Male", "FEMALE": "Female"}
            )

        result[dst] = series

    return pd.DataFrame(result)


def build_client_payloads(df_mapped: pd.DataFrame) -> list[dict]:
    """Convert mapped DataFrame rows into Fineract POST /clients payloads."""
    payloads = []
    for _, row in df_mapped.iterrows():
        payload = {
            "officeId": int(row.get("officeId")) if str(row.get("officeId", "")).isdigit() else 1,
            "legalFormId": 1,
            "active": True,
            "activationDate": "2024-01-01",
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        for field in ["firstname", "lastname", "middlename", "mobileNo",
                      "externalId", "dateOfBirth", "gender"]:
            val = row.get(field)
            if pd.notna(val) and str(val).strip():
                payload[field] = str(val).strip()

        payloads.append(payload)
    return payloads


def generate_sample_legacy_csv() -> str:
    """Generate a sample CSV that mimics a legacy MFI system export."""
    rows = [
        ["Cust_ID", "Full_Name", "DOB", "Sex", "Phone", "ID_Number", "Branch",
         "Loan_Ref", "Loan_Amt", "No_Instalments", "Freq", "Rate_PA", "Disburse_Dt", "Purpose"],
        ["C001", "MENSAH AMARA KOFI", "15/03/1988", "M", "0244567890", "GH-198803-4521", "Accra",
         "L2024001", "5000", "12", "Monthly", "18", "01/02/2024", "Business"],
        ["C002", "AL-HASSAN FATIMA", "22/07/1995", "F", "08012345678", "NG-1995-0722-F", "Lagos",
         "L2024002", "150000", "26", "Weekly", "24", "10/03/2024", "Tailoring"],
        ["C003", "RAMASWAMY PRIYA S", "30/11/1982", "F", "9876543210", "IN-MH-123456789", "Pune",
         "L2024003", "75000", "24", "Monthly", "12", "15/01/2024", "Agriculture"],
        ["C004", "OTIENO JOHN MWANGI", "05/06/1979", "M", "0722111222", "KE-1979-JOM", "Nairobi",
         "L2024004", "30000", "18", "Monthly", "20", "20/03/2024", "Livestock"],
        ["C005", "DUBOIS MARIE CLAIRE", "12/09/1991", "F", "+225 07 123 456", "CI-1991-MDC", "Abidjan",
         "L2024005", "800000", "12", "Monthly", "15", "05/02/2024", "Commerce"],
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue()
