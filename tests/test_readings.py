import unittest

from manga_checker.readings import kana_to_romaji, search_index_text, to_hiragana


class ReadingIndexTests(unittest.TestCase):
    def test_kaze_and_fuu_match_wind_and_cloud(self) -> None:
        blob = search_index_text("風と雲", title_kana="カゼトクモ").replace(" ", "").lower()
        self.assertIn("かぜ", blob)
        self.assertIn("ふう", blob)
        self.assertIn("くも", blob)
        self.assertIn("うん", blob)
        self.assertIn("kazetokumo", blob)
        romaji = kana_to_romaji("ふう")
        self.assertIn(romaji, blob)

    def test_official_kana_hiragana(self) -> None:
        blob = search_index_text("風と雲", title_kana="カゼトクモ")
        self.assertIn(to_hiragana("カゼトクモ"), blob.replace(" ", ""))

    def test_koi_ren(self) -> None:
        blob = search_index_text("恋月").replace(" ", "")
        self.assertIn("こい", blob)
        self.assertIn("れん", blob)
        self.assertIn("つき", blob)
        self.assertIn("げつ", blob)

    def test_single_kana_is_in_title_not_only_publisher(self) -> None:
        blob = search_index_text("6年生なのに", publisher="スクウェア・エニックス")
        self.assertIn("スクウェア", blob)

    def test_mae_reading_is_indexed_for_long_query(self) -> None:
        blob = search_index_text("お前がやったんだろ").replace(" ", "")
        self.assertIn("まえ", blob)
