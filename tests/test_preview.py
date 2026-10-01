import tempfile
import unittest
from datetime import date
from pathlib import Path
from manga_checker.book_pages import write_book_pages
from manga_checker.models import Comic, ComicReport
from manga_checker.preview import (
    cmoa_search_url,
    fallback_catalog_url,
    is_official_preview_url,
    is_released,
    pick_giga_first_episode,
    pick_matching_preview_link,
    pick_official_url,
    preview_fetch_order,
    preview_links_for,
    search_official_preview,
    search_queries,
    search_query,
    _preview_name,
    _search_result_url,
    _short_search_name,
    _unwrap_search_url,
)


class PreviewUrlTests(unittest.TestCase):
    def test_pick_prefers_episode_on_official_host(self) -> None:
        urls = [
            "https://example.com/foo",
            "https://comic-days.com/search?q=test",
            "https://shonenjumpplus.com/episode/13932016480028985562",
            "https://shonenjumpplus.com/episode/13932016480028985562",
        ]
        self.assertEqual(
            pick_official_url(urls),
            "https://shonenjumpplus.com/episode/13932016480028985562",
        )

    def test_rejects_non_official_and_search_paths(self) -> None:
        self.assertFalse(is_official_preview_url("https://www.amazon.co.jp/dp/x"))
        self.assertFalse(is_official_preview_url("https://comic-days.com/search?q=a"))
        self.assertTrue(is_official_preview_url("https://www.comic-days.com/episode/1"))
        self.assertTrue(
            is_official_preview_url(
                "https://shonen-sirius.com/comics/2026/9_02/0000429532.html"
            )
        )
        self.assertTrue(
            is_official_preview_url(
                "https://comic-walker.com/detail/KC_00500001290011_E"
            )
        )
        self.assertTrue(
            is_official_preview_url(
                "https://ciao.shogakukan.co.jp/comics/title/00827/episode/32377"
            )
        )
        self.assertTrue(
            is_official_preview_url(
                "https://shonenjumpplus.com/volume/9253191255858703505/trial"
            )
        )
        self.assertFalse(is_official_preview_url("https://shonenjumpplus.com/volume/trial"))
        self.assertTrue(
            is_official_preview_url(
                "https://www.s-manga.net/reader/main.php?cid=08X10000000074007700"
            )
        )
        self.assertFalse(is_official_preview_url("https://www.s-manga.net/reader/main.php"))
        self.assertTrue(is_official_preview_url("https://comic-fuz.com/manga/123"))
        self.assertTrue(
            is_official_preview_url("https://championcross.jp/series/aob6b28b34511/1")
        )
        self.assertTrue(
            is_official_preview_url(
                "https://pocket.shonenmagazine.com/title/03264/episode/438779"
            )
        )
        self.assertTrue(is_official_preview_url("https://yanmaga.jp/comics/MADE_IN_YAMATO"))
        self.assertTrue(
            is_official_preview_url(
                "https://yanmaga.jp/viewer/comics/MADE_IN_YAMATO/e03697a8d6a2050f1b14c10daae6c392"
            )
        )
        self.assertFalse(is_official_preview_url("https://mechacomic.jp/books/123"))
        self.assertTrue(
            is_official_preview_url(
                "https://www.sunday.webry.com/episode/12207421983738300325"
            )
        )
        self.assertTrue(
            is_official_preview_url(
                "https://www.sunday-webry.com/episode/12207421983738300325"
            )
        )
        self.assertFalse(
            is_official_preview_url(
                "https://shogakukan-comic.jp/book?jdcn=098548050000d0000000"
            )
        )
        self.assertFalse(
            is_official_preview_url("https://shogakukan-comic.jp/book?isbn=9784098734719")
        )
        self.assertFalse(is_official_preview_url("https://pocket.shonenmagazine.com/article/ABJ"))
        self.assertTrue(
            is_official_preview_url(
                "https://rimacomiplus.jp/cocohana/episodes/73b5eb672977e"
            )
        )
        self.assertTrue(
            is_official_preview_url(
                "https://rimacomiplus.jp/betsuma/episodes/abc"
            )
        )

    def test_unwraps_bing_redirect(self) -> None:
        import base64

        target = "https://shonenjumpplus.com/episode/9253191254199645867"
        payload = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
        wrapped = "https://www.bing.com/ck/a?!&&p=abc&u=a1" + payload
        self.assertEqual(_unwrap_search_url(wrapped), target)
        self.assertTrue(is_official_preview_url(wrapped))

    def test_web_search_keeps_ddg_when_google_empty_and_bing_is_maps(self) -> None:
        from unittest.mock import patch

        from manga_checker.preview import default_web_search

        rima = "https://rimacomiplus.jp/cocohana/episodes/73b5eb672977e"
        with patch("manga_checker.preview._google_html_search", return_value=[]), patch(
            "manga_checker.preview._bing_html_search",
            return_value=["https://maps.google.co.jp/mapfiles/home3.html"],
        ), patch(
            "manga_checker.preview._ddg_html_search",
            return_value=[rima, "https://www.cmoa.jp/title/1"],
        ), patch("manga_checker.preview._ddg_library_search", return_value=[]):
            hits = default_web_search("バツイチ人魚、恋に溺れる。 1話")
        self.assertEqual(pick_official_url(hits), rima)

    def test_skips_non_official_engine_hits(self) -> None:
        from manga_checker.preview import _first_official_search_hits

        batches = [
            [],
            [
                "https://ejje.weblio.jp/content/made",
                "https://www.made.com/",
            ],
            [
                "https://yanmaga.jp/comics/MADE_IN_YAMATO",
                "https://comic-days.com/episode/12207421984186879152",
            ],
        ]
        hits = _first_official_search_hits(batches)
        self.assertEqual(hits[0], "https://yanmaga.jp/comics/MADE_IN_YAMATO")
        self.assertEqual(
            pick_official_url(hits),
            "https://comic-days.com/episode/12207421984186879152",
        )

    def test_pick_prefers_yanmaga_viewer(self) -> None:
        urls = [
            "https://mechacomic.jp/books/123",
            "https://yanmaga.jp/comics/MADE_IN_YAMATO",
            "https://yanmaga.jp/viewer/comics/MADE_IN_YAMATO/e03697a8d6a2050f1b14c10daae6c392",
        ]
        self.assertEqual(
            pick_official_url(urls),
            "https://yanmaga.jp/viewer/comics/MADE_IN_YAMATO/e03697a8d6a2050f1b14c10daae6c392",
        )

    def test_pick_prefers_webry_episode_not_shogakukan_book(self) -> None:
        urls = [
            "https://shogakukan-comic.jp/book?jdcn=098548050000d0000000",
            "https://www.sunday-webry.com/episode/12207421983738300325",
        ]
        self.assertEqual(
            pick_official_url(urls),
            "https://www.sunday-webry.com/episode/12207421983738300325",
        )

    def test_pick_prefers_episode_over_volume_trial(self) -> None:
        urls = [
            "https://shonenjumpplus.com/volume/9253191255858703505/trial",
            "https://shonenjumpplus.com/episode/9253191254199645867",
        ]
        self.assertEqual(
            pick_official_url(urls),
            "https://shonenjumpplus.com/episode/9253191254199645867",
        )

    def test_pick_giga_first_episode_matches_title(self) -> None:
        html = """
        <div class="title-box">
          <p class="series-title">別作品</p>
          <a class="main-link" href="https://shonenjumpplus.com/episode/aaa">1話を読む</a>
        </div>
        <div class="title-box">
          <p class="series-title">あわいの焔刃</p>
          <a class="main-link" href="https://shonenjumpplus.com/episode/9253191254350319417">1話を読む</a>
        </div>
        """
        self.assertEqual(
            pick_giga_first_episode(html, "あわいの焔刃", "shonenjumpplus.com"),
            "https://shonenjumpplus.com/episode/9253191254350319417",
        )

    def test_preview_name_keeps_20_to_30_chars(self) -> None:
        long_title = (
            "ゲーム開始前に死ぬモブ悪役皇子に転生した俺 "
            "〜推しヒロインの妹と幸せになるために最弱魔法【闇刃】を"
            "過剰な努力で極め抜いたら、最強のぶっ壊れ性能と化していた件〜(1)"
        )
        name = _preview_name(Comic(title=long_title, volume="1"))
        self.assertGreaterEqual(len(name), 20)
        self.assertLessEqual(len(name), 30)
        self.assertIn("ゲーム開始前に死ぬモブ悪役皇子に転生した俺", name)
        self.assertNotIn("ぶっ壊れ", name)

    def test_pick_matching_uses_thumbnail_alt_and_list_item(self) -> None:
        html = """
        <ul class="series-list">
          <li>
            <div class="thmb-container">
              <a href="/episode/12207421983410089641">
                <img alt="種生産　～このスキルがチートだとまだ誰も気付いていない～">
              </a>
            </div>
            <a href="/episode/12207421983410089641">1話を読む</a>
          </li>
        </ul>
        """
        self.assertEqual(
            pick_matching_preview_link(
                html,
                "種生産 このスキルがチートだとまだ誰も気付いていない",
                "comic-days.com",
            ),
            "https://comic-days.com/episode/12207421983410089641",
        )
        html = """
        <a href="/title/03264/episode/438779">ゲーム開始前に死ぬモブ悪役皇子に転生した俺</a>
        <a href="/title/03264/episode/443841">最新話を読む</a>
        """
        self.assertEqual(
            pick_matching_preview_link(
                html,
                "ゲーム開始前に死ぬモブ悪役皇子に転生した俺",
                "pocket.shonenmagazine.com",
            ),
            "https://pocket.shonenmagazine.com/title/03264/episode/438779",
        )

    def test_search_queries_use_title_and_trial(self) -> None:
        comic = Comic(title="あっ、悪魔ちゃん 1", publisher="集英社")
        queries = search_queries(comic)
        self.assertEqual(queries[0], "あっ、悪魔ちゃん 1話")
        self.assertNotIn("1巻", queries[0])
        self.assertNotIn("第1巻", queries[0])
        self.assertNotRegex(queries[0], r"\(\s*1\s*\)")
        self.assertTrue(any("1話 site:shonenjumpplus.com" in q for q in queries))
        self.assertTrue(any("1話 site:rimacomiplus.jp" in q for q in queries))

    def test_long_title_keeps_full_query_and_kadokawa_sirius(self) -> None:
        long_title = "非の打ち所のない令息から婚約の打診が来たので、断ってみました(1)"
        comic = Comic(title=long_title, publisher="KADOKAWA", isbn="9784040000000")
        queries = search_queries(comic)
        self.assertTrue(queries[0].startswith("非の打ち所のない令息から婚約の打診が来たので、断ってみました 1話"))
        self.assertGreater(len(queries[0]), 30)
        self.assertTrue(any("site:shonen-sirius.com" in q for q in queries))
        self.assertTrue(any("site:comic-walker.com" in q for q in queries))

    def test_short_site_query_and_publisher_hosts(self) -> None:
        self.assertEqual(
            _short_search_name("バキのわ! バキを語る女子高校生たち"),
            "バキのわ",
        )
        akita = search_queries(
            Comic(title="バキのわ!〜バキを語る女子高校生たち〜 1", publisher="秋田書店")
        )
        self.assertTrue(any("1話 site:championcross.jp" in q for q in akita))
        shoga = search_queries(Comic(title="嘘と最愛の品格 1", publisher="小学館", isbn="9784098730000"))
        manga_one = next(i for i, q in enumerate(shoga) if "site:manga-one.com" in q)
        webry = next(i for i, q in enumerate(shoga) if "site:sunday-webry.com" in q)
        self.assertLess(manga_one, webry)
        self.assertFalse(any("site:shogakukan-comic.jp" in q for q in shoga))
        houbun = search_queries(Comic(title="件の件について 1", publisher="芳文社"))
        self.assertTrue(any("1話 site:comic-fuz.com" in q for q in houbun))
        hakusen = search_queries(Comic(title="花とゆめ作品 1", publisher="白泉社"))
        self.assertTrue(any("1話 site:manga-park.com" in q for q in hakusen))
        take = search_queries(Comic(title="竹書房作品 1", publisher="竹書房"))
        self.assertTrue(any("1話 site:takecomic.jp" in q for q in take))

    def test_isbn_maps_imprint_to_kodansha_sites(self) -> None:
        from manga_checker.preview import preview_hosts_for, isbn_publisher_guess

        comic = Comic(
            title="種生産 〜このスキルがチートだとまだ誰も気付いていない〜(1)",
            publisher="清談社",
            isbn="9784065445679",
        )
        self.assertEqual(isbn_publisher_guess(comic.isbn), "講談社")
        hosts = preview_hosts_for(comic)
        self.assertIn("comic-days.com", hosts)
        self.assertIn("pocket.shonenmagazine.com", hosts)

    def test_engine_hits_keep_publisher_hosts(self) -> None:
        urls = [
            "https://comic-days.com/episode/kodansha",
            "https://shonenjumpplus.com/episode/shueisha",
        ]
        self.assertEqual(
            pick_official_url(urls, allowed_hosts=("shonenjumpplus.com",)),
            "https://shonenjumpplus.com/episode/shueisha",
        )
        self.assertEqual(
            pick_official_url(urls, allowed_hosts=("pocket.shonenmagazine.com", "comic-days.com")),
            "https://comic-days.com/episode/kodansha",
        )

    def test_pick_prefers_rimacomiplus_episode(self) -> None:
        urls = [
            "https://www.s-manga.net/reader/main.php?cid=9784088433158",
            "https://rimacomiplus.jp/cocohana/episodes/73b5eb672977e",
        ]
        self.assertEqual(
            pick_official_url(urls),
            "https://rimacomiplus.jp/cocohana/episodes/73b5eb672977e",
        )

    def test_cmoa_and_fallback(self) -> None:
        comic = Comic(title="勇者デストロイヤーズ 1", publisher="集英社", isbn="9784088852287")
        self.assertIn("cmoa.jp/search/result/?word=", cmoa_search_url(comic))
        self.assertNotIn("keyword=", cmoa_search_url(comic))
        url, label = fallback_catalog_url(comic)
        self.assertIn("google.com/search", url)
        self.assertNotIn("%E8%A9%A6%E3%81%97%E8%AA%AD%E3%81%BF", url)
        self.assertIn("1%E8%A9%B1", url)
        self.assertEqual(label, "試し読みを検索")
        self.assertNotIn("hanmoto", url)

    def test_publisher_fallback_without_isbn(self) -> None:
        comic = Comic(title="テスト作品 1", publisher="講談社")
        url, label = fallback_catalog_url(comic)
        self.assertIn("google.com/search", url)
        self.assertEqual(label, "試し読みを検索")

    def test_released_uses_full_date(self) -> None:
        today = date(2026, 9, 27)
        self.assertTrue(is_released("2026-09-04", today=today))
        self.assertFalse(is_released("2026-10-08", today=today))

    def test_search_query_strips_volume(self) -> None:
        comic = Comic(title="勇者デストロイヤーズ 1", volume="1")
        self.assertEqual(search_query(comic), "勇者デストロイヤーズ 1話")
        self.assertNotIn("1巻", search_query(comic))
        self.assertNotIn('"', search_query(comic))

    def test_preview_links_official_hides_fallback(self) -> None:
        comic = Comic(
            title="あっ、悪魔ちゃん 1",
            publisher="集英社",
            pubdate="2026-09-04",
            isbn="9784088852546",
        )
        links = preview_links_for(
            comic,
            {"official_url": "https://shonenjumpplus.com/episode/1"},
            today=date(2026, 9, 27),
        )
        self.assertTrue(links["official_url"])
        self.assertEqual(links["fallback_url"], "")
        self.assertIn("cmoa.jp", links["cmoa_url"])


