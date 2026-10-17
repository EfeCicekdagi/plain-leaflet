"""Ölçüm scripti: KT'ler üzerinde analyze() (ara bilgileriyle: analiz_detayli) çalıştırır ve eval/results.md tablosunu yazar.
results.md İngilizce yazılır (rapor İngilizce).

Kullanım (repo kökünden):
  python -m eval.run_eval                        # data/kt/*.txt üzerinde çalışır
  python -m eval.run_eval --klasor data/samples  # başka klasör
  python -m eval.run_eval --onbellek             # eval/outputs/ altında çıktısı olan ilaçlar için modeli tekrar çağırmaz
  python -m eval.run_eval --sadakat              # elle doldurulan eval/sadakat_kontrol.csv'den yüzdeyi hesaplar, results.md'yi günceller

Elle sadakat kontrolü: ilk çalıştırma eval/sadakat_kontrol.csv dosyasını yazar (ilaç başına 3 rastgele madde).
"sadik" sütununa E (evet) veya H (hayır) yazılır, sonra --sadakat ile tekrar çalıştırılır.
CSV virgülle ayrılmıştır; Türkçe Excel tek sütunda açarsa Google Sheets veya Numbers ile açın.
"""
import argparse
import csv
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import config  # noqa: E402
from core import schema  # noqa: E402
from core.pipeline import analiz_detayli, dil_tespit, kanit_skoru  # noqa: E402
from eval.readability import okunabilirlik  # noqa: E402

EVAL = KOK / "eval"
CIKTILAR = EVAL / "outputs"
OZET = CIKTILAR / "_ozet.json"
SADAKAT_CSV = EVAL / "sadakat_kontrol.csv"
SONUCLAR = EVAL / "results.md"
SADAKAT_ORNEK = 3  # ilaç başına elle kontrol edilecek madde


def sade_metin(sonuc: dict) -> str:
    cumleler = []
    for kart in schema.KARTLAR:
        for madde in sonuc["kartlar"][kart]:
            metin = madde["metin"].strip()
            cumleler.append(metin if metin[-1] in ".!?" else metin + ".")
    return " ".join(cumleler)


def olc(ad: str, kt_metni: str, sonuc: dict, detay: dict, sure: float) -> dict:
    dil = detay.get("dil") or dil_tespit(kt_metni)
    skor_kt, olcut = okunabilirlik(kt_metni, dil)
    satir = {"ilac": ad, "dil": dil, "olcut": olcut, "sure_sn": round(sure, 1), "okunabilirlik_kt": skor_kt}
    if "hata" in sonuc:
        satir["hata"] = sonuc["hata"]
        return satir
    maddeler = [m for kart in schema.KARTLAR for m in sonuc["kartlar"][kart]]
    kalan, cikarilan = len(maddeler), len(sonuc["dogrulama"]["desteklenmeyen"])
    satir.update({
        "ilac_adi": sonuc["ilac_adi"],
        "okunabilirlik_sade": okunabilirlik(sade_metin(sonuc), dil)[0],
        "kalan": kalan,
        "cikarilan": cikarilan,
        # Bağımsız tekrar kontrol: son çıktıdaki her kanıt KT'de gerçekten var mı?
        "kanit_dolu": sum(1 for m in maddeler if m["kanit"]),
        "kanit_kt_de": sum(1 for m in maddeler if kanit_skoru(m["kanit"], kt_metni) >= config.KANIT_ESIK),
        "soru": len(sonuc["eczaciya_sorular"]),
        "guven": sonuc["dogrulama"]["guven"],
        "kod_elenen": detay.get("kod_elenen", 0),
        "sayi_elenen": detay.get("sayi_elenen", 0),
        "llm_elenen": detay.get("llm_elenen", 0),
        "llm_ilk_ret": detay.get("llm_ilk_ret", detay.get("llm_elenen", 0)),
        "duzeltilen": detay.get("duzeltilen", 0),
        "kriter_ret": detay.get("kriter_ret", {}),
        "dogrulayici_calisti": detay.get("dogrulayici_calisti", True),
    })
    return satir


