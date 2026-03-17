"""
fineract.py — Apache Fineract REST API client.

Handles client creation and loan application submission.
Fineract API docs: https://demo.fineract.dev/fineract-provider/swagger-ui/index.html
"""

import os
import requests
from requests.auth import HTTPBasicAuth
import urllib3
from dotenv import load_dotenv

load_dotenv()

# Suppress SSL warnings for local self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FineractClient:
    def __init__(self):
        self.base_url = os.getenv("FINERACT_BASE_URL",
                                  "https://localhost:8443/fineract-provider/api/v1")
        self.auth = HTTPBasicAuth(
            os.getenv("FINERACT_USERNAME", "mifos"),
            os.getenv("FINERACT_PASSWORD", "password")
        )
        self.tenant = os.getenv("FINERACT_TENANT", "default")
        self.verify_ssl = os.getenv("FINERACT_VERIFY_SSL", "false").lower() == "true"

        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "fineract-platform-tenantid": self.tenant,
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _handle(self, response: requests.Response) -> dict:
        try:
            response.raise_for_status()
            return {"success": True, "data": response.json(), "status": response.status_code}
        except requests.HTTPError as e:
            return {
                "success": False,
                "error": str(e),
                "status": response.status_code,
                "detail": response.text[:500],
            }

    def health_check(self) -> bool:
        """Ping Fineract to verify connectivity."""
        try:
            # Actuator is outside /api/v1 — build URL from base without the API path
            base = self.base_url.split("/api/")[0]
            r = self.session.get(
                f"{base}/actuator/health",
                verify=self.verify_ssl,
                timeout=5
            )
            return r.status_code == 200
        except Exception:
            return False

    def create_client(self, client_data: dict) -> dict:
        """
        POST /clients — Create a new client in Fineract.

        client_data keys (Fineract schema):
          firstname, lastname, dateOfBirth (YYYY-MM-DD),
          mobileNo, externalId, officeId (default 1),
          legalFormId (1=person, 2=entity), active, activationDate
        """
        # Use yyyy-MM-dd for everything — convert activationDate if needed
        activation = client_data.get("activationDate", "2024-01-01")
        if activation and " " in activation:
            # Convert "01 January 2024" → "2024-01-01"
            from datetime import datetime
            try:
                activation = datetime.strptime(activation, "%d %B %Y").strftime("%Y-%m-%d")
            except ValueError:
                activation = "2024-01-01"

        payload = {
            "officeId": client_data.get("officeId", 1),
            "legalFormId": 1,  # Person
            "active": True,
            "activationDate": activation,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }

        for field in ["firstname", "lastname", "middlename",
                      "mobileNo", "externalId", "dateOfBirth"]:
            val = client_data.get(field)
            if val:
                payload[field] = val

        r = self.session.post(
            self._url("/clients"),
            json=payload,
            verify=self.verify_ssl
        )
        return self._handle(r)

    def create_loan(self, client_id: int, loan_data: dict) -> dict:
        """
        POST /loans — Submit a loan application for an existing client.

        loan_data keys:
          principal, loanTermFrequency, loanTermFrequencyType (0=days,1=weeks,2=months),
          numberOfRepayments, repaymentEvery, repaymentFrequencyType,
          interestRatePerPeriod, disbursementDate (YYYY-MM-DD),
          loanType (1=individual), productId (default 1)
        """
        freq_map = {"weekly": 1, "biweekly": 1, "monthly": 2}
        freq_type = freq_map.get(
            (loan_data.get("repaymentFrequency") or "monthly").lower(), 2
        )
        repay_every = 2 if loan_data.get("repaymentFrequency") == "biweekly" else 1

        disbursement = loan_data.get("disbursementDate", "01 January 2024")

        payload = {
            "clientId": client_id,
            "productId": loan_data.get("productId", 1),
            "loanType": "individual",
            "principal": loan_data.get("principal", 0),
            "loanTermFrequency": loan_data.get("numberOfRepayments", 12),
            "loanTermFrequencyType": freq_type,
            "numberOfRepayments": loan_data.get("numberOfRepayments", 12),
            "repaymentEvery": repay_every,
            "repaymentFrequencyType": freq_type,
            "interestRatePerPeriod": loan_data.get("interestRate", 0),
            "amortizationType": 1,       # equal installments
            "interestType": 0,           # declining balance
            "interestCalculationPeriodType": 1,
            "transactionProcessingStrategyCode": "mifos-standard-strategy",
            "expectedDisbursementDate": disbursement,
            "submittedOnDate": disbursement,
            "dateFormat": "dd MMMM yyyy",
            "locale": "en",
        }

        if loan_data.get("disbursementDate"):
            # Convert YYYY-MM-DD → DD MMMM YYYY for Fineract
            from datetime import datetime
            try:
                dt = datetime.strptime(loan_data["disbursementDate"], "%Y-%m-%d")
                formatted = dt.strftime("%d %B %Y")
                payload["expectedDisbursementDate"] = formatted
                payload["submittedOnDate"] = formatted
            except ValueError:
                pass

        r = self.session.post(
            self._url("/loans"),
            json=payload,
            verify=self.verify_ssl
        )
        return self._handle(r)

    def get_client(self, client_id: int) -> dict:
        r = self.session.get(
            self._url(f"/clients/{client_id}"),
            verify=self.verify_ssl
        )
        return self._handle(r)

    def get_offices(self) -> dict:
        """GET /offices — List all branches/offices."""
        r = self.session.get(self._url("/offices"), verify=self.verify_ssl)
        return self._handle(r)

    def get_loan_products(self) -> dict:
        """GET /loanproducts — List available loan products."""
        r = self.session.get(self._url("/loanproducts"), verify=self.verify_ssl)
        return self._handle(r)

    def search_clients(self, query: str) -> dict:
        """GET /search — Find existing clients by name or ID (duplicate detection)."""
        r = self.session.get(
            self._url("/search"),
            params={"query": query, "resource": "clients"},
            verify=self.verify_ssl
        )
        return self._handle(r)

    def get_loan(self, loan_id: int) -> dict:
        """GET /loans/{id} — Fetch a loan with repayment schedule."""
        r = self.session.get(
            self._url(f"/loans/{loan_id}"),
            params={"associations": "repaymentSchedule"},
            verify=self.verify_ssl
        )
        return self._handle(r)

    def get_client_loans(self, client_id: int) -> dict:
        """GET /loans — Fetch all loans for a client."""
        r = self.session.get(
            self._url("/loans"),
            params={"externalId": client_id},
            verify=self.verify_ssl
        )
        return self._handle(r)

    def create_savings_account(self, client_id: int, product_id: int = 1) -> dict:
        """POST /savingsaccounts — Open a savings account for a client."""
        payload = {
            "clientId": client_id,
            "productId": product_id,
            "submittedOnDate": "01 January 2024",
            "dateFormat": "dd MMMM yyyy",
            "locale": "en",
        }
        r = self.session.post(
            self._url("/savingsaccounts"),
            json=payload,
            verify=self.verify_ssl
        )
        return self._handle(r)

    def get_report_list(self) -> dict:
        """GET /reports — List all saved Mifos reports."""
        r = self.session.get(self._url("/reports"), verify=self.verify_ssl)
        return self._handle(r)

    def create_report(self, report_def: dict) -> dict:
        """POST /reports — Register a new report in Mifos X."""
        r = self.session.post(
            self._url("/reports"),
            json=report_def,
            verify=self.verify_ssl
        )
        return self._handle(r)

    def bulk_import_clients(self, clients: list[dict]) -> list[dict]:
        """
        Create multiple clients sequentially, collecting results.
        Fineract doesn't have a native bulk endpoint, so we iterate.
        Returns list of {input, result} dicts.
        """
        results = []
        for client_data in clients:
            result = self.create_client(client_data)
            results.append({"input": client_data, "result": result})
        return results


def map_extracted_to_fineract(extracted: dict) -> tuple[dict, dict]:
    """
    Map LLM-extracted fields to Fineract API payloads.
    Returns (client_payload, loan_payload).
    """
    client = extracted.get("client", {})
    loan = extracted.get("loan", {})

    client_payload = {
        "firstname": client.get("firstname") or "Unknown",
        "lastname": client.get("lastname") or "Unknown",
        "middlename": client.get("middlename"),
        "mobileNo": client.get("mobileNo"),
        "dateOfBirth": client.get("dateOfBirth"),
        "externalId": client.get("nationalId"),
    }

    loan_payload = {
        "principal": loan.get("principal", 0),
        "currency": loan.get("currency", "USD"),
        "disbursementDate": loan.get("disbursementDate"),
        "repaymentFrequency": loan.get("repaymentFrequency", "monthly"),
        "numberOfRepayments": loan.get("numberOfRepayments", 12),
        "interestRate": loan.get("interestRate", 0),
    }

    return client_payload, loan_payload
