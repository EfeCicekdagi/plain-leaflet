"""Shared settings. Only Person 1 changes this file; every other file reads its settings from here."""
import os
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent
load_dotenv(KOK / ".env")

# Model
# On 17 October gemini-3.8-flash kept single calls waiting 77-151 s under high demand; 3.6-flash processed the same leaflet in 21 s with higher confidence
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# If the main model fails with 503 (high demand) or 429 (quota), the same call is tried once more with this model.
# The free quota is per model, so this also helps when the quota runs out. Empty = off.
YEDEK_MODEL = os.getenv("GEMINI_YEDEK_MODEL", "gemini-3.5-flash").strip()
# The verifier can use a separate model (e.g. the cheaper/faster gemini-3.5-flash-lite). Defaults to MODEL_NAME.
DOGRULAYICI_MODEL = os.getenv("GEMINI_DOGRULAYICI_MODEL", MODEL_NAME)
TEMPERATURE = 0.0      # greedy decoding: medical text needs consistency, not creativity
# The model's hidden thinking budget (tokens). Off, because the prompts already ask for explicit step-by-step reasoning (analysis/reason fields):
# on the paracetamol leaflet the draft went from 40-69 s to 14 s, with the same item count and quote check result. None = model default.
_dusunme = os.getenv("GEMINI_DUSUNME", "0").strip().lower()
DUSUNME_BUTCESI = int(_dusunme) if _dusunme.isdigit() else None
MAX_CIKTI_TOKEN = 16384  # real outputs are 3-6 thousand tokens; the limit only cuts an answer stuck in a loop
LLM_RETRY = 1          # how many more times to try after an error
LLM_RETRY_WAIT = 3.0   # seconds to wait before retrying
LLM_KOTA_WAIT = 20.0   # seconds to wait after a quota error (429)

# 1 = analyze() does not call the model and returns the mock JSON
USE_MOCK = os.getenv("USE_MOCK", "0") == "1"

# File paths
PROMPT_KARTLAR = KOK / "prompts" / "01_kartlar.txt"
PROMPT_DOGRULAYICI = KOK / "prompts" / "02_dogrulayici.txt"
PROMPT_DUZELTME = KOK / "prompts" / "03_duzeltme.txt"
MOCK_ANALYZE = KOK / "mock" / "analyze_output.json"

# Verifier
DUZELTME_ACIK = True    # items the verifier rejects are rewritten once and verified again (Finalize step)
KANIT_ESIK = 0.95       # difflib similarity (whitespace removed) below this means the quote is not in the leaflet. Every real quote scored 1.0; 0.95 accepts a one-letter difference and rejects a changed word
MAX_KT_KARAKTER = 60000  # longer texts are cut (leaflets are usually 15-40 thousand characters)
MIN_KT_KARAKTER = 200    # shorter text is not treated as a leaflet
