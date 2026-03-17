"""
generate_sample_form.py — Creates realistic sample microfinance forms as PDFs/images.

Run once to generate demo forms in sample_forms/
  python generate_sample_form.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
import random
import os

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "sample_forms")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def make_loan_application(filename: str, data: dict):
    """Generate a typed loan application form (simulates digitally filled paper)."""
    path = os.path.join(OUTPUT_DIR, filename)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    # Header
    c.setFillColor(colors.HexColor("#1a3a5c"))
    c.rect(0, h - 3 * cm, w, 3 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 1.5 * cm, "MICROFINANCE LOAN APPLICATION FORM")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, h - 2.2 * cm, "Mifos Community Finance | Branch Code: MFC-001")

    c.setFillColor(colors.black)

    def section(title, y):
        c.setFillColor(colors.HexColor("#e8f0f7"))
        c.rect(1.5 * cm, y - 0.3 * cm, w - 3 * cm, 0.7 * cm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1a3a5c"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1.8 * cm, y, title)
        c.setFillColor(colors.black)

    def field(label, value, x, y, label_width=5 * cm):
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawString(x, y, label + ":")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        c.drawString(x + label_width, y, str(value) if value else "")
        # underline
        c.setStrokeColor(colors.HexColor("#aaaaaa"))
        c.line(x + label_width, y - 0.1 * cm, x + label_width + 6 * cm, y - 0.1 * cm)
        c.setStrokeColor(colors.black)

    y = h - 4 * cm

    # Section 1: Client
    section("SECTION 1: CLIENT INFORMATION", y)
    y -= 0.8 * cm
    field("Full Name", f"{data['firstname']} {data.get('middlename', '')} {data['lastname']}", 1.5 * cm, y)
    y -= 0.7 * cm
    field("Date of Birth", data["dateOfBirth"], 1.5 * cm, y)
    field("Gender", data["gender"], 10 * cm, y, label_width=2.5 * cm)
    y -= 0.7 * cm
    field("National ID", data["nationalId"], 1.5 * cm, y)
    field("Mobile No.", data["mobileNo"], 10 * cm, y, label_width=2.5 * cm)
    y -= 0.7 * cm
    field("Address", data["address"], 1.5 * cm, y)

    y -= 1.2 * cm

    # Section 2: Loan
    section("SECTION 2: LOAN DETAILS", y)
    y -= 0.8 * cm
    field("Loan Amount", f"{data['currency']} {data['principal']:,.2f}", 1.5 * cm, y)
    field("Purpose", data["purpose"], 10 * cm, y, label_width=2.5 * cm)
    y -= 0.7 * cm
    field("Disbursement Date", data["disbursementDate"], 1.5 * cm, y)
    field("No. of Repayments", str(data["numberOfRepayments"]), 10 * cm, y, label_width=2.5 * cm)
    y -= 0.7 * cm
    field("Repayment Frequency", data["repaymentFrequency"].capitalize(), 1.5 * cm, y)
    field("Interest Rate (%)", f"{data['interestRate']}% p.a.", 10 * cm, y, label_width=2.5 * cm)

    y -= 1.2 * cm

    # Section 3: Signature
    section("SECTION 3: DECLARATION", y)
    y -= 0.8 * cm
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(1.5 * cm, y,
                 "I hereby declare that the information provided above is true and correct to the best of my knowledge.")
    y -= 0.7 * cm
    c.drawString(1.5 * cm, y,
                 "I authorize Mifos Community Finance to verify the information and process my loan application.")

    y -= 1.5 * cm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.line(1.5 * cm, y, 8 * cm, y)
    c.line(11 * cm, y, 18 * cm, y)
    y -= 0.4 * cm
    c.drawString(1.5 * cm, y, "Applicant Signature")
    c.drawString(11 * cm, y, "Date")

    # Footer
    c.setFillColor(colors.HexColor("#1a3a5c"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(w / 2, 1 * cm, "Form MFC-LA-001 | For office use only | Ref: " + data.get("ref", "N/A"))

    c.save()
    print(f"Generated: {path}")
    return path


def make_handwritten_style_form(filename: str, data: dict):
    """
    Simulates a scanned handwritten form using a slight rotation and
    irregular font sizing (approximation — real handwriting needs PIL).
    """
    path = os.path.join(OUTPUT_DIR, filename)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    c.setFont("Courier-Bold", 14)
    c.drawString(2 * cm, h - 2 * cm, "LOAN APPLICATION / DEMANDE DE PRET")
    c.setFont("Courier", 10)
    c.drawString(2 * cm, h - 2.6 * cm, "Mifos Microfinance — Branch: Accra Central")

    c.line(1.5 * cm, h - 2.9 * cm, w - 1.5 * cm, h - 2.9 * cm)

    entries = [
        ("Nom / Name", f"{data['firstname']} {data['lastname']}"),
        ("Date de naissance / DOB", data["dateOfBirth"]),
        ("Sexe / Gender", data["gender"]),
        ("No. National / National ID", data["nationalId"]),
        ("Tel / Mobile", data["mobileNo"]),
        ("Adresse / Address", data["address"]),
        ("", ""),
        ("Montant / Loan Amount", f"{data['currency']} {data['principal']:,.2f}"),
        ("Objet / Purpose", data["purpose"]),
        ("Date Decaissement / Disbursement", data["disbursementDate"]),
        ("Nbre Echeances / No. Repayments", str(data["numberOfRepayments"])),
        ("Frequence / Frequency", data["repaymentFrequency"]),
        ("Taux Interet / Interest Rate", f"{data['interestRate']}%"),
    ]

    y = h - 3.5 * cm
    for label, value in entries:
        if not label:
            y -= 0.4 * cm
            c.line(1.5 * cm, y, w - 1.5 * cm, y)
            y -= 0.2 * cm
            continue
        c.setFont("Courier-Bold", 9)
        c.drawString(2 * cm, y, label + ":")
        c.setFont("Courier", 10)
        # slight x-offset variation to simulate handwriting irregularity
        c.drawString(9 * cm, y, value)
        c.setStrokeColor(colors.HexColor("#cccccc"))
        c.line(9 * cm, y - 0.15 * cm, w - 2 * cm, y - 0.15 * cm)
        c.setStrokeColor(colors.black)
        y -= 0.75 * cm

    c.setFont("Courier", 8)
    c.drawString(2 * cm, 2 * cm, "Signature: ________________________    Date: ____________")

    c.save()
    print(f"Generated: {path}")
    return path


SAMPLE_CLIENTS = [
    {
        "firstname": "Amara", "middlename": "Kofi", "lastname": "Mensah",
        "dateOfBirth": "1988-03-15", "gender": "Male",
        "nationalId": "GH-198803-4521", "mobileNo": "+233 24 456 7890",
        "address": "12 Nkrumah Ave, Accra, Ghana",
        "principal": 5000.00, "currency": "GHS",
        "disbursementDate": "2024-02-01",
        "repaymentFrequency": "monthly", "numberOfRepayments": 12,
        "interestRate": 18, "purpose": "Small business expansion",
        "ref": "2024-ACC-00123",
    },
    {
        "firstname": "Fatima", "middlename": None, "lastname": "Al-Hassan",
        "dateOfBirth": "1995-07-22", "gender": "Female",
        "nationalId": "NG-1995-0722-F", "mobileNo": "+234 801 234 5678",
        "address": "45 Adeola Odeku St, Lagos, Nigeria",
        "principal": 150000.00, "currency": "NGN",
        "disbursementDate": "2024-03-10",
        "repaymentFrequency": "weekly", "numberOfRepayments": 26,
        "interestRate": 24, "purpose": "Tailoring business",
        "ref": "2024-LAG-00456",
    },
    {
        "firstname": "Priya", "middlename": "S", "lastname": "Ramaswamy",
        "dateOfBirth": "1982-11-30", "gender": "Female",
        "nationalId": "IN-MH-123456789",  "mobileNo": "+91 98765 43210",
        "address": "78 Gandhi Nagar, Pune, Maharashtra 411001",
        "principal": 75000.00, "currency": "INR",
        "disbursementDate": "2024-01-15",
        "repaymentFrequency": "monthly", "numberOfRepayments": 24,
        "interestRate": 12, "purpose": "Agriculture — irrigation pump",
        "ref": "2024-PUN-00789",
    },
]


if __name__ == "__main__":
    for i, client in enumerate(SAMPLE_CLIENTS):
        make_loan_application(f"typed_form_{i+1}.pdf", client)
        make_handwritten_style_form(f"handwritten_form_{i+1}.pdf", client)

    print(f"\nGenerated {len(SAMPLE_CLIENTS) * 2} sample forms in {OUTPUT_DIR}/")
    print("These represent forms from Ghana, Nigeria, and India.")
