"""
extractor.py - Extrakce křížovkových pojmů a nápověd pomocí Google Gemini 2.5 Flash

Tento modul načítá texty z crawleru (či webu), odesílá je na Gemini API
s Pydantic schématem vymáhajícím striktní formát (jednoslovná odpověď, bez diakritiky, velká písmena),
odstraňuje duplicity, normalizuje text a ukládá výsledek do pionyr_otazky.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from utils import clean_clue, normalize_answer, remove_diacritics

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback pokud pydantic ještě není nainstalován v systémovém Pythonu
    class BaseModel:
        pass
    def Field(*args, **kwargs):
        return None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PionyrExtractor")


# ---------------------------------------------------------------------------
# Pydantic schémata pro vynucení striktního JSON výstupu z Gemini API
# ---------------------------------------------------------------------------

class CrosswordItem(BaseModel):
    """Jeden záznam pro křížovku: jednoslovná odpověď a nápověda/otázka."""
    answer: str = Field(
        description="Jednoslovná odpověď, 3–12 písmen, VELKÁ PÍSMENA, ZCELA BEZ DIAKRITIKY (např. TABOR, ODDIL, PRIRODA, ZNAK)."
    )
    clue: str = Field(
        description="Výstižná a přesná otázka či nápověda pro luštitele v češtině, vztahující se k textu a organizaci Pionýr."
    )


class CrosswordQuestionsList(BaseModel):
    """Seznam křížovkových dvojic."""
    items: List[CrosswordItem] = Field(
        description="Seznam vygenerovaných křížovkových otázek a jednoslovných odpovědí."
    )


class RemovedItem(BaseModel):
    """Odstraněný záznam z čistění slovníku – s důvodem."""
    answer: str = Field(description="Odpověď (slovo) odstraněné položky.")
    clue: str = Field(description="Nápověda odstraněné položky.")
    reason: str = Field(description="Krátké vysvětlení v češtině, proč byla položka odstraněna (duplicita, podobný výraz, apod.).")


class VocabCleanupResult(BaseModel):
    """Výsledek čistění slovníku přes Gemini – zachované a odstraněné položky."""
    kept: List[CrosswordItem] = Field(description="Zachované unikátní a kvalitní položky slovníku.")
    removed: List[RemovedItem] = Field(description="Odstraněné duplicitní nebo příliš podobné položky.")


try:
    CrosswordItem.model_rebuild()
    CrosswordQuestionsList.model_rebuild()
    RemovedItem.model_rebuild()
    VocabCleanupResult.model_rebuild()
except Exception:
    pass


# Normalizační funkce (remove_diacritics, normalize_answer, clean_clue) jsou importovány z utils.py


# ---------------------------------------------------------------------------
# Třída GeminiExtractor
# ---------------------------------------------------------------------------

class GeminiExtractor:
    """
    Extraktor křížovkových pojmů využívající Google Gemini 2.5 Flash
    přes oficiální balíček google-genai s Pydantic schématem.
    """

    MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    FALLBACK_MODELS = [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
    ]

    def __init__(self, api_key: Optional[str] = None):
        # 1. Zkusíme předaný klíč, 2. z proměnné prostředí
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = None

        if self.api_key:
            self._init_client()
        else:
            logger.warning(
                "Není nastaven GEMINI_API_KEY. Extrakce přes Gemini API bude vyžadovat zadání klíče."
            )

    def _init_client(self):
        """Inicializuje klienta google-genai."""
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Klient Gemini API byl úspěšně inicializován s modelem {self.MODEL_NAME}.")
        except ImportError:
            logger.error(
                "Balíček 'google-genai' není nainstalován. Nainstalujte jej pomocí: pip install google-genai"
            )
            self.client = None
        except Exception as e:
            logger.error(f"Chyba při inicializaci klienta Gemini: {e}")
            self.client = None

    def set_api_key(self, api_key: str):
        """Aktualizuje API klíč a znovu inicializuje klienta."""
        self.api_key = api_key
        self._init_client()

    def extract_from_text(self, text: str) -> List[Dict[str, str]]:
        """
        Odešle text na Gemini API s Pydantic schématem a vrátí seznam normalizovaných položek.
        """
        if not self.client:
            raise RuntimeError(
                "Gemini API klient není inicializován. Zkontrolujte prosím nastavení GEMINI_API_KEY."
            )

        if not text or len(text.strip()) < 100:
            logger.warning("Příliš krátký text pro extrakci křížovkových pojmů.")
            return []

        prompt = f"""
