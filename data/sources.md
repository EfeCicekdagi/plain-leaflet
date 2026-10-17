# Leaflet sources

All leaflets were downloaded by hand. EMA files are the "EPAR – Product
Information" PDF; only the part after the "B. PACKAGE LEAFLET" heading is used
(`safety/sections.py: extract_leaflet()`). Medicines not authorised centrally
in the EU come from the UK eMC (medicines.org.uk) Patient Information Leaflet,
which contains the leaflet only.

## Where the files are

- `data/kt/` (ignored by git): all 16 PDFs and their leaflet text in
  `data/kt/txt/`. Shared with the team for evaluation, not committed.
- `data/samples/` (in the repo): six EMA PDFs for trying the app by hand, and
  one leaflet text for pasting into the "Explain my medicine" tab.

## Licence

Source: European Medicines Agency (EMA), https://www.ema.europa.eu.
EMA documents "are public and may be reproduced and / or distributed" provided
EMA is acknowledged as the source (EMA legal notice,
https://www.ema.europa.eu/en/about-us/legal-notice). Only EMA files are
committed to the repo; eMC leaflets stay in `data/kt/`.

## Leaflets

| File | Medicine | Active substance | Type | Source | Downloaded | Link |
|---|---|---|---|---|---|---|
| `Alendronic_Acid.pdf` | Alendronic Acid 70 mg tablets | alendronic acid | Osteoporosis | eMC | 2026-10-17 | https://www.medicines.org.uk/emc/files/pil.5206.pdf |
| `Apozyl.pdf` | APOZYL 5 mg, 10 mg orodispersible tablets | donepezil hydrochloride | Alzheimer's disease | eMC | 2026-10-17 | https://www.medicines.org.uk/emc/files/pil.15539.pdf |
| `Clopidogrel_Zentiva.pdf` | Clopidogrel Zentiva 75 mg film-coated tablets | clopidogrel | Antiplatelet | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/clopidogrel-zentiva-epar-product-information_en.pdf |
| `DuoPlavin.pdf` | DuoPlavin 75 mg/75 mg, 75 mg/100 mg film-coated tablets | clopidogrel, acetylsalicylic acid | Antiplatelet + aspirin | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/duoplavin-epar-product-information_en.pdf |
| `Entresto.pdf` | Entresto film-coated tablets | sacubitril, valsartan | Heart failure | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/entresto-epar-product-information_en.pdf |
| `Glyxambi.pdf` | Glyxambi 10 mg/5 mg, 25 mg/5 mg film-coated tablets | empagliflozin, linagliptin | Diabetes | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/glyxambi-epar-product-information_en.pdf |
| `Ibuprofen_Gen_Orph.pdf` | Ibuprofen Gen.Orph 5 mg/mL solution for injection | ibuprofen | Painkiller (NSAID) | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/ibuprofen-genorph-epar-product-information_en.pdf |
| `Nexium_Control.pdf` | Nexium Control 20 mg gastro-resistant tablets | esomeprazole | Stomach acid | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/nexium-control-epar-product-information_en.pdf |
| `Nilemdo.pdf` | Nilemdo 180 mg film-coated tablets | bempedoic acid | Cholesterol | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/nilemdo-epar-product-information_en.pdf |
| `Onpattro.pdf` | Onpattro 2 mg/mL concentrate for solution for infusion | patisiran | hATTR amyloidosis | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/onpattro-epar-product-information_en.pdf |
| `Pantozol_Control.pdf` | PANTOZOL Control 20 mg gastro-resistant tablets | pantoprazole | Stomach acid | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/pantozol-control-epar-product-information_en.pdf |
| `Rasilez.pdf` | Rasilez 150 mg, 300 mg film-coated tablets | aliskiren | Blood pressure | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/rasilez-epar-product-information_en.pdf |
| `Svariya.pdf` | Svariya 10 mg orodispersible film | rivaroxaban | Blood thinner | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/svariya-epar-product-information_en.pdf |
| `Synjardy.pdf` | Synjardy film-coated tablets | empagliflozin, metformin | Diabetes | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/synjardy-epar-product-information_en.pdf |
| `Xarelto.pdf` | Xarelto film-coated tablets | rivaroxaban | Blood thinner | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/xarelto-epar-product-information_en.pdf |
| `Xenleta.pdf` | Xenleta 600 mg film-coated tablets | lefamulin | Antibiotic | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/xenleta-epar-product-information_en.pdf |

In `data/samples/`: `Clopidogrel_Zentiva.pdf`, `Nexium_Control.pdf`,
`Nilemdo.pdf`, `Pantozol_Control.pdf`, `Xarelto.pdf`, `Xenleta.pdf` and
`Clopidogrel_Zentiva.txt`.

## Demo

**Main pair: Xarelto (rivaroxaban) + Clopidogrel Zentiva (clopidogrel).** Warns
in both directions. The "Other medicines and Xarelto" section lists "other
medicines to reduce blood clotting (e.g. enoxaparin, clopidogrel ...)", and
the Clopidogrel Zentiva leaflet lists "oral anticoagulants" (found through the
drug class dictionary). Svariya behaves like Xarelto.

**Three medicines: Xarelto + Clopidogrel Zentiva + Nexium Control.** Gives four
warnings: the two above, plus Clopidogrel Zentiva naming esomeprazole and
Nexium Control naming clopidogrel. All three PDFs are in `data/samples/`.

Backup pair: **Entresto (sacubitril/valsartan) + Rasilez (aliskiren).** Entresto
names aliskiren; Rasilez names "an angiotensin II receptor blocker", the class
of valsartan.

## Notes

- Xarelto's PDF contains several leaflets (one per strength), so its leaflet
  text is much longer (~144k characters) than the others (12–43k).
- Several leaflets name a drug class ("NSAIDs", "oral anticoagulants") instead
  of a substance. `DRUG_CLASSES` in `safety/interactions.py` maps six common
  classes to their substances; a class that is not in that list is still
  missed (known limit).
