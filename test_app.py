"""
test_app.py - Jednotkové testy pro aplikaci generování křížovek Pionýr
"""

import unittest
from utils import remove_diacritics, normalize_answer, clean_clue
from generator import CrosswordGenerator, CrosswordBuilder, PlacedWord
from crawler import PionyrCrawler
from pdf_exporter import export_crossword_pdf, generate_printable_html


class TestUtils(unittest.TestCase):
    def test_remove_diacritics(self):
        self.assertEqual(remove_diacritics("PŘÁTELSTVÍ"), "PRATELSTVI")
        self.assertEqual(remove_diacritics("Činžovní dům"), "Cinzovni dum")
        self.assertEqual(remove_diacritics("Žluťoučký kůň"), "Zlutoucky kun")

    def test_normalize_answer(self):
        self.assertEqual(normalize_answer("přátelství"), "PRATELSTVI")
        self.assertEqual(normalize_answer("  \"tábor!\"  "), "TABOR")
        self.assertEqual(normalize_answer("Křišťálová vlaštovka"), "KRISTALOVA")
        # Příliš krátké (< 3 znaky)
        self.assertIsNone(normalize_answer("ne"))
        # Příliš dlouhé (> 12 znaků)
        self.assertIsNone(normalize_answer("nejnezdevatadvacetinasobnejsi"))

    def test_clean_clue(self):
        self.assertEqual(clean_clue("Jak se jmenuje maskot"), "Jak se jmenuje maskot.")
        self.assertEqual(clean_clue("Kdo to ví?"), "Kdo to ví?")


class TestCrawlerFilters(unittest.TestCase):
    def setUp(self):
        self.crawler = PionyrCrawler()

    def test_valid_urls(self):
        self.assertTrue(self.crawler.is_valid_url("https://pionyr.cz/o-pionyru/"))
        self.assertTrue(self.crawler.is_valid_url("https://pionyr.cz/prehled-clanku/?detail=123"))

    def test_invalid_urls(self):
        # Cizí domény
        self.assertFalse(self.crawler.is_valid_url("https://facebook.com/pionyr.cz"))
        # Soubory
        self.assertFalse(self.crawler.is_valid_url("https://pionyr.cz/soubor.pdf"))
        self.assertFalse(self.crawler.is_valid_url("https://pionyr.cz/obrazek.jpg"))
        # Admin a kontakty
        self.assertFalse(self.crawler.is_valid_url("https://pionyr.cz/wp-admin/"))
        self.assertFalse(self.crawler.is_valid_url("https://pionyr.cz/kontakty/"))


class TestGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = CrosswordGenerator(vocabulary_path="pionyr_otazky.json")

    def test_load_vocabulary(self):
        self.assertGreater(len(self.gen.vocabulary), 20)
        for item in self.gen.vocabulary:
            self.assertTrue(3 <= len(item["answer"]) <= 12)
            self.assertTrue(item["answer"].isupper())
            self.assertTrue(item["answer"].isalpha())

    def test_generate_crossword(self):
        puzzle = self.gen.generate(word_count=10, secret_word="PIONYR")
        self.assertIsNotNone(puzzle)
        self.assertGreaterEqual(len(puzzle.words), 6)
        self.assertGreater(puzzle.width, 0)
        self.assertGreater(puzzle.height, 0)
        self.assertGreater(len(puzzle.across_clues), 0)
        self.assertGreater(len(puzzle.down_clues), 0)

        # Ověření křížení: každá buňka se stejnými souřadnicemi musí obsahovat stejné písmeno
        for w in puzzle.words:
            dx, dy = (1, 0) if w.direction == "across" else (0, 1)
            for i, ch in enumerate(w.word):
                x = w.x + dx * i
                y = w.y + dy * i
                self.assertEqual(puzzle.grid[y][x], ch)

    def test_printable_html(self):
        puzzle = self.gen.generate(word_count=8, secret_word="TABOR")
        html = generate_printable_html(puzzle, show_solution=False)
        self.assertIn("Pionýrská křížovka", html)
        self.assertIn("VODOROVNĚ", html)
        self.assertIn("SVISLE", html)
        self.assertIn("<table class=\"grid-table\">", html)
        self.assertIn(":root", html)
        self.assertIn("--bg-paper: #F3F2EE", html)

    def test_export_pdf(self):
        puzzle = self.gen.generate(word_count=8, secret_word="TABOR")
        pdf_bytes = export_crossword_pdf(puzzle, show_solution=True)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)


if __name__ == "__main__":
    unittest.main()
