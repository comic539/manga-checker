import unittest

from manga_checker.search_title import bare_search_title, toranoana_search_word


class BareSearchTitleTests(unittest.TestCase):
    def test_strips_volume_markers(self) -> None:
        self.assertEqual(bare_search_title("はじめての冒険 第1巻"), "はじめての冒険")
        self.assertEqual(bare_search_title("はじめての冒険 第１巻"), "はじめての冒険")
        self.assertEqual(bare_search_title("夜は猫といっしょ(1)"), "夜は猫といっしょ")
        self.assertEqual(bare_search_title("夜は猫といっしょ（１）"), "夜は猫といっしょ")
        self.assertEqual(bare_search_title("リベンジアクト 1巻"), "リベンジアクト")
        self.assertEqual(bare_search_title("冒険 一巻"), "冒険")
        self.assertEqual(bare_search_title("冒険 全1巻"), "冒険")
        self.assertEqual(bare_search_title("Example Volume 1"), "Example")
        self.assertEqual(bare_search_title("Example Vol.1"), "Example")
        self.assertEqual(bare_search_title("タイトル 1"), "タイトル")
        self.assertEqual(bare_search_title("ヒトナー 1"), "ヒトナー")

    def test_strips_decoration(self) -> None:
        self.assertEqual(bare_search_title("作品名 @COMIC (1)"), "作品名")
        self.assertEqual(bare_search_title("【コミック】社畜おじさん触手を買う(1)"), "社畜おじさん触手を買う")

    def test_keeps_meaningful_one(self) -> None:
        self.assertEqual(bare_search_title("1日10分でわかる世界史"), "1日10分でわかる世界史")

    def test_volume_field_not_appended(self) -> None:
        self.assertEqual(bare_search_title("リベンジアクト", "第1巻"), "リベンジアクト")

    def test_wave_dashes_become_spaces(self) -> None:
        self.assertEqual(
            bare_search_title("目が痛い~突然始まる異世界"),
            "目が痛い 突然始まる異世界",
        )
        self.assertEqual(
            bare_search_title("目が痛い〜突然始まる異世界"),
            "目が痛い 突然始まる異世界",
        )
        self.assertEqual(
            bare_search_title("目が痛い～突然始まる異世界"),
            "目が痛い 突然始まる異世界",
        )


class ToranoanaSearchWordTests(unittest.TestCase):
    def test_drops_subtitle_and_decoration(self) -> None:
        self.assertEqual(toranoana_search_word("ヒトナー 1"), "ヒトナー")
        self.assertEqual(
            toranoana_search_word(
                "この世界の顔面偏差値が高すぎて目が痛い〜突然始まる異世界溺愛生活〜"
            ),
            "この世界の顔面偏差値が高すぎて目が痛い",
        )
        self.assertEqual(toranoana_search_word("【コミック】初凪ヒメリウム (1)"), "初凪ヒメリウム")
