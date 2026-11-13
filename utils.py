"""
utils.py - Pomocné normalizační funkce pro text a křížovky

Tento modul neobsahuje žádné externí závislosti a využívá pouze vestavěné
knihovny Pythonu (unicodedata, re).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def remove_diacritics(text: str) -> str:
    """
    Spolehlivě odstraní českou a obecnou diakritiku z textu.
    Převede např. 'PŘÁTELSTVÍ' -> 'PRATELSTVI', 'ČINNOST' -> 'CINNOST'.
    """
    if not text:
        return ""
    # Dekompozice znaků a odstranění kombinujících diakritických značek
    nfkd_form = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in nfkd_form if not unicodedata.combining(c))
    # Náhrada dalších specifických znaků
    replacements = {
        "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ß": "ss"
    }
    for orig, rep in replacements.items():
        without_accents = without_accents.replace(orig, rep)
    return without_accents


def normalize_answer(raw_answer: str) -> Optional[str]:
    """
    Zvaliduje a normalizuje křížovkovou odpověď:
    - Odstraní diakritiku
    - Převede na velká písmena
    - Odstraní mezery, pomlčky a neabecední znaky
    - Zkontroluje délku (3 až 12 písmen)
    Vrací normalizované slovo nebo None, pokud je slovo neplatné.
    """
    if not raw_answer:
        return None

    # Odstranění uvozovek a okrajových mezer
    cleaned = raw_answer.strip().strip("\"'.,;:!?-")
    # Pokud obsahuje mezeru, vezmeme pouze první slovo
    if " " in cleaned:
        cleaned = cleaned.split()[0]

    # Odstranění diakritiky a převod na velká písmena
    no_accents = remove_diacritics(cleaned).upper()
    # Ponechat pouze písmena A-Z
    letters_only = re.sub(r"[^A-Z]", "", no_accents)

    # Validace délky (3–12 písmen)
    if 3 <= len(letters_only) <= 12:
        return letters_only

    return None


def clean_clue(raw_clue: str) -> str:
    """Očistí text nápovědy/otázky od nadbytečných mezer a uvozovek."""
    clue = raw_clue.strip().strip("\"'")
    if clue and not clue.endswith((".", "?", "!")):
        clue += "."
    return clue
