"""
main.py - Hlavní vstupní skript pro aplikaci Pionýr Crossword

Umožňuje:
1. Spustit Streamlit webové rozhraní: `python main.py --ui`
2. Vygenerovat novou křížovku do terminálu nebo PDF/HTML souboru:
   `python main.py --words 12 --secret PIONYR --pdf vystup.pdf`
3. Spustit crawler a extrakci přes Gemini API:
   `python main.py --crawl --pages 10`
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from crawler import crawl_pionyr
from extractor import GeminiExtractor, deduplicate_items, load_questions, save_questions
from generator import CrosswordGenerator
from pdf_exporter import export_crossword_pdf, generate_printable_html
from utils import normalize_answer


def main():
    parser = argparse.ArgumentParser(
        description="Pionýr Crossword - Automatický generátor křížovek pro pionyr.cz",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Příklady použití:
  python main.py --ui                                # Spustí webové rozhraní Streamlit
  python main.py --words 12 --secret PIONYR          # Vygeneruje křížovku do konzole
  python main.py --words 10 --html krizovka.html     # Uloží tisknutelné HTML
  python main.py --words 12 --pdf krizovka.pdf       # Uloží čisté PDF k tisku
  python main.py --crawl --pages 8                   # Stáhne články a ideály z pionyr.cz
        """
    )

    parser.add_argument("--ui", action="store_true", help="Spustit webové rozhraní ve Streamlitu")
    parser.add_argument("--words", type=int, default=12, help="Počet slov v křížovce (výchozí: 12)")
    parser.add_argument("--secret", type=str, default="PIONYR", help="Tajenka křížovky (výchozí: PIONYR)")
    parser.add_argument("--pdf", type=str, default=None, help="Cesta pro uložení křížovky do PDF")
    parser.add_argument("--html", type=str, default=None, help="Cesta pro uložení křížovky do tisknutelného HTML")
    parser.add_argument("--solution", action="store_true", help="Při exportu do PDF/HTML zahrnout i řešení")
    parser.add_argument("--url", type=str, default=None, help="Vycucnout křížovková slova z konkrétní URL adresy")
    parser.add_argument("--crawl", action="store_true", help="Spustit stažení stránek z pionyr.cz a extrakci přes Gemini")
    parser.add_argument("--pages", type=int, default=8, help="Počet stránek pro crawler (výchozí: 8)")
    parser.add_argument("--api-key", type=str, default=None, help="Gemini API klíč (jinak se načte z .env)")

    args = parser.parse_args()

    # 1. Spuštění UI ve Streamlitu
    if args.ui:
        print("Spouštím webové rozhraní Streamlit...")
        try:
            cmd = [sys.executable, "-m", "streamlit", "run", "app.py"]
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\nAplikace byla ukončena.")
        return

    # 2. Vycucnutí z konkrétní URL
    if args.url:
        api_key = args.api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("CHYBA: Není nastaven GEMINI_API_KEY. Zadejte jej v souboru .env nebo parametrem --api-key.")
            sys.exit(1)

        print(f"Stahuji a analyzuji zadanou URL: {args.url}...")
        extractor = GeminiExtractor(api_key=api_key)
        items = extractor.extract_from_url(args.url)

        existing = load_questions("pionyr_otazky.json")
        existing_answers = {it["answer"] for it in existing}

        new_words = [it for it in items if it["answer"] not in existing_answers]
        if new_words:
            updated = existing + new_words
            save_questions(updated, "pionyr_otazky.json")
            print(f"\nÚSPĚCH! Bylo přidáno {len(new_words)} nových slov do slovníku:")
            for w in new_words:
                print(f"  + [{w['answer']}] {w['clue']}")
            print(f"Celkem ve slovníku: {len(updated)} otázek.")
        else:
            print(f"\nZe stránky bylo získáno {len(items)} slov, ale všechna již ve slovníku existují.")
        return

    # 3. Spuštění crawleru a extrakce přes Gemini
    if args.crawl:
        api_key = args.api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("CHYBA: Není nastaven GEMINI_API_KEY. Zadejte jej v souboru .env nebo parametrem --api-key.")
            sys.exit(1)

        print(f"1. Spouštím crawler pro web pionyr.cz (limit: {args.pages} stránek)...")
        pages = crawl_pionyr(max_pages=args.pages)
        if not pages:
            print("CHYBA: Crawler nezískal žádný obsah.")
            sys.exit(1)

        print(f"2. Extrahuji křížovkové pojmy pomocí Gemini 2.5 Flash...")
        extractor = GeminiExtractor(api_key=api_key)
        new_items = extractor.process_crawled_data(pages)

        existing = load_questions("pionyr_otazky.json")
        combined = deduplicate_items(existing + new_items)
        save_questions(combined, "pionyr_otazky.json")
        print(f"Hotovo! Do pionyr_otazky.json bylo uloženo celkem {len(combined)} otázek.")
        return

    # 3. Vygenerování křížovky
    norm_secret = normalize_answer(args.secret) if args.secret else None
    print(f"Generuji křížovku (počet slov: {args.words}, tajenka: {norm_secret or 'žádná'})...")
    gen = CrosswordGenerator(vocabulary_path="pionyr_otazky.json")
    puzzle = gen.generate(word_count=args.words, secret_word=norm_secret)

    if not puzzle:
        print("CHYBA: Křížovku se nepodařilo vygenerovat. Zkuste jiný počet slov.")
        sys.exit(1)

    print(f"\nÚSPĚCH! Vygenerována mřížka {puzzle.width}×{puzzle.height} s {len(puzzle.words)} slovy.\n")

    # Výpis do konzole
    secret_set = {(sc.x, sc.y) for sc in puzzle.secret_cells}
    for y, row in enumerate(puzzle.grid):
        line = []
        for x, ch in enumerate(row):
            if ch:
                if (x, y) in secret_set:
                    line.append(f"[{ch}]")
                else:
                    line.append(f" {ch} ")
            else:
                line.append(" · ")
        print("".join(line))

    print("\nVODOROVNĚ:")
    for w in puzzle.across_clues:
        print(f"  {w.number:2d}. {w.clue} ({len(w.word)} písmen) [{w.word}]")

    print("\nSVISLE:")
    for w in puzzle.down_clues:
        print(f"  {w.number:2d}. {w.clue} ({len(w.word)} písmen) [{w.word}]")

    if puzzle.secret_cells:
        print(f"\nTAJENKA: {puzzle.secret_word}")
        for sc in sorted(puzzle.secret_cells, key=lambda s: s.order_index):
            print(f"  {sc.order_index}. písmeno '{sc.char}' na souřadnici [{sc.x}, {sc.y}]")

    # Export do HTML
    if args.html:
        html_content = generate_printable_html(puzzle, show_solution=args.solution)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"\nTisknutelné HTML bylo uloženo do: {args.html}")

    # Export do PDF
    if args.pdf:
        try:
            export_crossword_pdf(puzzle, output_path=args.pdf, show_solution=args.solution)
            print(f"PDF soubor byl úspěšně vytvořen: {args.pdf}")
        except Exception as e:
            print(f"Chyba při exportu do PDF (zkontrolujte reportlab): {e}")


if __name__ == "__main__":
    main()
