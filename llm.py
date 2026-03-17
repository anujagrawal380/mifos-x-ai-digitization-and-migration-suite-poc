"""
llm.py — LLM-powered structured field extraction from OCR text + image.

Supports two free backends:
  - Ollama (fully local, llama3.2-vision or llava)
  - Google Gemini Flash (free tier: 15 req/min, 1M tokens/day)

The LLM receives both the raw OCR text AND the original image so it can
correct OCR errors (especially for handwriting).
"""

import json
import os
import re
import base64
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("LLM_BACKEND", "gemini").lower()

EXTRACTION_PROMPT = """You are a data extraction assistant for a microfinance institution.

You will be given:
1. Raw OCR text extracted from a scanned paper record (may contain errors)
2. The original scanned image

Your job is to extract structured data and return ONLY a valid JSON object.

Extract these fields (use null if not found):
{{
  "client": {{
    "firstname": string,
    "lastname": string,
    "middlename": string | null,
    "dateOfBirth": "YYYY-MM-DD" | null,
    "gender": "Male" | "Female" | "Other" | null,
    "mobileNo": string | null,
    "nationalId": string | null,
    "address": string | null
  }},
  "loan": {{
    "principal": number | null,
    "currency": string | null,
    "disbursementDate": "YYYY-MM-DD" | null,
    "repaymentFrequency": "weekly" | "biweekly" | "monthly" | null,
    "numberOfRepayments": number | null,
    "interestRate": number | null,
    "purpose": string | null
  }},
  "meta": {{
    "formType": "loan_application" | "client_registration" | "repayment_schedule" | "other",
    "detectedLanguage": string,
    "hasHandwriting": boolean,
    "uncertainFields": [list of field names you are not confident about],
    "overallConfidence": float between 0 and 1
  }}
}}

Rules:
- Correct obvious OCR errors using context (e.g., "0" vs "O" in names)
- For dates, try to parse any format (DD/MM/YYYY, MM-DD-YYYY, etc.)
- If a field is partially legible, include your best guess and add it to uncertainFields
- Return ONLY valid JSON starting with {{ and ending with }}. No prose, no markdown fences, no explanation.

OCR Text:
{ocr_text}
"""


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def _extract_gemini(ocr_text: str, image: Image.Image) -> dict:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key in ("your_key_here", "YOUR_KEY_HERE", ""):
        raise ValueError("GEMINI_API_KEY not set — add it to your .env file")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")  # free tier model

    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)
    response = model.generate_content([prompt, image])

    # Newer SDK versions raise ValueError on .text if response is blocked/multi-part
    try:
        raw_text = response.text
    except ValueError:
        # Try extracting from candidates directly
        try:
            raw_text = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            )
        except (IndexError, AttributeError) as exc:
            raise ValueError(
                f"Gemini returned no usable text. "
                f"Finish reason: {getattr(response.candidates[0], 'finish_reason', 'unknown') if response.candidates else 'no candidates'}"
            ) from exc

    if not raw_text or not raw_text.strip():
        raise ValueError("Gemini returned an empty response — check your API key and quota")

    return _parse_llm_response(raw_text)


# ---------------------------------------------------------------------------
# Groq backend (free tier: 30 req/min, 14,400/day — https://console.groq.com)
# ---------------------------------------------------------------------------

def _extract_groq(ocr_text: str, image: Image.Image) -> dict:
    from groq import Groq
    from ocr import image_to_bytes

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key in ("your_key_here", ""):
        raise ValueError("GROQ_API_KEY not set — get a free key at console.groq.com")

    client = Groq(api_key=api_key)

    # Encode image as base64 for vision model
    img_bytes = image_to_bytes(image)
    img_b64 = base64.b64encode(img_bytes).decode()

    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",  # free vision model on Groq
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

    return _parse_llm_response(response.choices[0].message.content)


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

def _extract_ollama(ocr_text: str, image: Image.Image) -> dict:
    import ollama
    from ocr import image_to_bytes

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2-vision")

    client = ollama.Client(host=host)

    img_bytes = image_to_bytes(image)
    img_b64 = base64.b64encode(img_bytes).decode()

    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

    response = client.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": prompt,
            "images": [img_b64],
        }]
    )

    return _parse_llm_response(response["message"]["content"])


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_llm_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks and partial responses."""
    if not text or not text.strip():
        raise ValueError("LLM returned an empty response")

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: find the outermost { ... } block
    # Use a brace counter to find matching braces (handles nested objects correctly)
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(cleaned[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break

    # Strategy 3: LLM omitted outer braces — response starts with "client": {...}
    # Wrap the whole thing in {} and try again
    if re.search(r'"(client|loan|meta)"\s*:', cleaned):
        # Remove any trailing comma before closing
        wrapped = "{" + cleaned.rstrip().rstrip(",") + "}"
        try:
            result = json.loads(wrapped)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse JSON from LLM response. "
        f"Raw response (first 400 chars):\n{text[:400]}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_fields(ocr_text: str, image: Image.Image) -> dict:
    """
    Extract structured fields from OCR text + image using the configured backend.

    Returns a dict with keys: client, loan, meta
    """
    if BACKEND == "gemini":
        return _extract_gemini(ocr_text, image)
    elif BACKEND == "groq":
        return _extract_groq(ocr_text, image)
    elif BACKEND == "ollama":
        return _extract_ollama(ocr_text, image)
    else:
        raise ValueError(f"Unknown LLM_BACKEND: {BACKEND}. Use 'gemini', 'groq', or 'ollama'.")
