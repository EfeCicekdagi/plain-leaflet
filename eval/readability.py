"""Ateşman okunabilirlik skoru (Türkçe). Başka hiçbir dosyaya bağlı değildir.

Skor = 198.825 - 40.175 * (hece / kelime) - 2.610 * (kelime / cümle)
Hece sayısı = sesli harf sayısı. Yüksek skor = daha kolay metin.
  90-100 çok kolay, 70-89 kolay, 50-69 orta, 30-49 zor, 1-29 çok zor
"""
import re

SESLI = set("aeıioöuüâîû")
KELIME = re.compile(r"[a-zçğıöşüâîû]+")
# Cümle sonu: . ! ? … veya satır başındaki madde işareti
CUMLE_SONU = re.compile(r"[.!?…]+|\n\s*[•\-–*▪●○]\s+")


def atesman(metin: str) -> float:
    try:
        metin = metin.replace("İ", "i").replace("I", "ı").lower()
        metin = re.sub(r"(\d)[.,](\d)", r"\1\2", metin)  # 2.5 gibi sayılar cümleyi bölmesin
        cumleler = [c for c in CUMLE_SONU.split("\n" + metin) if KELIME.search(c)]
        # Sesli harfi olmayan kısaltmalar (mg, ml) kelime sayılmaz
        kelimeler = [k for k in KELIME.findall(metin) if SESLI.intersection(k)]
        if not cumleler or not kelimeler:
            return 0.0
        hece = sum(1 for harf in metin if harf in SESLI)
        skor = 198.825 - 40.175 * (hece / len(kelimeler)) - 2.610 * (len(kelimeler) / len(cumleler))
        return round(min(100.0, max(0.0, skor)), 2)
    except Exception:
        return 0.0


if __name__ == "__main__":
    print(atesman("Ağrı ve ateşi azaltmak için kullanılır. Tableti su ile yutun."))
    print(atesman("Karaciğer veya böbrek yetmezliğiniz varsa, bu ilacı kullanmadan önce doktorunuza danışınız, "
                  "zira parasetamolün hepatik metabolizması bozulmuş hastalarda toksisite riski artmaktadır."))
