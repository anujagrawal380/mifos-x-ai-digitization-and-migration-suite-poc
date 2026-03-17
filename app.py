"""
app.py — Mifos X AI Digitization & Migration Suite.

Three use cases from the GSoC project brief:
  Page 1 — Paper Digitizer   : scan → OCR → LLM → Fineract API
  Page 2 — Report Migrator   : legacy report image → Mifos report definition
  Page 3 — Data Migration    : legacy CSV → field mapping → bulk import

Run: streamlit run app.py
"""

import streamlit as st
from PIL import Image
import json
import os
import pandas as pd
import io
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Mifos AI Suite",
    page_icon="🏦",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
for key in ["extracted", "ocr_result", "uploaded_image",
            "report_analysis", "migration_mapping", "migration_df",
            "audit_log", "fineract_offices", "fineract_loan_products"]:
    if key not in st.session_state:
        st.session_state[key] = None

if "audit_log" not in st.session_state or st.session_state.audit_log is None:
    st.session_state.audit_log = []

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@st.cache_resource
def get_fineract_client():
    from fineract import FineractClient
    return FineractClient()


def confidence_badge(score: float) -> str:
    color = "green" if score >= 0.85 else ("orange" if score >= 0.65 else "red")
    return f":{color}[**{int(score * 100)}% confidence**]"


def log_audit(action: str, details: dict):
    import datetime
    st.session_state.audit_log.append({
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        **details,
    })


def render_field(label: str, value, uncertain: list, key: str) -> str:
    is_uncertain = label.lower().replace(" ", "_") in [u.lower() for u in uncertain]
    display = f"⚠️ {label}" if is_uncertain else label
    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown(f"**{display}**")
    with col2:
        return st.text_input(label, value=str(value) if value else "",
                             key=key, label_visibility="collapsed")


