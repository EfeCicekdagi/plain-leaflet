# Leaflet sources

All leaflets were downloaded by hand from the European Medicines Agency (EMA).
Each file is the "EPAR – Product Information" PDF; only the part after the
"B. PACKAGE LEAFLET" heading is used (`safety/sections.py: extract_leaflet()`).

The full PDFs and text files are shared with the team and kept out of the repo
(`data/kt/`, ignored by git). Only 1–2 sample texts go into `data/samples/`.

| File | Medicine | Active substance | Type | Source | Downloaded | Link |
|---|---|---|---|---|---|---|
| `Clopidogrel_Zentiva.pdf` | Clopidogrel Zentiva 75 mg film-coated tablets | clopidogrel | Antiplatelet | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/clopidogrel-zentiva-epar-product-information_en.pdf |
| `DuoPlavin.pdf` | DuoPlavin 75 mg/75 mg, 75 mg/100 mg film-coated tablets | clopidogrel, acetylsalicylic acid | Antiplatelet + aspirin | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/duoplavin-epar-product-information_en.pdf |
| `Ibuprofen_Gen_Orph.pdf` | Ibuprofen Gen.Orph 5 mg/mL solution for injection | ibuprofen | Painkiller (NSAID) | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/ibuprofen-genorph-epar-product-information_en.pdf |
| `Onpattro.pdf` | Onpattro 2 mg/mL concentrate for solution for infusion | patisiran | hATTR amyloidosis | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/onpattro-epar-product-information_en.pdf |
| `Rasilez.pdf` | Rasilez 150 mg, 300 mg film-coated tablets | aliskiren | Blood pressure | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/rasilez-epar-product-information_en.pdf |
| `Svariya.pdf` | Svariya 10 mg orodispersible film | rivaroxaban | Blood thinner | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/svariya-epar-product-information_en.pdf |
| `Synjardy.pdf` | Synjardy film-coated tablets | empagliflozin, metformin | Diabetes | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/synjardy-epar-product-information_en.pdf |
| `Xarelto.pdf` | Xarelto film-coated tablets | rivaroxaban | Blood thinner | EMA | 2026-10-17 | https://www.ema.europa.eu/en/documents/product-information/xarelto-epar-product-information_en.pdf |

## Demo pair

**Xarelto (rivaroxaban) + Clopidogrel Zentiva (clopidogrel).** The "Other
medicines and Xarelto" section lists "other medicines to reduce blood clotting
(e.g. enoxaparin, clopidogrel or vitamin K antagonists such as warfarin and
acenocoumarol)". Svariya has the same sentence.

## Notes

- Xarelto's PDF contains several leaflets (one per strength), so its leaflet
  text is much longer (~144k characters) than the others (15–43k).
- Rasilez and DuoPlavin name a drug class ("non-steroidal anti-inflammatory
  medicines (NSAIDs)") instead of ibuprofen. A plain name search misses these
  (known limit, see `safety/interactions.py`).
