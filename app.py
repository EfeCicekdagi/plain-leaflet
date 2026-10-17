"""Plain Leaflet: medicine package leaflets in plain English for older adults.

Run: streamlit run app.py
Nothing is written to disk; uploads and results live only in the session.
"""

import html
from pathlib import Path

import streamlit as st

from core.inputs import pdf_to_text
from core.pipeline import analyze
from safety.interactions import check_interactions
from safety.sections import extract_leaflet

# Card keys from the data contract, in display order, with their titles
CARDS = [
    ("what_for", "What is it for?"),
    ("how_to_use", "How to take it"),
    ("see_doctor_now", "See a doctor now if…"),
    ("side_effects", "Possible side effects"),
    ("storage", "How to store it"),
]

STYLE = """
<style>
html, body, [class*="css"], p, li, label, .stMarkdown, .stTextArea textarea {
    font-size: 20px !important;
    line-height: 1.5;
}
h1 { font-size: 40px !important; }
h2 { font-size: 32px !important; }
h3 { font-size: 26px !important; }
.stButton button, .stDownloadButton button {
    font-size: 22px !important;
    padding: 0.6em 1.6em;
    min-height: 3em;
}
.stTabs [data-baseweb="tab"] p { font-size: 22px !important; font-weight: 600; }
.disclaimer {
    background: #fff4ce;
    color: #1a1a1a;
    border: 2px solid #8a6d00;
    border-radius: 8px;
    padding: 0.8em 1em;
    font-weight: 600;
    margin-bottom: 1em;
}
.warning-card {
    background: #fde7e9;
    color: #1a1a1a;
    border: 3px solid #b00020;
    border-radius: 10px;
    padding: 1em 1.2em;
    margin-bottom: 1em;
}
.warning-card h3 { color: #b00020; margin-top: 0; }
.warning-card blockquote {
    border-left: 4px solid #b00020;
    margin: 0.6em 0;
    padding-left: 0.8em;
    font-style: italic;
}
</style>
"""


def read_upload(upload) -> str:
    """Return leaflet text from an uploaded PDF, or "" if it cannot be read."""
    if upload is None:
        return ""
    return extract_leaflet(pdf_to_text(upload.getvalue()))


def drug_label(upload) -> str:
    """Use the file name without extension as the drug name."""
    return Path(upload.name).stem.replace("_", " ").strip() or upload.name


def show_result(result: dict) -> None:
    """Render the analyze() output as five cards and a question list."""
    if not isinstance(result, dict) or result.get("error"):
        message = result.get("error") if isinstance(result, dict) else None
        st.error(message or "Something went wrong. Please try again.")
        return

    if result.get("drug_name"):
        st.header(result["drug_name"])

    if result.get("verification", {}).get("confidence") == "low":
        st.warning("Please check this with your pharmacist.")

    cards = result.get("cards", {})
    for key, title in CARDS:
        with st.container(border=True):
            st.subheader(title)
            items = cards.get(key) or []
            if not items:
                st.write("The leaflet does not say anything about this.")
            for item in items:
                st.markdown(f"- {item.get('text', '')}")
                if item.get("evidence"):
                    with st.expander("Show source"):
                        st.markdown(f"> {item['evidence']}")

    questions = result.get("pharmacist_questions") or []
    if questions:
        with st.container(border=True):
            st.subheader("Questions for my pharmacist")
            for question in questions:
                st.markdown(f"- {question}")


def show_warnings(warnings: list[dict]) -> None:
    """Render interaction warnings as red cards with the leaflet quote."""
    if not warnings:
        st.success("No warnings were found in these leaflets.")
        st.info("This check only finds medicine names written in the leaflets. "
                "Always tell your pharmacist about all the medicines you take.")
        return

    for warning in warnings:
        drug_a = html.escape(warning.get("drug_a", ""))
        drug_b = html.escape(warning.get("drug_b", ""))
        evidence = html.escape(warning.get("evidence", ""))
        message = html.escape(warning.get("message", ""))
        st.markdown(
            f"""<div class="warning-card">
<h3>{drug_a} + {drug_b}</h3>
<p>{message}</p>
<p>The leaflet of <b>{drug_a}</b> says:</p>
<blockquote>{evidence}</blockquote>
</div>""",
            unsafe_allow_html=True,
        )


def explain_tab() -> None:
    st.write("Upload your medicine's leaflet or paste its text. "
             "We will explain it in plain English.")
    upload = st.file_uploader("Upload the leaflet (PDF)", type=["pdf"], key="explain_pdf")
    pasted = st.text_area("Or paste the leaflet text here", height=200, key="explain_text")

    if st.button("Explain", type="primary", key="explain_button"):
        text = read_upload(upload) if upload else extract_leaflet(pasted.strip())
        if not text.strip():
            st.session_state.pop("explain_result", None)
            st.warning("We could not read any text. Please upload a PDF leaflet or paste its text.")
        else:
            with st.spinner("Reading the leaflet…"):
                st.session_state["explain_result"] = analyze(text)

    if "explain_result" in st.session_state:
        show_result(st.session_state["explain_result"])


def medicines_tab() -> None:
    st.write("Upload the leaflets of all the medicines you take. "
             "We will look for warnings about taking them together.")
    uploads = st.file_uploader("Upload two or more leaflets (PDF)", type=["pdf"],
                               accept_multiple_files=True, key="medicines_pdfs")

    if st.button("Check my medicines", type="primary", key="medicines_button"):
        if len(uploads or []) < 2:
            st.session_state.pop("medicines_result", None)
            st.warning("Please upload at least two leaflets.")
        else:
            leaflets = {}
            unreadable = []
            for upload in uploads:
                text = read_upload(upload)
                if text.strip():
                    leaflets[drug_label(upload)] = text
                else:
                    unreadable.append(upload.name)
            if unreadable:
                st.warning("We could not read: " + ", ".join(unreadable))
            with st.spinner("Checking the leaflets…"):
                st.session_state["medicines_result"] = check_interactions(leaflets)

    if "medicines_result" in st.session_state:
        show_warnings(st.session_state["medicines_result"])


def main() -> None:
    st.set_page_config(page_title="Plain Leaflet", layout="centered")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.title("Plain Leaflet")
    st.markdown('<div class="disclaimer">This tool does not replace your doctor or pharmacist.</div>',
                unsafe_allow_html=True)

    explain, medicines = st.tabs(["Explain my medicine", "My medicines"])
    with explain:
        explain_tab()
    with medicines:
        medicines_tab()


main()
