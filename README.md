# Plain Leaflet

Plain Leaflet turns official medicine package leaflets into short, plain-English,
large-print cards for older adults. Every sentence on a card is linked to the
exact passage of the leaflet it comes from, so nothing is invented. A second tab
checks several leaflets against each other for interaction warnings.

Samsung Innovation Campus GenAI for SDGs Hackathon, Group 7.
SDG 3.8 (access to safe medicines and health information) and SDG 10.2 (inclusion of older adults).

> Plain Leaflet does not replace a doctor or pharmacist.

## What it does

**Explain my medicine.** Upload a leaflet (PDF or photo) or paste its text. The app returns:

- the medicine name,
- five cards: *What is it for?*, *How to take it*, *See a doctor now if…*,
  *Possible side effects*, *How to store it*,
- a **Show source** box under every sentence with the original leaflet quote,
- questions to ask your pharmacist,
- a warning when the result could not be fully verified,
- **Read aloud** (browser speech, nothing leaves the device) and a printable card.

**My medicines.** Upload two or more leaflets. The app reads each leaflet's
"Other medicines" section and warns when it mentions another uploaded medicine,
its active substance or its drug class (for example clopidogrel with esomeprazole).
This check is rule-based and does not use the model.

## How the explanation is made

1. **Extract** the patient leaflet. EMA PDFs also contain the prescriber
   information (SmPC), so only the part after "B. PACKAGE LEAFLET" is kept.
2. **Draft** the cards with Gemini. Each item has a plain sentence and a
   verbatim quote from the leaflet.
3. **Verify** every item three ways:
   - the quote must really be in the leaflet (difflib match),
   - the numbers in the sentence must match the quote (code check),
   - an LLM verifier checks that the sentence stays faithful to its quote.
4. **Finalize.** Rejected items are rewritten once and verified again; items
   that still fail are removed and lower the confidence level.

Prompts and design notes: [`prompts/PROMPT_NOTES.md`](prompts/PROMPT_NOTES.md).
The prompts include defences against instructions hidden in a leaflet and
reject text that is not a leaflet.

## Quick start

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env
```

In `.env`, either add a free Gemini API key from
<https://aistudio.google.com/apikey>:

```
GEMINI_API_KEY=your-key
USE_MOCK=0
```

or run without a key using a fixed sample result:

```
USE_MOCK=1
```

Then start the app:

```bash
streamlit run app.py
```

Try it with the leaflets in [`data/samples/`](data/samples/).

### Mock mode

With `USE_MOCK=1`, *Explain my medicine* always shows the same sample result
(`mock/analyze_output.json`), whatever leaflet you give it. Use it to try the
interface without a key. *My medicines* works fully in mock mode because it does
not use the model. Photo upload needs a key.

### Free quota

One explanation makes 2 to 6 model calls and usually takes under a minute.
Results are cached per leaflet, so opening the same leaflet again is free. The
free daily quota is small; record the demo in advance.

The default model is `gemini-3.6-flash`. If it fails because it is busy (503) or
out of quota (429), the same call is retried once with `gemini-3.5-flash`; the
free quota is counted per model. Both can be changed in `.env`
(`GEMINI_MODEL`, `GEMINI_YEDEK_MODEL`). On 17 October 2026, `gemini-3.8-flash`
kept single calls waiting 77 to 151 seconds under high demand, while
`gemini-3.6-flash` explained the same leaflet in 21 seconds.

## Tests and evaluation

```bash
python -m core.llm                       # checks the API key (1 model call)
python -m unittest discover -s tests     # 44 tests, no model calls
```

The evaluation script runs the full pipeline on every leaflet text in a folder
and writes `eval/results.md`: readability before and after (Flesch Reading
Ease), how many items each check removed, quote matches, and the hallucination
rate.

```bash
python -m eval.run_eval              # data/kt/txt, real model calls, needs a key
python -m eval.run_eval --onbellek   # reuse saved outputs in eval/outputs/
```

Do not run the evaluation in mock mode: every leaflet would get the same sample
cards and the numbers would be meaningless. After the first run, mark the
sampled items in `eval/sadakat_kontrol.csv` (E = faithful, H = not) and run
`python -m eval.run_eval --sadakat` to add the manual faithfulness score.

## Project structure

```
app.py                  Streamlit interface (both tabs, read aloud, print card)
config.py               model name, thresholds, file paths (reads .env)
core/
  inputs.py             PDF and photo to text
  llm.py                Gemini client
  pipeline.py           analyze(): draft, verify, finalize
  schema.py             output contract and JSON schemas
prompts/                draft, verifier and fix prompts, design notes
safety/
  sections.py           leaflet extraction, drug name, "Other medicines" section
  interactions.py       rule-based interaction check
eval/                   readability metric and evaluation script
mock/                   sample outputs for mock mode
tests/                  unit tests
data/
  samples/              six EMA leaflets for trying the app
  sources.md            where every leaflet comes from, licence
```

`data/kt/` holds all 16 evaluation leaflets. It is not in git (some come from
the UK eMC); it is shared within the team.

## Output format

`analyze(text)` never raises. On failure it returns `{"error": "..."}`; otherwise:

```json
{
  "drug_name": "PANTOZOL Control 20 mg gastro-resistant tablets",
  "cards": {
    "what_for": [{"text": "plain sentence", "evidence": "exact quote from the leaflet"}],
    "how_to_use": [],
    "see_doctor_now": [],
    "side_effects": [],
    "storage": []
  },
  "pharmacist_questions": ["..."],
  "verification": {"unsupported": [], "confidence": "high | medium | low"}
}
```

## Data and licence

Leaflets come from the European Medicines Agency (EMA, <https://www.ema.europa.eu>),
reproduced with acknowledgement as allowed by the EMA legal notice. See
[`data/sources.md`](data/sources.md) for every file, link and download date.
