"""Plain Leaflet: medicine package leaflets in plain English for older adults.

Run: streamlit run app.py
Nothing is written to disk; uploads and results live only in the session
(st.cache_data keeps them in memory).
"""

import html
from pathlib import Path

import streamlit as st

from core.inputs import pdf_to_text
from core.pipeline import analyze
from safety.interactions import check_interactions
from safety.sections import extract_leaflet

# Card keys from the data contract, in display order: (key, title, icon)
CARDS = [
    ("what_for", "What is it for?", "💊"),
    ("how_to_use", "How to take it", "🕒"),
    ("see_doctor_now", "See a doctor now if…", "🚨"),
    ("side_effects", "Possible side effects", "⚠️"),
    ("storage", "How to store it", "📦"),
]

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap');

:root {
    --ink: #1b1f24;
    --muted: #4a5360;
    --bg: #fbf8f3;
    --card: #ffffff;
    --line: #ddd6ca;
    --primary: #0b5394;
    --blue: #0b5394;   --blue-bg: #e8f0fa;
    --green: #1e6b3a;  --green-bg: #e7f4ec;
    --red: #b3261e;    --red-bg: #fdecea;
    --amber: #7a5200;  --amber-bg: #fff4d6;
    --purple: #5b3d8f; --purple-bg: #f1ecf8;
}

/* Larger base size: Streamlit sizes everything in rem */
html { font-size: 20px; }
html, body, .stApp, [data-testid="stMarkdownContainer"], p, li, h1, h2, h3, small, label, button, input, textarea, summary {
    font-family: 'Atkinson Hyperlegible', 'Segoe UI', Arial, sans-serif !important;
}
.stApp { background: var(--bg); color: var(--ink); }
.block-container { padding-top: 2rem; max-width: 46rem; }

/* Hide Streamlit chrome so the demo shows only the app */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none; }

/* Header */
.hero { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.6rem; }
.hero-icon {
    font-size: 2.4rem; background: var(--blue-bg); border-radius: 18px;
    width: 3.4rem; height: 3.4rem; display: flex; align-items: center; justify-content: center;
}
.hero h1 { margin: 0; padding: 0; font-size: 2.1rem; color: var(--ink); }
.hero p { margin: 0; color: var(--muted); font-size: 1.05rem; }

.notice {
    display: flex; gap: 0.6rem; align-items: flex-start;
    border-radius: 12px; padding: 0.8rem 1rem; margin: 0.8rem 0; font-weight: 700;
}
.notice-info { background: var(--amber-bg); border: 2px solid var(--amber); color: var(--ink); }
.notice-warn { background: var(--amber-bg); border: 2px solid var(--amber); color: var(--ink); }
.notice-ok   { background: var(--green-bg); border: 2px solid var(--green); color: var(--ink); }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 0.5rem; flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] {
    background: var(--card); border: 2px solid var(--line); border-bottom: none;
    border-radius: 12px 12px 0 0; padding: 0.5rem 1rem; height: auto;
}
.stTabs [data-baseweb="tab"] p { font-size: 1.05rem; font-weight: 700; }
.stTabs [aria-selected="true"] { border-color: var(--primary); background: var(--blue-bg); }

/* Steps */
.steps { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.6rem 0 1rem; }
.step {
    flex: 1 1 10rem; background: var(--card); border: 2px solid var(--line);
    border-radius: 12px; padding: 0.5rem 0.7rem; color: var(--ink);
}
.step b {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.5rem; height: 1.5rem; border-radius: 50%;
    background: var(--primary); color: #fff; margin-right: 0.4rem; font-size: 0.85rem;
}

/* Inputs and buttons */
[data-testid="stFileUploader"] section { border: 2px dashed var(--primary); background: var(--card); }
.stTextArea textarea { border: 2px solid var(--line); background: var(--card); }
.stButton button { min-height: 3rem; border-radius: 12px; }
.stButton button p { font-size: 1.15rem; font-weight: 700; }
[data-testid="stWidgetLabel"] p { font-size: 1rem; font-weight: 700; color: var(--ink); }
.stButton button[kind="primary"] { background: var(--primary); border-color: var(--primary); }
.or { text-align: center; color: var(--muted); font-weight: 700; margin: 0.3rem 0; }

