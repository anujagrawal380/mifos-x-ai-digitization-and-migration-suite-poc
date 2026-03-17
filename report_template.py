"""
report_template.py — Use Case 2: AI-assisted report template migration.

Given an image or PDF of an existing report template (from any system),
extract its structure and generate a Mifos X compatible report definition
that can be registered via POST /reports.

Mifos X supports these report types:
  - Table  (SQL-based, most common)
  - Chart  (visualization)
  - SMS    (notification reports)
  - Pentaho (complex PRPT templates)
"""

import json
import os
import re
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("LLM_BACKEND", "gemini").lower()

REPORT_ANALYSIS_PROMPT = """You are a Mifos X reporting expert.

Analyze this report template image and extract its structure.
Return ONLY a valid JSON with this exact shape:

{
  "reportName": string,
  "reportType": "Table" | "Chart" | "SMS" | "Pentaho",
  "reportSubType": "S" | null,
  "reportCategory": "Loan" | "Savings" | "Client" | "Fund" | "Accounting" | null,
  "description": string,
  "coreReport": false,
  "useReport": true,
  "columns": [
    {"name": string, "label": string, "dataType": "string"|"integer"|"decimal"|"date"|"boolean"}
  ],
  "filters": [
    {"name": string, "label": string, "type": "date"|"select"|"text"|"office"|"loanProduct"}
  ],
  "suggestedSQL": string,
  "mifosApiEndpoints": [string],
  "confidence": float,
  "notes": string
}

Rules:
- suggestedSQL: Write a realistic SQL query that would generate this report using
  Fineract's schema. Key tables: m_client, m_loan, m_loan_repayment_schedule,
  m_savings_account, m_office, m_product_loan, m_staff
- mifosApiEndpoints: list Fineract REST endpoints that provide this data
- notes: any assumptions made or fields you could not determine

Report image to analyze:
"""

REPORT_ANALYSIS_PROMPT_TEXT = REPORT_ANALYSIS_PROMPT + "\n\nOCR Text from report:\n{ocr_text}"


def analyze_report_template(image: Image.Image, ocr_text: str = "") -> dict:
    """
    Analyze a report template image and return a Mifos-compatible report definition.
    """
    if BACKEND == "gemini":
        return _analyze_gemini(image, ocr_text)
    elif BACKEND == "groq":
        return _analyze_groq(image, ocr_text)
    elif BACKEND == "ollama":
        return _analyze_ollama(image, ocr_text)
    else:
        raise ValueError(f"Unknown LLM_BACKEND: {BACKEND}")


def _analyze_gemini(image: Image.Image, ocr_text: str) -> dict:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = REPORT_ANALYSIS_PROMPT
    if ocr_text:
        prompt += f"\n\nOCR Text:\n{ocr_text}"

    response = model.generate_content([prompt, image])
    return _parse_response(response.text)


def _analyze_groq(image: Image.Image, ocr_text: str) -> dict:
    import base64
    from groq import Groq
    from ocr import image_to_bytes

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set — get a free key at console.groq.com")

    client = Groq(api_key=api_key)
    img_b64 = base64.b64encode(image_to_bytes(image)).decode()

    prompt = REPORT_ANALYSIS_PROMPT
    if ocr_text:
        prompt += f"\n\nOCR Text:\n{ocr_text}"

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }],
        temperature=0.1,
        max_tokens=2048,
    )
    return _parse_response(response.choices[0].message.content)


def _analyze_ollama(image: Image.Image, ocr_text: str) -> dict:
    import ollama
    import base64
    from ocr import image_to_bytes

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2-vision")
    client = ollama.Client(host=host)

    img_b64 = base64.b64encode(image_to_bytes(image)).decode()
    prompt = REPORT_ANALYSIS_PROMPT
    if ocr_text:
        prompt += f"\n\nOCR Text:\n{ocr_text}"

    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt, "images": [img_b64]}]
    )
    return _parse_response(response["message"]["content"])


