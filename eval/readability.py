"""Readability scores. Depends on no other file.

Turkish - Ateşman: Score = 198.825 - 40.175 * (syllables / words) - 2.610 * (words / sentences)
                   Syllables = number of vowels.
English - Flesch:  Score = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
                   Syllables = vowel groups (a silent final "e" is dropped), at least 1 per word.
For both, a higher score = easier text, from 0 to 100.
  90-100 very easy, 70-89 easy, 50-69 medium, 30-49 difficult, 0-29 very difficult
"""
import re

SESLI = set("aeıioöuüâîû")
KELIME = re.compile(r"[a-zçğıöşüâîû]+")
# Sentence end: . ! ? … or a bullet at the start of a line
CUMLE_SONU = re.compile(r"[.!?…]+|\n\s*[•\-–*▪●○]\s+")


def _hazirla(metin: str) -> tuple[str, list[str], list[str]]:
    """(lower-case text, words, sentences)"""
    metin = metin.replace("İ", "i").replace("I", "ı").lower()
    metin = re.sub(r"(\d)[.,](\d)", r"\1\2", metin)  # numbers such as 2.5 must not split a sentence
    cumleler = [c for c in CUMLE_SONU.split("\n" + metin) if KELIME.search(c)]
    # Abbreviations without vowels (mg, ml) are not counted as words
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
    kelime = kelime.replace("ı", "i")  # the ı comes from the Turkish lower-casing above
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
    """(score, metric name). Ateşman for Turkish, Flesch Reading Ease for English."""
    return (atesman(metin), "Ateşman") if dil == "tr" else (flesch(metin), "Flesch")


if __name__ == "__main__":
    print(atesman("Ağrı ve ateşi azaltmak için kullanılır. Tableti su ile yutun."))
    print(atesman("Karaciğer veya böbrek yetmezliğiniz varsa, bu ilacı kullanmadan önce doktorunuza danışınız, "
                  "zira parasetamolün hepatik metabolizması bozulmuş hastalarda toksisite riski artmaktadır."))
    print(flesch("Swallow the tablet with water. Store it below 25 degrees."))
    print(flesch("Concomitant administration with hepatic enzyme-inducing anticonvulsant medications "
                 "may potentiate hepatotoxicity, particularly in patients with pre-existing hepatic impairment."))