class BookPageTrialButtonTests(unittest.TestCase):
    def test_buttons_use_search_hit_and_cmoa(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="あっ、悪魔ちゃん 1",
                    publisher="集英社",
                    pubdate="2026-09-04",
                    isbn="978-4-08-885254-6",
                )
            )
        ]

        def fake_search(query: str) -> list[str]:
            self.assertIn("悪魔ちゃん", query)
            return ["https://shonenjumpplus.com/episode/abc"]

        with tempfile.TemporaryDirectory() as tmp:
            books = Path(tmp) / "books"
            cache = Path(tmp) / "preview.json"
            write_book_pages(
                reports,
                books,
                preview_cache_path=cache,
                fetch_preview=True,
                search_fn=fake_search,
                preview_delay_sec=0,
            )
            body = (books / "9784088852546.html").read_text(encoding="utf-8")
        self.assertIn("公式で試し読み", body)
        self.assertNotIn("公式で第1話を試し読み", body)
        self.assertIn("https://shonenjumpplus.com/episode/abc", body)
        self.assertIn("シーモアで試し読み", body)
        self.assertIn("cmoa.jp/search/result", body)
        self.assertNotIn('class="ext trial-fallback"', body)
        self.assertNotIn("📖", body)
        self.assertNotIn("📙", body)

    def test_future_release_skips_cmoa_and_uses_fallback(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="未来の本 1",
                    publisher="講談社",
                    pubdate="2099-12-20",
                    isbn="978-4-06-000000-1",
                )
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            books = Path(tmp) / "books"
            write_book_pages(reports, books, fetch_preview=False)
            body = (books / "9784060000001.html").read_text(encoding="utf-8")
        self.assertIn("trial-fallback", body)
        self.assertIn("試し読みを検索", body)
        self.assertIn("google.com/search", body)
        self.assertNotIn("試し読みリンク不明", body)
        self.assertNotIn("版元ドットコム", body)
        self.assertNotIn("hanmoto.com", body)
        self.assertNotIn("シーモアで試し読み", body)


