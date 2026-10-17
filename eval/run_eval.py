"""Ölçüm scripti: KT'ler üzerinde analyze() çalıştırır ve eval/results.md tablosunu yazar.

Kullanım (repo kökünden):
  python -m eval.run_eval                        # data/kt/*.txt üzerinde çalışır
  python -m eval.run_eval --klasor data/samples  # başka klasör
  python -m eval.run_eval --onbellek             # eval/outputs/ altında çıktısı olan ilaçlar için modeli tekrar çağırmaz
  python -m eval.run_eval --sadakat              # elle doldurulan eval/sadakat_kontrol.csv'den yüzdeyi hesaplar, results.md'yi günceller

Elle sadakat kontrolü: ilk çalıştırma eval/sadakat_kontrol.csv dosyasını yazar (ilaç başına 3 rastgele madde).
"sadik" sütununa E (evet) veya H (hayır) yazılır, sonra --sadakat ile tekrar çalıştırılır.
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
from core.pipeline import analyze, kanit_skoru  # noqa: E402
from eval.readability import atesman  # noqa: E402

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


def olc(ad: str, kt_metni: str, sonuc: dict, sure: float) -> dict:
    satir = {"ilac": ad, "sure_sn": round(sure, 1), "atesman_kt": atesman(kt_metni)}
    if "hata" in sonuc:
        satir["hata"] = sonuc["hata"]
        return satir
    maddeler = [m for kart in schema.KARTLAR for m in sonuc["kartlar"][kart]]
    kalan, cikarilan = len(maddeler), len(sonuc["dogrulama"]["desteklenmeyen"])
    satir.update({
        "ilac_adi": sonuc["ilac_adi"],
        "atesman_sade": atesman(sade_metin(sonuc)),
        "kalan": kalan,
        "cikarilan": cikarilan,
        "gecen_oran": kalan / (kalan + cikarilan) if kalan + cikarilan else 0.0,
        # Bağımsız tekrar kontrol: son çıktıdaki her kanıt KT'de gerçekten var mı?
        "kanit_dolu": sum(1 for m in maddeler if m["kanit"]),
        "kanit_kt_de": sum(1 for m in maddeler if kanit_skoru(m["kanit"], kt_metni) >= config.KANIT_ESIK),
        "soru": len(sonuc["eczaciya_sorular"]),
        "guven": sonuc["dogrulama"]["guven"],
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
    return f"%{100 * pay / payda:.1f}" if payda else "-"


def rapor_yaz(ozet: dict) -> None:
    satirlar = ozet["satirlar"]
    basarili = [s for s in satirlar if "hata" not in s]
    hatali = [s for s in satirlar if "hata" in s]

    y = [
        "# Değerlendirme sonuçları",
        "",
        f"- Tarih: {ozet['tarih']}",
        f"- Model: `{ozet['model']}`, sıcaklık {config.TEMPERATURE}",
        f"- KT sayısı: {len(satirlar)} (hatasız: {len(basarili)}, hatalı: {len(hatali)})",
        f"- Kanıt eşiği (difflib): {config.KANIT_ESIK}",
        "",
        "Bu dosya `python -m eval.run_eval` ile üretilir. Rapordaki rakamlar sadece buradan alınır.",
        "",
        "## 1. Okunabilirlik (Ateşman, önce / sonra)",
        "",
        "Yüksek skor = daha kolay metin. 90-100 çok kolay, 70-89 kolay, 50-69 orta, 30-49 zor, 1-29 çok zor.",
        "",
        "| İlaç | KT (önce) | Sade kartlar (sonra) | Fark |",
        "|---|---:|---:|---:|",
    ]
    for s in basarili:
        y.append(f"| {s['ilac']} | {s['atesman_kt']:.1f} | {s['atesman_sade']:.1f} | {s['atesman_sade'] - s['atesman_kt']:+.1f} |")
    if basarili:
        once = sum(s["atesman_kt"] for s in basarili) / len(basarili)
        sonra = sum(s["atesman_sade"] for s in basarili) / len(basarili)
        y.append(f"| **Ortalama** | **{once:.1f}** | **{sonra:.1f}** | **{sonra - once:+.1f}** |")

    kalan = sum(s["kalan"] for s in basarili)
    cikarilan = sum(s["cikarilan"] for s in basarili)
    y += [
        "",
        "## 2. Kaynağa bağlılık ve doğrulayıcı",
        "",
        "- *Geçen oran*: modelin ürettiği maddelerden doğrulayıcının iki kontrolünü (kanıt KT'de var mı + sade cümle alıntıya sadık mı) geçenlerin oranı.",
        "- *Kanıtı KT'de*: son çıktıdaki maddelerden kanıtı KT metninde bağımsız olarak tekrar bulunanlar.",
        "",
        "| İlaç | Kalan madde | Çıkarılan | Geçen oran | Kanıtı dolu | Kanıtı KT'de | Eczacı sorusu | Güven | Süre (sn) |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for s in basarili:
        y.append(
            f"| {s['ilac']} | {s['kalan']} | {s['cikarilan']} | {yuzde(s['kalan'], s['kalan'] + s['cikarilan'])} "
            f"| {s['kanit_dolu']}/{s['kalan']} | {s['kanit_kt_de']}/{s['kalan']} | {s['soru']} | {s['guven']} | {s['sure_sn']} |"
        )
    if basarili:
        y.append(
            f"| **Toplam** | **{kalan}** | **{cikarilan}** | **{yuzde(kalan, kalan + cikarilan)}** "
            f"| **{sum(s['kanit_dolu'] for s in basarili)}/{kalan}** | **{sum(s['kanit_kt_de'] for s in basarili)}/{kalan}** "
            f"| **{sum(s['soru'] for s in basarili)}** | | |"
        )

    y += ["", "## 3. Elle sadakat kontrolü", ""]
    sadakat = sadakat_oku()
    if sadakat:
        y.append(f"Rastgele seçilen {sadakat[1]} madde (ilaç başına {SADAKAT_ORNEK}) \"sade cümle alıntıya sadık mı?\" diye elle işaretlendi.")
        y.append("")
        y.append(f"**Sadakat: {sadakat[0]}/{sadakat[1]} = {yuzde(*sadakat)}**")
        y.append("")
        y.append("İşaretlemeler: `eval/sadakat_kontrol.csv`")
    else:
        y.append("Henüz işaretlenmedi. `eval/sadakat_kontrol.csv` dosyasının `sadik` sütununa E/H yazıp `python -m eval.run_eval --sadakat` çalıştırın.")

    if hatali:
        y += ["", "## 4. Hata veren KT'ler", "", "| İlaç | Hata |", "|---|---|"]
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
            sonuc, sure = kayit["sonuc"], kayit["sure_sn"]
        else:
            if i > 1 and bekle:
                time.sleep(bekle)  # ücretsiz kota dakikadaki istek sayısını sınırlıyor
            bas = time.time()
            sonuc = analyze(kt_metni)
            sure = time.time() - bas
            with open(cikti, "w", encoding="utf-8") as f:
                json.dump({"sonuc": sonuc, "sure_sn": sure}, f, ensure_ascii=False, indent=2)
        sonuclar[ad] = sonuc
        satir = olc(ad, kt_metni, sonuc, sure)
        satirlar.append(satir)
        durum = f"HATA: {satir['hata']}" if "hata" in satir else f"{satir['kalan']} madde, {satir['cikarilan']} çıkarıldı, güven {satir['guven']}"
        print(f"[{i}/{len(dosyalar)}] {ad}: {durum}")

    ozet = {"tarih": date.today().isoformat(), "model": config.MODEL_NAME, "satirlar": satirlar}
    with open(OZET, "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=2)
    if sadakat_oku() is None:
        sadakat_ornegi_yaz(sonuclar)
    else:
        print(f"{SADAKAT_CSV.relative_to(KOK)} zaten işaretlenmiş, üzerine yazılmadı.")
    rapor_yaz(ozet)
    print(f"Yazıldı: {SONUCLAR.relative_to(KOK)}, {SADAKAT_CSV.relative_to(KOK)}")


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
