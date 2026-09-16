import unittest

from manga_checker.title_match import listing_matches_work, titles_match


class TitleMatchTests(unittest.TestCase):
    def test_short_title_does_not_match_longer_work(self) -> None:
        self.assertFalse(
            titles_match("ラブソング", "裏切り者のラブソング (1) 別の作者")
        )

    def test_short_title_prefix_and_exact(self) -> None:
        self.assertTrue(titles_match("ラブソング", "ラブソング (1)"))
        self.assertTrue(titles_match("ラブソング", "ラブソング"))
        self.assertTrue(titles_match("夜は猫といっしょ", "夜は猫といっしょ (1) 著者"))

    def test_title_inside_privilege_card(self) -> None:
        self.assertTrue(
            titles_match(
                "初凪ヒメリウム 1",
                "特典 【メロンブックス限定特典】 初凪ヒメリウム 描き下ろしイラストカード",
            )
        )

    def test_author_disambiguates_short_title(self) -> None:
        self.assertTrue(
            titles_match(
                "ラブソング",
                "裏切り者のラブソング 山田太郎 特典あり",
                author="山田太郎",
            )
        )
        self.assertFalse(
            titles_match(
                "ラブソング",
                "裏切り者のラブソング 別作者 特典あり",
                author="山田太郎",
            )
        )

    def test_listing_rejects_similar_but_unrelated_title(self) -> None:
        self.assertFalse(listing_matches_work("ヒトナー", "ひと夏limited"))
        self.assertTrue(listing_matches_work("ヒトナー", "ヒトナー (1)"))
        self.assertTrue(
            listing_matches_work("ヒトナー", "ISBN 9784088852317", "9784088852317")
        )