class PreviewSearchOrderTests(unittest.TestCase):
    def test_unwraps_google_relative_url_redirect(self) -> None:
        target = "https://comic-walker.com/detail/KC_00500001290011_E"
        wrapped = "/url?q=" + target + "&sa=U&ved=0ah"
        self.assertEqual(_search_result_url(wrapped), target)
        self.assertEqual(
            pick_official_url([wrapped, "https://www.amazon.co.jp/dp/x"]),
            target,
        )

    def test_publisher_sites_before_web_search(self) -> None:
        from unittest.mock import patch

        comic = Comic(
            title="来月の本",
            publisher="講談社",
            isbn="9784060000001",
            pubdate="2026-11-12",
        )
        magapoke = "https://pocket.shonenmagazine.com/title/1/episode/1"
        with patch(
            "manga_checker.preview.search_giga_preview",
            return_value=magapoke,
        ) as giga, patch(
            "manga_checker.preview.default_web_search",
            return_value=["https://comic-days.com/episode/12207421984186879152"],
        ) as web:
            url = search_official_preview(comic)
        self.assertEqual(url, magapoke)
        giga.assert_called()
        web.assert_not_called()

    def test_giga_runs_if_first_web_query_misses(self) -> None:
        from unittest.mock import patch

        comic = Comic(
            title="群雄を綴る(1)",
            publisher="講談社",
            isbn="9784065453575",
            pubdate="2026-10-16",
        )
        magapoke = "https://pocket.shonenmagazine.com/title/03246/episode/441544"
        with patch(
            "manga_checker.preview.search_giga_preview",
            return_value="",
        ), patch(
            "manga_checker.preview.default_web_search",
            return_value=["https://www.tohnichi.co.jp/", magapoke],
        ):
            url = search_official_preview(comic)
        self.assertEqual(url, magapoke)

    def test_kodansha_hosts_include_magapoke(self) -> None:
        from manga_checker.preview import preview_hosts_for

        hosts = preview_hosts_for(
            Comic(title="群雄を綴る(1)", publisher="講談社", isbn="9784065453575")
        )
        self.assertIn("pocket.shonenmagazine.com", hosts)
        self.assertIn("comic-days.com", hosts)

    def test_priority_publishers_have_official_preview_hosts(self) -> None:
        from manga_checker.preview import preview_hosts_for, publisher_preview_hosts
        from manga_checker.publishers import PUBLISHER_ORDER

        expected = {
            "秋田書店": ("championcross.jp",),
            "白泉社": "manga-park.com",
            "竹書房": "takecomic.jp",
            "双葉社": "comic-action.com",
            "少年画報社": "mangadx-plus.com",
            "徳間書店": "comic-ryu.jp",
            "一迅社": "zerosumonline.com",
            "コアミックス": "comic-zenon.com",
            "TOブックス": "comic-gardo.com",
            "オーバーラップ": "comic-gardo.com",
            "フロンティアワークス": "comic-growl.com",
            "ホビージャパン": "comic-fire.com",
            "ブシロードワークス": "comic-boost.com",
            "マイクロマガジン社": "comic-ride.jp",
            "イマジカインフォス": "lovecoffre.com",
            "アルファポリス": "alphapolis.co.jp",
        }
        for name in PUBLISHER_ORDER:
            self.assertTrue(publisher_preview_hosts(name), name)
        self.assertEqual(publisher_preview_hosts("秋田書店"), expected["秋田書店"])
        for name, host in expected.items():
            if name == "秋田書店":
                continue
            self.assertIn(host, preview_hosts_for(Comic(title="x 1", publisher=name)))
        self.assertTrue(is_official_preview_url("https://manga-park.com/title/123/episode/1"))
        self.assertTrue(is_official_preview_url("https://takecomic.jp/episode/abc"))
        self.assertTrue(is_official_preview_url("https://comic-gardo.com/episode/1"))

    def test_magapoke_title_episode_is_official(self) -> None:
        self.assertTrue(
            is_official_preview_url(
                "https://pocket.shonenmagazine.com/title/03246/episode/441544"
            )
        )

    def test_preview_fetch_order_puts_future_before_past(self) -> None:
        comics = [
            Comic(title="六月", isbn="9784060000001", pubdate="2026-06-01"),
            Comic(title="十一月", isbn="9784060000002", pubdate="2026-11-01"),
            Comic(title="九月", isbn="9784060000003", pubdate="2026-09-15"),
        ]
        ordered = preview_fetch_order(comics, today=date(2026, 9, 30))
        self.assertEqual([c.title for c in ordered], ["九月", "十一月", "六月"])


if __name__ == "__main__":
    unittest.main()