def load_fineract_metadata(fc):
    """Fetch offices and loan products from live Fineract and cache in session."""
    if st.session_state.fineract_offices is None:
        res = fc.get_offices()
        if res["success"]:
            st.session_state.fineract_offices = {
                o["name"]: o["id"] for o in res["data"]
            }
    if st.session_state.fineract_loan_products is None:
        res = fc.get_loan_products()
        if res["success"]:
            st.session_state.fineract_loan_products = {
                p["name"]: p["id"] for p in res["data"]
            }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Config")

    backend = st.selectbox("LLM Backend", ["groq", "gemini", "ollama"], index=0)
    os.environ["LLM_BACKEND"] = backend

    st.divider()
    st.subheader("Fineract Connection")
    fineract_url = st.text_input(
        "Base URL",
        value=os.getenv("FINERACT_BASE_URL",
                        "https://localhost:8443/fineract-provider/api/v1")
    )
    os.environ["FINERACT_BASE_URL"] = fineract_url

    col_a, col_b = st.columns(2)
    with col_a:
        fineract_user = st.text_input("User", value="mifos")
        os.environ["FINERACT_USERNAME"] = fineract_user
    with col_b:
        fineract_pass = st.text_input("Password", value="password", type="password")
        os.environ["FINERACT_PASSWORD"] = fineract_pass

    fineract_ok = False
    if st.button("Test Connection", use_container_width=True):
        fc = get_fineract_client()
        fineract_ok = fc.health_check()
        if fineract_ok:
            st.success("Connected")
            # Force-refresh metadata on every connect (products may have changed)
            st.session_state.fineract_offices = None
            st.session_state.fineract_loan_products = None
            load_fineract_metadata(fc)
        else:
            st.warning("Offline — AI features still work")

    # Show live Fineract data
    if st.session_state.fineract_offices:
        st.caption(f"Offices loaded: {len(st.session_state.fineract_offices)}")
    if st.session_state.fineract_loan_products:
        st.caption(f"Loan products: {len(st.session_state.fineract_loan_products)}")

    st.divider()
    # Audit log download
    if st.session_state.audit_log:
        audit_json = json.dumps(st.session_state.audit_log, indent=2)
        st.download_button(
            "Download Audit Log",
            data=audit_json,
            file_name="audit_log.json",
            mime="application/json",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Page selector
# ---------------------------------------------------------------------------
page = st.radio(
    "Use Case",
    ["📄 Paper Digitizer", "📊 Report Migrator", "🔄 Data Migration"],
    horizontal=True,
    label_visibility="collapsed",
)
st.divider()


# ===========================================================================
# PAGE 1 — Paper Digitizer
# ===========================================================================
if page == "📄 Paper Digitizer":
    st.title("Paper Record Digitizer")
    st.caption("Scan a paper loan/client form → AI extracts fields → submit directly to Mifos X.")

    tab_upload, tab_review, tab_raw = st.tabs(["Upload", "Review & Submit", "Raw Output"])

    with tab_upload:
        col_left, col_right = st.columns([1, 1])
        with col_left:
            uploaded = st.file_uploader("Upload scanned form", type=["jpg", "jpeg", "png"])

            sample_dir = os.path.join(os.path.dirname(__file__), "sample_forms")
            samples = sorted([f for f in os.listdir(sample_dir)
                              if f.endswith(".png")]) if os.path.exists(sample_dir) else []
            selected = st.selectbox("Or use a sample form", ["— none —"] + samples)
            extract_btn = st.button("Extract Data", type="primary", use_container_width=True)

        with col_right:
            image = None
            if uploaded:
                image = Image.open(uploaded)
            elif selected != "— none —":
                image = Image.open(os.path.join(sample_dir, selected))
            if image is not None:
                st.image(image, use_container_width=True)
                st.session_state.uploaded_image = image

        if extract_btn:
            if image is None:
                st.error("Upload an image or select a sample.")
            else:
                with st.spinner("Running OCR..."):
                    from ocr import extract_text
                    ocr_result = extract_text(image)
                    st.session_state.ocr_result = ocr_result

                st.markdown(f"OCR: {confidence_badge(ocr_result['avg_ocr_confidence'])} "
                            f"— {ocr_result['word_count']} words detected")

                with st.spinner(f"Extracting fields ({backend})..."):
                    try:
                        from llm import extract_fields
                        extracted = extract_fields(ocr_result["raw_text"], image)
                        st.session_state.extracted = extracted
                        log_audit("extraction", {
                            "source": selected if selected != "— none —" else "upload",
                            "ocr_confidence": ocr_result["avg_ocr_confidence"],
                            "llm_confidence": extracted.get("meta", {}).get("overallConfidence"),
                            "uncertain_fields": extracted.get("meta", {}).get("uncertainFields", []),
                        })
                        st.success("Done — switch to **Review & Submit**")
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")
                        with st.expander("Debug: error details"):
                            st.code(str(e))
                            st.caption("If this says 'GEMINI_API_KEY not set' or 'API key not valid', "
                                       "add your key to the .env file (copy .env.example → .env).")

    with tab_review:
        if not st.session_state.extracted:
            st.info("Extract a form first.")
        else:
            extracted = st.session_state.extracted
            client_data = extracted.get("client", {})
            loan_data = extracted.get("loan", {})
            meta = extracted.get("meta", {})
            uncertain = meta.get("uncertainFields", [])

            # Duplicate detection (skip gracefully if Fineract offline)
            fc = get_fineract_client()
            name_query = f"{client_data.get('firstname', '')} {client_data.get('lastname', '')}".strip()
            if name_query:
                try:
                    dup_result = fc.search_clients(name_query)
                    if dup_result["success"] and dup_result["data"]:
                        st.warning(f"Possible duplicate: **{len(dup_result['data'])}** existing client(s) "
                                   f"match '{name_query}'. Review before submitting.")
                        with st.expander("View potential duplicates"):
                            st.json(dup_result["data"])
                except Exception:
                    pass  # Fineract offline — skip duplicate check silently

            cols = st.columns(3)
            cols[0].metric("Confidence", f"{int(meta.get('overallConfidence', 0) * 100)}%")
            cols[1].metric("Language", meta.get("detectedLanguage", "?"))
            cols[2].metric("Has Handwriting", "Yes" if meta.get("hasHandwriting") else "No")

            if uncertain:
                st.warning(f"Verify these fields: **{', '.join(uncertain)}**")

            st.divider()
            col_c, col_l = st.columns(2)

            with col_c:
                st.subheader("Client")
                firstname = render_field("First Name", client_data.get("firstname"), uncertain, "fn")
                lastname = render_field("Last Name", client_data.get("lastname"), uncertain, "ln")
                middlename = render_field("Middle Name", client_data.get("middlename"), uncertain, "mn")
                dob = render_field("Date of Birth", client_data.get("dateOfBirth"), uncertain, "dob")
                gender = render_field("Gender", client_data.get("gender"), uncertain, "gen")
                mobile = render_field("Mobile No.", client_data.get("mobileNo"), uncertain, "mob")
                national_id = render_field("National ID", client_data.get("nationalId"), uncertain, "nid")
                address = render_field("Address", client_data.get("address"), uncertain, "addr")

                # Office selector populated from live Fineract
                offices = st.session_state.fineract_offices or {"Head Office": 1}
                selected_office = st.selectbox("Office / Branch", list(offices.keys()))
                office_id = offices[selected_office]

            with col_l:
                st.subheader("Loan")
                principal = render_field("Principal Amount", loan_data.get("principal"), uncertain, "pri")
                currency = render_field("Currency", loan_data.get("currency"), uncertain, "cur")
                disb_date = render_field("Disbursement Date", loan_data.get("disbursementDate"), uncertain, "dd")
                freq = render_field("Repayment Frequency", loan_data.get("repaymentFrequency"), uncertain, "freq")
                num_repay = render_field("No. of Repayments", loan_data.get("numberOfRepayments"), uncertain, "nr")
                interest = render_field("Interest Rate (%)", loan_data.get("interestRate"), uncertain, "ir")
                purpose = render_field("Purpose", loan_data.get("purpose"), uncertain, "pur")

                # Loan product selector from live Fineract
                products = st.session_state.fineract_loan_products or {"Default Product": 1}
                selected_product = st.selectbox("Loan Product", list(products.keys()))
                product_id = products[selected_product]

            st.divider()
            b1, b2, b3 = st.columns([1, 1, 2])

            with b1:
                fineract_live = bool(st.session_state.fineract_offices)
                submit_label = "Submit to Fineract" if fineract_live else "Submit to Fineract (connect first)"
                if st.button(submit_label, type="primary", use_container_width=True,
                             disabled=not fineract_live):
                    from fineract import FineractClient, map_extracted_to_fineract
                    edited = {
                        "client": {
                            "firstname": firstname, "lastname": lastname,
                            "middlename": middlename or None,
                            "dateOfBirth": dob or None, "gender": gender,
                            "mobileNo": mobile, "nationalId": national_id,
                            "address": address, "officeId": office_id,
                        },
                        "loan": {
                            "principal": float(principal) if principal else 0,
                            "currency": currency,
                            "disbursementDate": disb_date or None,
                            "repaymentFrequency": freq,
                            "numberOfRepayments": int(num_repay) if num_repay else 12,
                            "interestRate": float(interest) if interest else 0,
                            "purpose": purpose,
                            "productId": product_id,
                        },
                    }
                    client_payload, loan_payload = map_extracted_to_fineract(edited)
                    fc2 = FineractClient()

                    with st.spinner("Creating client..."):
                        cr = fc2.create_client(client_payload)
                    if cr["success"]:
                        cid = cr["data"]["clientId"]
                        st.success(f"Client created — ID: **{cid}**")
                        with st.spinner("Submitting loan..."):
                            lr = fc2.create_loan(cid, loan_payload)
                        if lr["success"]:
                            lid = lr["data"]["loanId"]
                            st.success(f"Loan submitted — ID: **{lid}**")
                            log_audit("fineract_submit", {
                                "clientId": cid, "loanId": lid,
                                "auto_fields": [f for f in ["firstname", "lastname", "principal"]
                                               if f not in uncertain],
                                "human_verified": uncertain,
                            })
                            st.balloons()
                        else:
                            st.error(f"Loan failed: {lr.get('detail', lr.get('error'))}")
                    else:
                        st.error(f"Client failed: {cr.get('detail', cr.get('error'))}")

            with b2:
                st.download_button(
                    "Export JSON",
                    data=json.dumps(extracted, indent=2),
                    file_name="extracted.json",
                    mime="application/json",
                    use_container_width=True,
                )

    with tab_raw:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("OCR Output")
            if st.session_state.ocr_result:
                ocr = st.session_state.ocr_result
                st.metric("Avg Confidence", f"{int(ocr['avg_ocr_confidence'] * 100)}%")
                st.text_area("Raw text", ocr["raw_text"], height=350)
        with c2:
            st.subheader("LLM JSON")
            if st.session_state.extracted:
                st.json(st.session_state.extracted)


# ===========================================================================
# PAGE 2 — Report Migrator
# ===========================================================================
elif page == "📊 Report Migrator":
    st.title("Report Template Migrator")
    st.caption("Upload an existing report (from any system) → AI generates a Mifos X report definition.")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Input")
        report_upload = st.file_uploader("Upload report template image", type=["png", "jpg", "jpeg"])

        use_sample = st.button("Generate & Use Sample Report", use_container_width=True)

        if use_sample:
            with st.spinner("Generating sample legacy report..."):
                from report_template import generate_sample_report_image
                sample_img = generate_sample_report_image()
                st.session_state.report_image = sample_img
                st.success("Sample report generated.")

        analyze_btn = st.button("Analyze Report Template", type="primary", use_container_width=True)

    with col_right:
        st.subheader("Preview")
        report_image = None
        if report_upload:
            report_image = Image.open(report_upload)
            st.session_state.report_image = report_image
        elif hasattr(st.session_state, "report_image") and st.session_state.report_image:
            report_image = st.session_state.report_image

        if report_image is not None:
            st.image(report_image, use_container_width=True)

    if analyze_btn:
        ri = getattr(st.session_state, "report_image", None)
        if ri is None:
            st.error("Upload or generate a report image first.")
        else:
            with st.spinner("Running OCR on report..."):
                from ocr import extract_text
                ocr = extract_text(ri)

            with st.spinner(f"Analyzing structure with {backend}..."):
                try:
                    from report_template import analyze_report_template, build_fineract_report_payload
                    analysis = analyze_report_template(ri, ocr["raw_text"])
                    st.session_state.report_analysis = analysis
                    log_audit("report_analysis", {
                        "reportName": analysis.get("reportName"),
                        "reportType": analysis.get("reportType"),
                        "confidence": analysis.get("confidence"),
                    })
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

    if st.session_state.report_analysis:
        analysis = st.session_state.report_analysis
        from report_template import build_fineract_report_payload

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Report Type", analysis.get("reportType", "?"))
        c2.metric("Category", analysis.get("reportCategory", "?"))
        c3.metric("Confidence", f"{int(analysis.get('confidence', 0) * 100)}%")

        tab_def, tab_sql, tab_json = st.tabs(["Report Definition", "SQL Query", "Full JSON"])

        with tab_def:
            st.subheader(analysis.get("reportName", "Unnamed Report"))
            st.caption(analysis.get("description", ""))

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Columns detected:**")
                for col in analysis.get("columns", []):
                    st.markdown(f"- `{col['name']}` ({col.get('dataType', '?')}) — {col.get('label', '')}")
            with col_b:
                st.markdown("**Filter parameters:**")
                for f in analysis.get("filters", []):
                    st.markdown(f"- `{f['name']}` ({f.get('type', '?')}) — {f.get('label', '')}")

            st.markdown("**Mifos API endpoints used:**")
            for ep in analysis.get("mifosApiEndpoints", []):
                st.code(ep)

            if analysis.get("notes"):
                st.info(f"Notes: {analysis['notes']}")

        with tab_sql:
            sql = analysis.get("suggestedSQL", "-- No SQL generated")
            st.code(sql, language="sql")

        with tab_json:
            payload = build_fineract_report_payload(analysis)
            st.json(payload)

        st.divider()
        b1, b2 = st.columns([1, 3])
        with b1:
            fineract_live = bool(st.session_state.fineract_offices)
            if st.button("Register in Fineract", type="primary", disabled=not fineract_live):
                from report_template import build_fineract_report_payload
                from fineract import FineractClient
                payload = build_fineract_report_payload(analysis)
                fc = FineractClient()
                with st.spinner("Registering report..."):
                    result = fc.create_report(payload)
                if result["success"]:
                    st.success(f"Report registered. ID: {result['data'].get('resourceId')}")
                    log_audit("report_registered", {"reportName": analysis.get("reportName")})
                else:
                    st.error(f"Failed: {result.get('detail', result.get('error'))}")

        with b2:
            payload = build_fineract_report_payload(analysis)
            st.download_button(
                "Download Report Definition JSON",
                data=json.dumps(payload, indent=2),
                file_name=f"{analysis.get('reportName', 'report').replace(' ', '_')}.json",
                mime="application/json",
            )


# ===========================================================================
# PAGE 3 — Data Migration
# ===========================================================================
elif page == "🔄 Data Migration":
    st.title("Legacy System Data Migration")
    st.caption("Upload a CSV from any legacy MFI system → AI maps columns → bulk import to Mifos X.")

    tab_upload, tab_mapping, tab_import = st.tabs(["Upload CSV", "Column Mapping", "Bulk Import"])

    with tab_upload:
        col_l, col_r = st.columns([1, 1])
        with col_l:
            csv_upload = st.file_uploader("Upload legacy system CSV", type=["csv", "xlsx"])

            if st.button("Use Sample Legacy CSV", use_container_width=True):
                from migration import generate_sample_legacy_csv
                csv_str = generate_sample_legacy_csv()
                df = pd.read_csv(io.StringIO(csv_str))
                st.session_state.migration_df = df
                st.success("Sample CSV loaded.")

            map_btn = st.button("Analyze Column Mapping", type="primary", use_container_width=True)

        with col_r:
            if csv_upload:
                if csv_upload.name.endswith(".xlsx"):
                    df = pd.read_excel(csv_upload)
                else:
                    df = pd.read_csv(csv_upload)
                st.session_state.migration_df = df

            if st.session_state.migration_df is not None:
                df = st.session_state.migration_df
                st.metric("Rows", len(df))
                st.metric("Columns", len(df.columns))
                st.dataframe(df.head(5), use_container_width=True)

        if map_btn:
            if st.session_state.migration_df is None:
                st.error("Load a CSV first.")
            else:
                with st.spinner(f"Analyzing column mappings with {backend}..."):
                    try:
                        from migration import analyze_csv_mapping
                        mapping = analyze_csv_mapping(st.session_state.migration_df)
                        st.session_state.migration_mapping = mapping
                        log_audit("migration_mapping", {
                            "columns": list(st.session_state.migration_df.columns),
                            "detectedEntity": mapping.get("detectedEntity"),
                            "confidence": mapping.get("overallConfidence"),
                            "warnings": mapping.get("warnings", []),
                        })
                        st.success("Mapping done — switch to **Column Mapping** tab.")
                    except Exception as e:
                        st.error(f"Mapping failed: {e}")

    with tab_mapping:
        if not st.session_state.migration_mapping:
            st.info("Run column mapping analysis first.")
        else:
            mapping = st.session_state.migration_mapping

            c1, c2, c3 = st.columns(3)
            c1.metric("Entity Type", mapping.get("detectedEntity", "?").capitalize())
            c2.metric("Records", mapping.get("estimatedRecords", "?"))
            c3.metric("Confidence", f"{int(mapping.get('overallConfidence', 0) * 100)}%")

            if mapping.get("warnings"):
                for w in mapping["warnings"]:
                    st.warning(w)

            st.subheader("Column Mappings")
            st.caption("Edit Fineract Field or Transformation if needed, then proceed to Import.")

            mappings = mapping.get("mappings", [])
            edited_mappings = []
            for i, m in enumerate(mappings):
                conf = m.get("confidence", 0)
                badge = "green" if conf >= 0.85 else ("orange" if conf >= 0.65 else "red")
                with st.expander(f":{badge}[{m['sourceColumn']}]  →  `{m.get('fineractField') or 'unmapped'}`"):
                    col_a, col_b, col_c = st.columns([1, 1, 1])
                    with col_a:
                        new_field = st.text_input(
                            "Fineract Field",
                            value=m.get("fineractField") or "",
                            key=f"field_{i}"
                        )
                    with col_b:
                        new_transform = st.text_input(
                            "Transformation",
                            value=m.get("transformation") or "",
                            key=f"transform_{i}"
                        )
                    with col_c:
                        st.metric("Confidence", f"{int(conf * 100)}%")
                    if m.get("notes"):
                        st.caption(m["notes"])
                    edited_mappings.append({
                        **m,
                        "fineractField": new_field or None,
                        "transformation": new_transform or None,
                    })

            if mapping.get("unmappedColumns"):
                st.warning(f"Unmapped columns (will be ignored): "
                           f"{', '.join(mapping['unmappedColumns'])}")

            if st.button("Apply Mappings & Preview", type="primary"):
                from migration import apply_mappings, build_client_payloads
                df = st.session_state.migration_df
                mapped_df = apply_mappings(df, edited_mappings)
                st.session_state.mapped_df = mapped_df
                st.subheader("Mapped Preview")
                st.dataframe(mapped_df.head(10), use_container_width=True)

    with tab_import:
        if not hasattr(st.session_state, "mapped_df") or st.session_state.get("mapped_df") is None:
            st.info("Apply column mappings first.")
        else:
            mapped_df = st.session_state.mapped_df
            st.metric("Records ready for import", len(mapped_df))
            st.dataframe(mapped_df, use_container_width=True)

            col_opts = st.columns(2)
            with col_opts[0]:
                dry_run = st.checkbox("Dry run (validate only, don't submit)", value=True)
            with col_opts[1]:
                batch_size = st.number_input("Batch size", min_value=1, max_value=50, value=5)

            fineract_live = bool(st.session_state.fineract_offices)
            if not fineract_live and not dry_run:
                st.info("Connect to Fineract first for live import. Enable dry run to preview without connecting.")
            if st.button("Start Import", type="primary", disabled=not dry_run and not fineract_live):
                from migration import build_client_payloads
                from fineract import FineractClient

                payloads = build_client_payloads(mapped_df)
                fc = FineractClient()

                progress = st.progress(0)
                results_container = st.empty()
                results = []

                for i, payload in enumerate(payloads):
                    progress.progress((i + 1) / len(payloads))
                    if dry_run:
                        results.append({
                            "row": i + 1,
                            "status": "dry_run_ok",
                            "name": f"{payload.get('firstname', '')} {payload.get('lastname', '')}",
                            "payload_keys": list(payload.keys()),
                        })
                    else:
                        result = fc.create_client(payload)
                        results.append({
                            "row": i + 1,
                            "name": f"{payload.get('firstname', '')} {payload.get('lastname', '')}",
                            "success": result["success"],
                            "clientId": result["data"].get("clientId") if result["success"] else None,
                            "error": result.get("detail") if not result["success"] else None,
                        })

                progress.empty()
                results_df = pd.DataFrame(results)
                st.dataframe(results_df, use_container_width=True)

                success_count = sum(1 for r in results if r.get("status") == "dry_run_ok"
                                    or r.get("success"))
                st.metric("Successful", f"{success_count}/{len(results)}")

                log_audit("bulk_import", {
                    "dry_run": dry_run,
                    "total": len(results),
                    "success": success_count,
                })

                st.download_button(
                    "Download Import Results",
                    data=results_df.to_csv(index=False),
                    file_name="import_results.csv",
                    mime="text/csv",
                )