def sadakat_ornegi_yaz(sonuclar: dict[str, dict], tohum: int = 42) -> None:
    rastgele = random.Random(tohum)
    with open(SADAKAT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        yazici = csv.writer(f)
        yazici.writerow(["ilac", "kart", "metin", "kanit", "sadik"])
        for ad, sonuc in sonuclar.items():
            if "hata" in sonuc:
                continue
            maddeler = [(kart, m) for kart in schema.KARTLAR for m in sonuc["kartlar"][kart]]
            for kart, m in rastgele.sample(maddeler, min(SADAKAT_ORNEK, len(maddeler))):
                yazici.writerow([ad, kart, m["metin"], m["kanit"], ""])


def sadakat_oku() -> tuple[int, int] | None:
    """(sadık, işaretlenen) döndürür. CSV yoksa veya hiç işaretlenmemişse None."""
    if not SADAKAT_CSV.exists():
        return None
    with open(SADAKAT_CSV, encoding="utf-8-sig") as f:
        isaretler = [r["sadik"].strip().upper() for r in csv.DictReader(f)]
    isaretli = [i for i in isaretler if i in ("E", "H")]
    if not isaretli:
        return None
    return isaretli.count("E"), len(isaretli)


def yuzde(pay: float, payda: float) -> str:
    return f"{100 * pay / payda:.1f}%" if payda else "-"


def rapor_yaz(ozet: dict) -> None:
    satirlar = ozet["satirlar"]
    basarili = [s for s in satirlar if "hata" not in s]
    hatali = [s for s in satirlar if "hata" in s]
    diller = sorted({s["dil"] for s in satirlar})

    y = [
        "# Evaluation results",
        "",
        f"- Date: {ozet['tarih']}",
        f"- Model: `{ozet['model']}`, temperature {config.TEMPERATURE}",
        f"- Leaflets: {len(satirlar)} (succeeded: {len(basarili)}, failed: {len(hatali)}), languages: {', '.join(diller)}",
        f"- Quote match threshold (difflib): {config.KANIT_ESIK}",
        "",
        "Generated by `python -m eval.run_eval`. Numbers in the report come only from this file.",
        "",
        "## 1. Readability (before / after)",
        "",
        "Turkish leaflets: Ateşman score. English leaflets: Flesch Reading Ease. Both 0-100, higher = easier.",
        "90-100 very easy, 70-89 easy, 50-69 medium, 30-49 difficult, 0-29 very difficult.",
        "",
        "| Medicine | Language | Metric | Leaflet (before) | Plain cards (after) | Change |",
        "|---|---|---|---:|---:|---:|",
    ]
    for s in basarili:
        y.append(f"| {s['ilac']} | {s['dil']} | {s['olcut']} | {s['okunabilirlik_kt']:.1f} | {s['okunabilirlik_sade']:.1f} "
                 f"| {s['okunabilirlik_sade'] - s['okunabilirlik_kt']:+.1f} |")
    for olcut in sorted({s["olcut"] for s in basarili}):
        grup = [s for s in basarili if s["olcut"] == olcut]
        once = sum(s["okunabilirlik_kt"] for s in grup) / len(grup)
        sonra = sum(s["okunabilirlik_sade"] for s in grup) / len(grup)
        y.append(f"| **Average ({len(grup)} leaflet{'s' if len(grup) > 1 else ''})** | | **{olcut}** | **{once:.1f}** | **{sonra:.1f}** | **{sonra - once:+.1f}** |")

    kalan = sum(s["kalan"] for s in basarili)
    cikarilan = sum(s["cikarilan"] for s in basarili)
    y += [
        "",
        "## 2. Source grounding and the verifier",
        "",
        "Every draft item passes three checks: is the quote really in the leaflet (difflib), do the numbers match (code), "
        "does the plain sentence stay faithful to its quote (LLM verifier, 4 criteria). Items the LLM verifier rejects are "
        "rewritten once using its reason and verified again (finalize step); items that still fail are removed.",
        "",
        "- *Pass rate*: share of draft items in the final cards.",
        "- *Quote in leaflet*: final items whose quote is found in the leaflet again by an independent re-check.",
        "",
        "| Medicine | Draft items | Quote not in leaflet | Numbers differ | Rejected by LLM | Fixed and re-verified | Removed | Kept | Pass rate | Quote in leaflet | Pharmacist questions | Confidence | Time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for s in basarili:
        uyari = "" if s["dogrulayici_calisti"] else " (LLM verifier did not run)"
        y.append(
            f"| {s['ilac']}{uyari} | {s['kalan'] + s['cikarilan']} | {s['kod_elenen']} | {s['sayi_elenen']} | {s['llm_ilk_ret']} "
            f"| {s['duzeltilen']} | {s['cikarilan']} | {s['kalan']} "
            f"| {yuzde(s['kalan'], s['kalan'] + s['cikarilan'])} | {s['kanit_kt_de']}/{s['kalan']} | {s['soru']} | {s['guven']} | {s['sure_sn']} |"
        )
    toplam = {k: sum(s[k] for s in basarili)
              for k in ("kod_elenen", "sayi_elenen", "llm_ilk_ret", "duzeltilen", "kanit_kt_de", "soru")}
    if basarili:
        y.append(
            f"| **Total** | **{kalan + cikarilan}** | **{toplam['kod_elenen']}** | **{toplam['sayi_elenen']}** | **{toplam['llm_ilk_ret']}** "
            f"| **{toplam['duzeltilen']}** | **{cikarilan}** | **{kalan}** | **{yuzde(kalan, kalan + cikarilan)}** | **{toplam['kanit_kt_de']}/{kalan}** | **{toplam['soru']}** | | |"
        )

    y += [
        "",
        "Which criterion the LLM verifier failed in its first pass (one item can fail several):",
        "",
        "| Criterion | Rejections |",
        "|---|---:|",
    ]
    for kriter in schema.DOGRULAYICI_KRITERLER:
        y.append(f"| `{kriter}` | {sum(s['kriter_ret'].get(kriter, 0) for s in basarili)} |")

    sadakat = sadakat_oku()
    taslak_hata = toplam["kod_elenen"] + toplam["sayi_elenen"] + toplam["llm_ilk_ret"] if basarili else 0
    y += [
        "",
        "## 3. Hallucination rate",
        "",
        "Target: below 5% (Samsung Innovation Campus GenAI course, Chapter 4, Responsible AI metrics).",
        "",
        "| Stage | Rate |",
        "|---|---:|",
        f"| Draft, before verification: items not grounded in the leaflet or saying more than their quote | {yuzde(taslak_hata, kalan + cikarilan)} |",
        f"| Final cards, automatic checks: items removed because they could not be verified | {yuzde(cikarilan, kalan + cikarilan)} |",
        f"| Final output, manual check: items not faithful to their quote | "
        f"{yuzde(sadakat[1] - sadakat[0], sadakat[1]) if sadakat else 'manual check pending'} |",
    ]

    y += ["", "## 4. Manual faithfulness check", ""]
    if sadakat:
        y.append(f"{sadakat[1]} randomly sampled items ({SADAKAT_ORNEK} per medicine) were checked by hand: "
                 "\"Is the plain sentence faithful to its quote?\"")
        y.append("")
        y.append(f"**Faithfulness: {sadakat[0]}/{sadakat[1]} = {yuzde(*sadakat)}**")
        y.append("")
        y.append("Labels: `eval/sadakat_kontrol.csv` (E = yes, H = no)")
    else:
        y.append("Not labelled yet. Write E/H in the `sadik` column of `eval/sadakat_kontrol.csv`, "
                 "then run `python -m eval.run_eval --sadakat`.")

    if hatali:
        y += ["", "## 5. Leaflets that returned an error", "", "| Medicine | Error |", "|---|---|"]
        y += [f"| {s['ilac']} | {s['hata']} |" for s in hatali]

    with open(SONUCLAR, "w", encoding="utf-8") as f:
        f.write("\n".join(y) + "\n")


def calistir(klasor: Path, onbellek: bool, bekle: float) -> None:
    dosyalar = sorted(klasor.glob("*.txt"))
    if not dosyalar:
        sys.exit(f"{klasor} içinde .txt dosyası yok.")
    CIKTILAR.mkdir(exist_ok=True)

    satirlar, sonuclar = [], {}
    for i, dosya in enumerate(dosyalar, 1):
        ad = dosya.stem
        with open(dosya, encoding="utf-8") as f:
            kt_metni = f.read()
        cikti = CIKTILAR / f"{ad}.json"
        if onbellek and cikti.exists():
            with open(cikti, encoding="utf-8") as f:
                kayit = json.load(f)
            sonuc, detay, sure = kayit["sonuc"], kayit.get("detay", {}), kayit["sure_sn"]
        else:
            if i > 1 and bekle:
                time.sleep(bekle)  # ücretsiz kota dakikadaki istek sayısını sınırlıyor
            bas = time.time()
            sonuc, detay = analiz_detayli(kt_metni)
            sure = time.time() - bas
            with open(cikti, "w", encoding="utf-8") as f:
                json.dump({"sonuc": sonuc, "detay": detay, "sure_sn": sure}, f, ensure_ascii=False, indent=2)
        sonuclar[ad] = sonuc
        satir = olc(ad, kt_metni, sonuc, detay, sure)
        satirlar.append(satir)
        durum = f"HATA: {satir['hata']}" if "hata" in satir else f"{satir['kalan']} madde, {satir['cikarilan']} çıkarıldı, güven {satir['guven']}"
        print(f"[{i}/{len(dosyalar)}] {ad} ({satir['dil']}): {durum}")

    ozet = {"tarih": date.today().isoformat(), "model": config.MODEL_NAME, "satirlar": satirlar}
    with open(OZET, "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=2)
    yazilanlar = [SONUCLAR.relative_to(KOK)]
    if sadakat_oku() is None:
        sadakat_ornegi_yaz(sonuclar)
        yazilanlar.append(SADAKAT_CSV.relative_to(KOK))
    else:
        print(f"{SADAKAT_CSV.relative_to(KOK)} zaten işaretlenmiş, üzerine yazılmadı.")
    rapor_yaz(ozet)
    print("Yazıldı:", ", ".join(map(str, yazilanlar)))


def main() -> None:
    p = argparse.ArgumentParser(description="İlaç Rehberim ölçüm scripti")
    p.add_argument("--klasor", type=Path, default=KOK / "data" / "kt", help="KT .txt dosyalarının klasörü")
    p.add_argument("--onbellek", action="store_true", help="eval/outputs/ altındaki eski çıktıları kullan")
    p.add_argument("--bekle", type=float, default=5.0, help="ilaçlar arası bekleme (sn), kota için")
    p.add_argument("--sadakat", action="store_true", help="sadece sadakat CSV'sini okuyup results.md'yi güncelle")
    args = p.parse_args()

    if args.sadakat:
        if not OZET.exists():
            sys.exit("Önce ölçümü çalıştırın: python -m eval.run_eval")
        with open(OZET, encoding="utf-8") as f:
            rapor_yaz(json.load(f))
        print(f"Güncellendi: {SONUCLAR.relative_to(KOK)}")
        return
    calistir(args.klasor, args.onbellek, args.bekle)


if __name__ == "__main__":
    main()