Jsi zkušený český tvůrce křížovek. Tvým úkolem je na základě níže uvedeného textu o dětské a mládežnické organizaci Pionýr
vytvořit co nejvíce kvalitních, zajímavých a rozmanitých křížovkových otázek a jednoslovných odpovědí.

PŘÍSNÁ PRAVIDLA PRO ODPOVĚĎ (answer):
1. POUZE JEDNO SLOVO (podstatné jméno v 1. pádě jednotného čísla, případně významný název, ideál nebo pojem).
2. Délka slova MUSÍ být mezi 3 až 12 písmeny.
3. Odpověď MUSÍ být napsána VELKÝMI PÍSMENY a ZCELA BEZ DIAKRITIKY (žádné háčky ani čárky, např. TABOR, ODDIL, OBRANICE, ZNAK, VLADAR, PRIRODA, PRAVDA, POMOC, POZNANI, PAMET, PREKONANI, PRATELSTVI, SEDMIKVITEK, KLUBOVNA, VLASTOVKA).
4. Žádné mezery, číslice ani interpunkce v odpovědi.

PRAVIDLA PRO OTÁZKU/NÁPOVĚDU (clue):
1. Výstižná, přesná a přirozená otázka v češtině (např. "Jeden ze sedmi pionýrských ideálů spojený s ochranou lesů a zvířat" pro PRIRODA, nebo "Výroční ocenění Pionýra: Křišťálová..." pro VLASTOVKA).
2. Nápověda nesmí přímo obsahovat samotné hledané slovo.

TEXT O PIONÝRU K ANALÝZE:
{text}
"""

        from google.genai import types

        response = None
        models_to_try = [self.MODEL_NAME] + [m for m in self.FALLBACK_MODELS if m != self.MODEL_NAME]

        for model_candidate in models_to_try:
            try:
                logger.info(f"Odesílám dotaz na Gemini API ({model_candidate})...")
                response = self.client.models.generate_content(
                    model=model_candidate,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CrosswordQuestionsList,
                        temperature=0.3,
                    )
                )
                if response and response.text:
                    self.MODEL_NAME = model_candidate
                    break
            except Exception as e:
                logger.warning(f"Model {model_candidate} selhal: {e}. Zkouším další...")
                import time
                time.sleep(1.5)

        try:
            if not response or not response.text:
                logger.warning("Gemini API vrátilo prázdnou odpověď.")
                return []

            # Parsování JSONu
            data = json.loads(response.text)
            raw_items = data.get("items", [])

            valid_items: List[Dict[str, str]] = []
            for item in raw_items:
                raw_ans = item.get("answer", "")
                raw_clue = item.get("clue", "")

                norm_ans = normalize_answer(raw_ans)
                if norm_ans and raw_clue:
                    valid_items.append({
                        "answer": norm_ans,
                        "clue": clean_clue(raw_clue)
                    })

            logger.info(f"Z textu bylo úspěšně extrahováno {len(valid_items)} platných křížovkových položek.")
            return valid_items

        except Exception as e:
            logger.error(f"Chyba při volání Gemini API: {e}")
            raise

    def process_crawled_data(
        self,
        pages: List[Dict[str, str]],
        chunk_size: int = 4000
    ) -> List[Dict[str, str]]:
        """
        Zpracuje seznam stažených stránek z crawleru, rozdělí text do dávek
        a extrahuje křížovková slova.
        """
        if not pages:
            logger.warning("Žádné stránky k dispozici pro extrakci.")
            return []

        # Spojení a příprava textu
        combined_text_chunks: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for page in pages:
            title = page.get("title", "")
            text = page.get("text", "")
            block = f"--- {title} ---\n{text}\n"

            if current_len + len(block) > chunk_size and current_chunk:
                combined_text_chunks.append("\n".join(current_chunk))
                current_chunk = [block]
                current_len = len(block)
            else:
                current_chunk.append(block)
                current_len += len(block)

        if current_chunk:
            combined_text_chunks.append("\n".join(current_chunk))

        all_items: List[Dict[str, str]] = []

        logger.info(f"Text rozdělen do {len(combined_text_chunks)} dávek pro Gemini API.")
        for idx, chunk in enumerate(combined_text_chunks):
            logger.info(f"Zpracovávám dávku {idx + 1}/{len(combined_text_chunks)} ({len(chunk)} znaků)...")
            try:
                items = self.extract_from_text(chunk)
                all_items.extend(items)
            except Exception as e:
                logger.error(f"Přeskakuji dávku {idx + 1} kvůli chybě: {e}")

        # Deduplikace
        deduped = deduplicate_items(all_items)
        logger.info(f"Celkem po deduplikaci získáno {len(deduped)} unikátních křížovkových slov.")
        return deduped

    def extract_from_url(self, url: str) -> List[Dict[str, str]]:
        """
        Stáhne obsah jedné konkrétní URL adresy, vyčistí HTML a pomocí Gemini
        extrahuje křížovkové dvojice otázka/odpověď.
        """
        import requests
        from bs4 import BeautifulSoup
        from crawler import PionyrCrawler

        logger.info(f"Stahuji zadanou URL: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (PionyrCrosswordBot/1.0)",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        crawler = PionyrCrawler()
        title, clean_text = crawler.clean_html_content(resp.text)

        # Ošetření specifických tabulek (skupiny, oddíly, základny atd.)
        soup = BeautifulSoup(resp.text, "html.parser")
        table_rows = []
        for tr in soup.find_all("tr", class_="colorizeTr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                name = tds[0].get_text(strip=True)
                addr = tds[1].get_text(strip=True)
                table_rows.append(f"{name} ({addr})")

        if table_rows:
            clean_text += "\n\nSeznam položek z tabulky:\n" + "\n".join(table_rows[:70])

        if len(clean_text) < 60:
            raise ValueError("Ze zadané stránky se nepodařilo získat dostatek smysluplného textu.")

        pages = [{"url": url, "title": title or "Zadaná stránka", "text": clean_text}]
        return self.process_crawled_data(pages)


def deduplicate_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Deduplikuje položky podle odpovědi. Pokud se stejné slovo vyskytne vícekrát,
    ponechá položku s delší (obvykle podrobnější a kvalitnější) nápovědou.
    """
    words_map: Dict[str, Dict[str, str]] = {}

    for item in items:
        ans = item.get("answer", "").strip().upper()
        clue = item.get("clue", "").strip()

        if not ans or not clue:
            continue

        if ans not in words_map:
            words_map[ans] = item
        else:
            # Ponecháme delší / lepší nápovědu
            if len(clue) > len(words_map[ans].get("clue", "")):
                words_map[ans] = item

    # Seřadíme podle abecedy
    sorted_items = sorted(words_map.values(), key=lambda x: x["answer"])
    return sorted_items


