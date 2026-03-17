"""
convert_samples.py — Convert generated PDF sample forms to PNG images.

Run after generate_sample_form.py:
  python convert_samples.py
"""

import os
from pdf2image import convert_from_path

FORMS_DIR = os.path.join(os.path.dirname(__file__), "sample_forms")

for fname in sorted(os.listdir(FORMS_DIR)):
    if not fname.endswith(".pdf"):
        continue
    pdf_path = os.path.join(FORMS_DIR, fname)
    pages = convert_from_path(pdf_path, dpi=150)
    out_path = pdf_path.replace(".pdf", ".png")
    pages[0].save(out_path, "PNG")
    print(f"Converted: {out_path}")

print("\nDone. PNG files are ready for the Streamlit demo.")