def _parse_response(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("LLM returned an empty response")
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    # Find outermost { ... } using brace counting
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(cleaned[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(cleaned[start:i + 1])
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break
    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:400]}")


def build_fineract_report_payload(analysis: dict) -> dict:
    """
    Convert the LLM analysis into the exact payload for POST /reports.
    reportParameters must reference IDs from GET /reports/template allowedParameters.
    """
    # Map LLM filter type → Fineract parameter ID
    PARAM_ID_MAP = {
        "office":       5,   # OfficeIdSelectOne
        "loanProduct":  25,  # loanProductIdSelectAll
        "loanOfficer":  6,   # loanOfficerIdSelectAll
        "currency":     10,  # currencyIdSelectAll
        "fund":         20,  # fundIdSelectAll
    }
    # Date filters need two separate params: start + end
    DATE_PARAMS = [
        {"parameterId": 1, "reportParameterName": "startDateSelect"},
        {"parameterId": 2, "reportParameterName": "endDateSelect"},
    ]

    report_params = []
    date_added = False
    for f in analysis.get("filters", []):
        ftype = f.get("type", "")
        if ftype == "date" and not date_added:
            report_params.extend(DATE_PARAMS)
            date_added = True
        elif ftype in PARAM_ID_MAP:
            report_params.append({
                "parameterId": PARAM_ID_MAP[ftype],
                "reportParameterName": f.get("name", ftype),
            })

    payload = {
        "reportName": analysis.get("reportName", "Migrated Report"),
        "reportType": analysis.get("reportType", "Table"),
        "reportCategory": analysis.get("reportCategory"),
        "description": analysis.get("description", ""),
        "reportSql": analysis.get("suggestedSQL", ""),
    }
    if analysis.get("reportSubType"):
        payload["reportSubType"] = analysis["reportSubType"]
    if report_params:
        payload["reportParameters"] = report_params
    return payload


def generate_sample_report_image() -> Image.Image:
    """
    Generate a sample 'existing report template' image for demo purposes.
    Simulates a printout from a legacy MFI system.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    import io
    from pdf2image import convert_from_bytes

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Header
    c.setFillColor(colors.HexColor("#2c5f2e"))
    c.rect(0, h - 2.5 * cm, w, 2.5 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, h - 1.2 * cm, "MONTHLY LOAN PORTFOLIO REPORT")
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 1.9 * cm, "Legacy MFI System v2.3 | Generated: 2024-01-31")

    c.setFillColor(colors.black)

    # Filter section
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, h - 3.5 * cm, "REPORT PARAMETERS")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, h - 4.1 * cm, "Office:  [ All Branches ]")
    c.drawString(8 * cm, h - 4.1 * cm, "Date From:  [ 2024-01-01 ]")
    c.drawString(14 * cm, h - 4.1 * cm, "Date To:  [ 2024-01-31 ]")
    c.drawString(2 * cm, h - 4.6 * cm, "Loan Product:  [ All Products ]")
    c.drawString(8 * cm, h - 4.6 * cm, "Loan Officer:  [ All Officers ]")

    c.line(1.5 * cm, h - 4.9 * cm, w - 1.5 * cm, h - 4.9 * cm)

    # Table header
    headers = ["Client ID", "Client Name", "Loan ID", "Product", "Principal", "Outstanding", "Days Overdue", "Status"]
    widths = [2, 4, 2, 3, 2.5, 2.5, 2.5, 2.5]
    x_positions = [1.5]
    for ww in widths[:-1]:
        x_positions.append(x_positions[-1] + ww * cm)

    c.setFillColor(colors.HexColor("#e8f5e9"))
    c.rect(1.5 * cm, h - 5.7 * cm, w - 3 * cm, 0.6 * cm, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    for i, (header, x) in enumerate(zip(headers, x_positions)):
        c.drawString(x + 0.1 * cm, h - 5.3 * cm, header)

    # Sample data rows
    rows = [
        ["001", "Amara Mensah", "L-001", "SME Loan", "5,000", "3,200", "0", "Active"],
        ["002", "Fatima Hassan", "L-002", "Agri Loan", "150,000", "142,500", "0", "Active"],
        ["003", "John Otieno", "L-003", "SME Loan", "20,000", "18,500", "15", "Arrears"],
        ["004", "Priya Sharma", "L-004", "Housing", "500,000", "490,000", "0", "Active"],
        ["005", "Marie Dubois", "L-005", "Consumer", "8,000", "6,400", "32", "Arrears"],
    ]

    c.setFont("Helvetica", 8)
    row_y = h - 6.0 * cm
    for j, row in enumerate(rows):
        if j % 2 == 0:
            c.setFillColor(colors.HexColor("#f9f9f9"))
            c.rect(1.5 * cm, row_y - 0.1 * cm, w - 3 * cm, 0.55 * cm, fill=1, stroke=0)
        c.setFillColor(colors.black)
        for val, x in zip(row, x_positions):
            c.drawString(x + 0.1 * cm, row_y + 0.2 * cm, str(val))
        row_y -= 0.6 * cm

    # Summary section
    c.line(1.5 * cm, row_y, w - 1.5 * cm, row_y)
    row_y -= 0.5 * cm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2 * cm, row_y, "SUMMARY")
    row_y -= 0.5 * cm
    c.setFont("Helvetica", 9)
    summaries = [
        ("Total Active Loans:", "5"),
        ("Total Portfolio Outstanding:", "660,600"),
        ("Portfolio at Risk (PAR > 30):", "2 loans (8,400)"),
        ("Collection Rate:", "94.2%"),
    ]
    for label, val in summaries:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(2 * cm, row_y, label)
        c.setFont("Helvetica", 9)
        c.drawString(8 * cm, row_y, val)
        row_y -= 0.5 * cm

    c.save()

    pdf_bytes = buf.getvalue()
    pages = convert_from_bytes(pdf_bytes, dpi=150)
    return pages[0]