def cleanup_vocabulary_via_gemini(
    items: List[Dict[str, str]],
    extractor: "GeminiExtractor",
    filepath: str = "pionyr_otazky.json",
) -> tuple:
    """
    Odešle celý slovník na Gemini API, které identifikuje a odstraní duplicitní
    nebo výrazně podobné výrazy. Vrátí dvojici (zachované, odstraněné).

    Args:
        items: Aktuální seznam položek slovníku.
        extractor: Inicializovaný GeminiExtractor s platným API klíčem.
        filepath: Cesta k souboru, do kterého se uloží očistěný slovník.

    Returns:
        Tuple (kept: List[Dict], removed: List[Dict]) kde každý removed dict
        má klíče 'answer', 'clue', 'reason'.
    """
    if not extractor.client:
        raise RuntimeError("Gemini API klient není inicializován – zkontrolujte API klíč.")

    if not items:
        return [], []

    # Vytvoříme stručný seznam pro prompt (číslo + slovo + nápověda)
    vocab_lines = []
    for idx, it in enumerate(items, start=1):
        vocab_lines.append(f"{idx}. [{it['answer']}] – {it['clue']}")
    vocab_text = "\n".join(vocab_lines)

    prompt = f"""Jsi asistent pro správu databáze křížovkových otázek v češtině pro organizaci Pionýr.
Dostaneš číslovaný seznam křížovkových položek ve formátu: ČÍSLO. [ODPOVĚĎ] – nápověda.

Tvým úkolem je:
1. Identifikovat DUPLICITNÍ nebo VELMI PODOBNÉ výrazy (slova se stejným nebo překrývajícím se významem, různé formy téhož slova, apod.).
2. Z každé skupiny podobných výrazů ponechat POUZE JEDEN nejlepší (nejpřesnější nápověda, nejcharakterističtější pro Pionýr).
3. Ostatní z dané skupiny označit jako odstraněné a u každého uvést krátký důvod v češtině.
4. Výrazy, které jsou unikátní a kvalitní, ponechat beze změny.

DŮLEŽITÉ: Neodstraňuj výrazy jen proto, že jsou tematicky podobné – odstraňuj pouze skutečné duplicity nebo slova se zcela totožným významem.
Počet zachovaných položek by měl být co nejvyšší – buď konzervativní.

SEZNAM POLOŽEK SLOVNÍKU:
{vocab_text}
"""

    from google.genai import types

    models_to_try = [extractor.MODEL_NAME] + [
        m for m in extractor.FALLBACK_MODELS if m != extractor.MODEL_NAME
    ]

    response = None
    for model_candidate in models_to_try:
        try:
            logger.info(f"Odesílám slovník ke čistění na Gemini ({model_candidate})...")
            response = extractor.client.models.generate_content(
                model=model_candidate,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VocabCleanupResult,
                    temperature=0.1,   # nízká teplota = deterministický výsledek
                ),
            )
            if response and response.text:
                extractor.MODEL_NAME = model_candidate
                break
        except Exception as e:
            logger.warning(f"Model {model_candidate} selhal: {e}. Zkouším další...")
            import time
            time.sleep(1.5)

    if not response or not response.text:
        raise RuntimeError("Gemini API vrátilo prázdnou odpověď při čistění slovníku.")

    data = json.loads(response.text)

    # Normalizace zachovaných položek
    kept_raw = data.get("kept", [])
    removed_raw = data.get("removed", [])

    kept: List[Dict[str, str]] = []
    for it in kept_raw:
        ans = normalize_answer(it.get("answer", ""))
        clue = clean_clue(it.get("clue", ""))
        if ans and clue:
            kept.append({"answer": ans, "clue": clue})

    removed: List[Dict[str, str]] = []
    for it in removed_raw:
        ans = normalize_answer(it.get("answer", ""))
        clue = clean_clue(it.get("clue", ""))
        reason = it.get("reason", "").strip()
        if ans:
            removed.append({"answer": ans, "clue": clue, "reason": reason})

    # Seřadit zachované abecedně a uložit
    kept_sorted = sorted(kept, key=lambda x: x["answer"])
    save_questions(kept_sorted, filepath)

    logger.info(
        f"Čistění slovníku dokončeno: zachováno {len(kept_sorted)}, odstraněno {len(removed)} položek."
    )
    return kept_sorted, removed



