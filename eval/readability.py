"""Okunabilirlik skorları. Başka hiçbir dosyaya bağlı değildir.

Türkçe - Ateşman:   Skor = 198.825 - 40.175 * (hece / kelime) - 2.610 * (kelime / cümle)
                    Hece sayısı = sesli harf sayısı.
İngilizce - Flesch: Skor = 206.835 - 1.015 * (kelime / cümle) - 84.6 * (hece / kelime)
                    Hece sayısı = sesli harf grupları (sondaki sessiz "e" düşülür), kelime başına en az 1.
İkisinde de yüksek skor = daha kolay metin, 0-100 arası.
  90-100 çok kolay, 70-89 kolay, 50-69 orta, 30-49 zor, 0-29 çok zor
"""
import re

SESLI = set("aeıioöuüâîû")
KELIME = re.compile(r"[a-zçğıöşüâîû]+")
# Cümle sonu: . ! ? … veya satır başındaki madde işareti
CUMLE_SONU = re.compile(r"[.!?…]+|\n\s*[•\-–*▪●○]\s+")


def _hazirla(metin: str) -> tuple[str, list[str], list[str]]:
    """(küçük harfli metin, kelimeler, cümleler)"""
    metin = metin.replace("İ", "i").replace("I", "ı").lower()
    metin = re.sub(r"(\d)[.,](\d)", r"\1\2", metin)  # 2.5 gibi sayılar cümleyi bölmesin
    cumleler = [c for c in CUMLE_SONU.split("\n" + metin) if KELIME.search(c)]
    # Sesli harfi olmayan kısaltmalar (mg, ml) kelime sayılmaz
    kelimeler = [k for k in KELIME.findall(metin) if SESLI.intersection(k)]
    return metin, kelimeler, cumleler


def atesman(metin: str) -> float:
    try:
        metin, kelimeler, cumleler = _hazirla(metin)
        if not cumleler or not kelimeler:
            return 0.0
        hece = sum(1 for harf in metin if harf in SESLI)
        skor = 198.825 - 40.175 * (hece / len(kelimeler)) - 2.610 * (len(kelimeler) / len(cumleler))
        return round(min(100.0, max(0.0, skor)), 2)
    except Exception:
        return 0.0


def _ingilizce_hece(kelime: str) -> int:
    kelime = kelime.replace("ı", "i")  # Türkçe küçük harf dönüşümünden gelen ı
    gruplar = len(re.findall(r"[aeiouy]+", kelime))
    if kelime.endswith("e") and not kelime.endswith(("le", "ee")) and gruplar > 1:
        gruplar -= 1
    return max(1, gruplar)


def flesch(metin: str) -> float:
    try:
        _, kelimeler, cumleler = _hazirla(metin)
        if not cumleler or not kelimeler:
            return 0.0
        hece = sum(_ingilizce_hece(k) for k in kelimeler)
        skor = 206.835 - 1.015 * (len(kelimeler) / len(cumleler)) - 84.6 * (hece / len(kelimeler))
        return round(min(100.0, max(0.0, skor)), 2)
    except Exception:
        return 0.0


def okunabilirlik(metin: str, dil: str) -> tuple[float, str]:
    """(skor, ölçüt adı). Türkçe için Ateşman, İngilizce için Flesch Reading Ease."""
    return (atesman(metin), "Ateşman") if dil == "tr" else (flesch(metin), "Flesch")


if __name__ == "__main__":
    print(atesman("Ağrı ve ateşi azaltmak için kullanılır. Tableti su ile yutun."))
    print(atesman("Karaciğer veya böbrek yetmezliğiniz varsa, bu ilacı kullanmadan önce doktorunuza danışınız, "
                  "zira parasetamolün hepatik metabolizması bozulmuş hastalarda toksisite riski artmaktadır."))
    print(flesch("Swallow the tablet with water. Store it below 25 degrees."))
    print(flesch("Concomitant administration with hepatic enzyme-inducing anticonvulsant medications "
                 "may potentiate hepatotoxicity, particularly in patients with pre-existing hepatic impairment."))