/* Result */
.drug {
    background: var(--primary); color: #fff; border-radius: 14px;
    padding: 0.9rem 1.2rem; margin: 1.2rem 0 0.6rem;
}
.drug small { opacity: 0.9; font-size: 0.85rem; }
.drug h2 { color: #fff; margin: 0; padding: 0; font-size: 1.5rem; }

.card {
    background: var(--card); border: 2px solid var(--line); border-left: 8px solid var(--accent);
    border-radius: 14px; padding: 0.9rem 1.2rem; margin: 0.8rem 0;
}
.card-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem; }
.card-icon {
    font-size: 1.4rem; background: var(--accent-bg); border-radius: 10px;
    width: 2.3rem; height: 2.3rem; display: flex; align-items: center; justify-content: center;
}
.card h3 { margin: 0; padding: 0; font-size: 1.3rem; color: var(--accent); }
.card ul { margin: 0.2rem 0 0; padding-left: 1.2rem; }
.card li { margin: 0.5rem 0; }
.card li p { margin: 0; }
.card .empty { color: var(--muted); margin: 0.2rem 0 0; }
.card details { margin-top: 0.2rem; }
.card summary {
    cursor: pointer; color: var(--primary); font-weight: 700; font-size: 0.9rem;
    display: inline-block; padding: 0.1rem 0;
}
.card .quote {
    margin: 0.4rem 0 0; padding: 0.5rem 0.8rem; background: var(--accent-bg);
    border-left: 4px solid var(--accent); border-radius: 6px; font-size: 0.9rem; color: var(--ink) !important;
}
.card-what_for       { --accent: var(--blue);   --accent-bg: var(--blue-bg); }
.card-how_to_use     { --accent: var(--green);  --accent-bg: var(--green-bg); }
.card-see_doctor_now { --accent: var(--red);    --accent-bg: var(--red-bg); background: #fffafa; }
.card-side_effects   { --accent: var(--amber);  --accent-bg: var(--amber-bg); }
.card-storage        { --accent: var(--purple); --accent-bg: var(--purple-bg); }
.card-questions      { --accent: var(--blue);   --accent-bg: var(--blue-bg); }
.card .hint { color: var(--muted); font-size: 0.9rem; margin: 0 0 0.2rem; }

/* Interaction warnings */
.alert {
    background: var(--red-bg); border: 3px solid var(--red); border-radius: 14px;
    padding: 1rem 1.2rem; margin: 0.8rem 0; color: var(--ink);
}
.alert h3 { color: var(--red); margin: 0 0 0.3rem; padding: 0; font-size: 1.3rem; }
.alert p { margin: 0.3rem 0; }
.alert .quote {
    margin: 0.4rem 0; padding: 0.5rem 0.8rem; background: #fff;
    border-left: 4px solid var(--red); border-radius: 6px; font-size: 0.9rem; color: var(--ink) !important;
}
.alert small { color: var(--muted); }
.summary { font-size: 1.15rem; font-weight: 700; margin: 1rem 0 0.2rem; }
</style>
"""


class _ErrorResult(Exception):
    """Raised inside cached functions so error results are not cached."""

    def __init__(self, result: dict):
        self.result = result


@st.cache_data(show_spinner=False)
def _explain_cached(text: str) -> dict:
    result = analyze(text)
    if not isinstance(result, dict) or result.get("error"):
        raise _ErrorResult(result)
    return result


def explain(text: str) -> dict:
    """analyze() with caching, so the same leaflet never costs a second model call."""
    try:
        return _explain_cached(text)
    except _ErrorResult as e:
        return e.result if isinstance(e.result, dict) else {}


@st.cache_data(show_spinner=False)
def leaflet_from_pdf(data: bytes) -> str:
    """Return leaflet text from PDF bytes, or "" if it cannot be read."""
    return extract_leaflet(pdf_to_text(data))


def drug_label(upload) -> str:
    """Use the file name without extension as the drug name."""
    return Path(upload.name).stem.replace("_", " ").strip() or upload.name


def esc(value) -> str:
    return html.escape(str(value or ""))


def notice(kind: str, icon: str, text: str) -> None:
    st.markdown(f'<div class="notice notice-{kind}"><span>{icon}</span><span>{esc(text)}</span></div>',
                unsafe_allow_html=True)


def steps(*labels: str) -> None:
    parts = "".join(f'<div class="step"><b>{i}</b>{esc(label)}</div>' for i, label in enumerate(labels, 1))
    st.markdown(f'<div class="steps">{parts}</div>', unsafe_allow_html=True)


def card_html(key: str, title: str, icon: str, items: list) -> str:
    """One result card. HTML is built on one line so Markdown does not treat it as code."""
    rows = []
    for item in items:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        source = ""
        if item.get("evidence"):
            source = (f'<details><summary>Show source</summary>'
                      f'<div class="quote">{esc(item["evidence"])}</div></details>')
        rows.append(f'<li><p>{esc(item["text"])}</p>{source}</li>')
    body = f'<ul>{"".join(rows)}</ul>' if rows else \
        '<p class="empty">The leaflet does not say anything about this.</p>'
    return (f'<div class="card card-{key}"><div class="card-head"><span class="card-icon">{icon}</span>'
            f'<h3>{esc(title)}</h3></div>{body}</div>')


def show_result(result: dict) -> None:
    """Render the analyze() output as five cards and a question list."""
    if not isinstance(result, dict) or not result or result.get("error"):
        message = result.get("error") if isinstance(result, dict) else None
        st.error(message or "Something went wrong. Please try again.")
        return

    if result.get("drug_name"):
        st.markdown(f'<div class="drug"><small>Your medicine</small><h2>{esc(result["drug_name"])}</h2></div>',
                    unsafe_allow_html=True)

    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    if verification.get("confidence") == "low":
        notice("warn", "⚠️", "Please check this with your pharmacist.")

    cards = result.get("cards") if isinstance(result.get("cards"), dict) else {}
    html_cards = "".join(card_html(key, title, icon, cards.get(key) or []) for key, title, icon in CARDS)
    st.markdown(html_cards, unsafe_allow_html=True)

    questions = [q for q in result.get("pharmacist_questions") or [] if q]
    if questions:
        rows = "".join(f"<li><p>{esc(q)}</p></li>" for q in questions)
        st.markdown(
            f'<div class="card card-questions"><div class="card-head"><span class="card-icon">❓</span>'
            f'<h3>Questions for my pharmacist</h3></div>'
            f'<p class="hint">Take this list with you to the pharmacy.</p><ul>{rows}</ul></div>',
            unsafe_allow_html=True,
        )


def show_warnings(warnings: list[dict]) -> None:
    """Render interaction warnings as red cards with the leaflet quote."""
    if not warnings:
        notice("ok", "✅", "No warnings were found in these leaflets.")
        notice("info", "ℹ️", "This check only finds medicine names written in the leaflets. "
                             "Always tell your pharmacist about all the medicines you take.")
        return

    count = len(warnings)
    st.markdown(f'<p class="summary">We found {count} warning{"s" if count > 1 else ""}.</p>',
                unsafe_allow_html=True)
    for warning in warnings:
        drug_a, drug_b = esc(warning.get("drug_a")), esc(warning.get("drug_b"))
        st.markdown(
            f'<div class="alert"><h3>⚠️ {drug_a} + {drug_b}</h3>'
            f'<p><b>{esc(warning.get("message"))}</b></p>'
            f'<p>The leaflet of <b>{drug_a}</b> says:</p>'
            f'<div class="quote">{esc(warning.get("evidence"))}</div>'
            f'<small>Found the word “{esc(warning.get("matched"))}”.</small></div>',
            unsafe_allow_html=True,
        )


def explain_tab() -> None:
    steps("Upload or paste the leaflet", "Press Explain", "Read the cards")
    upload = st.file_uploader("Upload the leaflet (PDF)", type=["pdf"], key="explain_pdf")
    st.markdown('<p class="or">or</p>', unsafe_allow_html=True)
    pasted = st.text_area("Paste the leaflet text here", height=180, key="explain_text")

    if st.button("Explain", type="primary", key="explain_button", use_container_width=True):
        text = leaflet_from_pdf(upload.getvalue()) if upload else extract_leaflet(pasted.strip())
        if not text.strip():
            st.session_state.pop("explain_result", None)
            notice("warn", "⚠️", "We could not read any text. Please upload a PDF leaflet or paste its text.")
        else:
            with st.spinner("Reading the leaflet… This can take about 30 seconds."):
                st.session_state["explain_result"] = explain(text)

    if "explain_result" in st.session_state:
        show_result(st.session_state["explain_result"])


def medicines_tab() -> None:
    steps("Upload all your leaflets", "Press Check", "Read the warnings")
    uploads = st.file_uploader("Upload two or more leaflets (PDF)", type=["pdf"],
                               accept_multiple_files=True, key="medicines_pdfs")

    if st.button("Check my medicines", type="primary", key="medicines_button", use_container_width=True):
        if len(uploads or []) < 2:
            st.session_state.pop("medicines_result", None)
            notice("warn", "⚠️", "Please upload at least two leaflets.")
        else:
            leaflets, unreadable = {}, []
            with st.spinner("Checking the leaflets…"):
                for upload in uploads:
                    text = leaflet_from_pdf(upload.getvalue())
                    if text.strip():
                        leaflets[drug_label(upload)] = text
                    else:
                        unreadable.append(upload.name)
                st.session_state["medicines_result"] = check_interactions(leaflets)
            if unreadable:
                notice("warn", "⚠️", "We could not read: " + ", ".join(unreadable))

    if "medicines_result" in st.session_state:
        show_warnings(st.session_state["medicines_result"])


def main() -> None:
    st.set_page_config(page_title="Plain Leaflet", page_icon="💊", layout="centered")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.markdown(
        '<div class="hero"><div class="hero-icon">💊</div><div><h1>Plain Leaflet</h1>'
        '<p>Your medicine leaflet, in plain English.</p></div></div>',
        unsafe_allow_html=True,
    )
    notice("info", "ℹ️", "This tool does not replace your doctor or pharmacist.")

    explain, medicines = st.tabs(["💊 Explain my medicine", "🧺 My medicines"])
    with explain:
        explain_tab()
    with medicines:
        medicines_tab()


main()