def save_questions(items: List[Dict[str, str]], filepath: str = "pionyr_otazky.json"):
    """Uloží seznam otázek do JSON souboru."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    logger.info(f"Otázky byly úspěšně uloženy do '{filepath}' ({len(items)} položek).")


def load_questions(filepath: str = "pionyr_otazky.json") -> List[Dict[str, str]]:
    """Načte uložené otázky z JSON souboru."""
    p = Path(filepath)
    if not p.exists():
        logger.warning(f"Soubor '{filepath}' neexistuje.")
        return []

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "items" in data:
        return data["items"]
    return []


# ---------------------------------------------------------------------------
# CLI rozhraní
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrakce otázek pro křížovku pomocí Gemini API")
    parser.add_argument("--input", type=str, default="pionyr_obsah.json", help="Vstupní soubor z crawleru")
    parser.add_argument("--output", type=str, default="pionyr_otazky.json", help="Výstupní JSON s otázkami")
    parser.add_argument("--api-key", type=str, default=None, help="Volitelný Gemini API klíč (jinak z .env)")
    args = parser.parse_args()

    api_key_to_use = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key_to_use:
        print("CHYBA: Není nastaven GEMINI_API_KEY. Zadejte jej do souboru .env nebo parametrem --api-key.")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"CHYBA: Vstupní soubor '{args.input}' nebyl nalezen. Nejprve spusťte: python crawler.py")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        pages_data = json.load(f)

    extractor = GeminiExtractor(api_key=api_key_to_use)
    extracted = extractor.process_crawled_data(pages_data)
    save_questions(extracted, filepath=args.output)
    print(f"Hotovo! Extrahováno {len(extracted)} otázek a uloženo do {args.output}")
