"""
Testes unitários para a lógica pura de filtro de palavras-chave.

Rode com:
    python -m unittest test_keywords.py
"""

import tempfile
import unittest
from pathlib import Path

from keywords import find_matches, load_keywords, normalize, save_keywords


class NormalizeTest(unittest.TestCase):
    def test_lower_cases(self):
        self.assertEqual(normalize("Air Fryer"), "air fryer")

    def test_removes_accents(self):
        self.assertEqual(normalize("cadeira ergonômica"), "cadeira ergonomica")
        self.assertEqual(normalize("teclado mecânico"), "teclado mecanico")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("air   fryer"), "air fryer")
        self.assertEqual(normalize("  air fryer  "), "air fryer")

    def test_empty_string(self):
        self.assertEqual(normalize(""), "")


class LoadKeywordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp_dir.name) / "keywords.txt"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_loads_keywords(self):
        self.path.write_text("ssd\nair fryer\n", encoding="utf-8")
        self.assertEqual(load_keywords(self.path), ["ssd", "air fryer"])

    def test_ignores_comments_and_blank_lines(self):
        self.path.write_text("# comentario\n\n  ryzen 7  \n\n# outro\n", encoding="utf-8")
        self.assertEqual(load_keywords(self.path), ["ryzen 7"])

    def test_returns_empty_when_file_missing(self):
        missing = Path(self.tmp_dir.name) / "nao_existe.txt"
        self.assertEqual(load_keywords(missing), [])


class SaveKeywordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp_dir.name) / "keywords.txt"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_saves_sorted_keywords(self):
        save_keywords(["zebra", "abacate", "Air Fryer"], self.path)
        content = self.path.read_text(encoding="utf-8")
        self.assertEqual(content, "abacate\nAir Fryer\nzebra\n")

    def test_removes_duplicates_case_insensitive(self):
        save_keywords(["ssd", "SSD", "ssd", "air fryer"], self.path)
        content = self.path.read_text(encoding="utf-8")
        self.assertEqual(content, "air fryer\nssd\n")


class FindMatchesTest(unittest.TestCase):
    def test_basic_match(self):
        self.assertEqual(find_matches("promoção de ssd", ["ssd"]), ["ssd"])

    def test_no_match(self):
        self.assertEqual(find_matches("promoção de mouse", ["ssd"]), [])

    def test_ignores_case_and_accents(self):
        self.assertEqual(
            find_matches("TeClAdO MecÂnico", ["teclado mecanico"]),
            ["teclado mecanico"],
        )

    def test_matches_with_hyphens_and_spaces(self):
        self.assertEqual(find_matches("AirFryer em promoção", ["air fryer"]), ["air fryer"])
        self.assertEqual(find_matches("air-fryer barato", ["air fryer"]), ["air fryer"])

    def test_word_boundary(self):
        # 'ssd' não deve casar com 'ssdex' ou 'abcssd'
        self.assertEqual(find_matches("ssdex em promoção", ["ssd"]), [])
        self.assertEqual(find_matches("abcssd em promoção", ["ssd"]), [])

    def test_multiple_keywords_keeps_order_of_keyword_list(self):
        text = "promoção de ssd e air fryer"
        matches = find_matches(text, ["ssd", "air fryer", "mouse"])
        self.assertEqual(matches, ["ssd", "air fryer"])

    def test_multiword_keyword_boundary(self):
        # 'ryzen 7' não deve casar com 'ryzen 70'
        self.assertEqual(find_matches("ryzen 70 em promoção", ["ryzen 7"]), [])


if __name__ == "__main__":
    unittest.main()
