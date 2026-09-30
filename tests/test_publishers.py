import re
import tempfile
import unittest
from pathlib import Path

from manga_checker.models import Comic, ComicReport, StoreCheck
from manga_checker.privilege import STATUS_UNKNOWN
from manga_checker.publishers import canonical_publisher, publisher_sort_key
from manga_checker.report import ASSET_VER, _group_by_publisher, write_html


class PublisherSortTests(unittest.TestCase):
    def test_priority_order(self) -> None:
        names = ["芳文社", "KADOKAWA", "秋田書店", "小学館", "講談社", "集英社", "竹書房"]
        ordered = sorted(names, key=lambda n: publisher_sort_key(n, "2026-09-01", "A"))
        self.assertEqual(
            ordered,
            ["集英社", "講談社", "小学館", "KADOKAWA", "秋田書店", "芳文社", "竹書房"],
        )

    def test_listed_publishers_keep_fixed_order(self) -> None:
        reports = [
            ComicReport(Comic(title="C", publisher="白泉社", pubdate="2026-09-02")),
            ComicReport(Comic(title="A", publisher="一迅社", pubdate="2026-09-10")),
            ComicReport(Comic(title="B", publisher="スクウェア・エニックス", pubdate="2026-09-01")),
            ComicReport(Comic(title="D", publisher="竹書房", pubdate="2026-09-01")),
            ComicReport(Comic(title="S", publisher="集英社", pubdate="2026-09-20")),
        ]
        labels = [label for label, _ in _group_by_publisher(reports)]
        self.assertEqual(
            labels,
            ["集英社", "スクウェア・エニックス", "白泉社", "竹書房", "一迅社"],
        )
        self.assertNotIn("その他", labels)

    def test_unknown_publishers_go_to_other_group(self) -> None:
        reports = [
            ComicReport(Comic(title="X", publisher="架空書房", pubdate="2026-09-01")),
            ComicReport(Comic(title="S", publisher="集英社", pubdate="2026-09-01")),
            ComicReport(Comic(title="Y", publisher="別の出版社", pubdate="2026-09-02")),
        ]
        labels = [label for label, _ in _group_by_publisher(reports)]
        self.assertEqual(labels, ["集英社", "その他"])
        other_titles = [r.comic.title for r in _group_by_publisher(reports)[-1][1]]
        self.assertEqual(other_titles, ["X", "Y"])

    def test_html_groups_follow_priority_list_even_if_input_is_shuffled(self) -> None:
        reports = [
            ComicReport(Comic(title="K", publisher="KADOKAWA", pubdate="2026-09-01")),
            ComicReport(Comic(title="H", publisher="芳文社", pubdate="2026-09-01")),
            ComicReport(Comic(title="S", publisher="集英社", pubdate="2026-09-20")),
            ComicReport(Comic(title="O", publisher="小学館", pubdate="2026-09-01")),
        ]
        labels = [label for label, _ in _group_by_publisher(reports)]
        self.assertEqual(labels, ["集英社", "小学館", "KADOKAWA", "芳文社"])

    def test_same_publisher_by_date(self) -> None:
        earlier = publisher_sort_key("集英社", "2026.9.1", "Z")
        later = publisher_sort_key("集英社", "2026.9.20", "A")
        self.assertLess(earlier, later)

    def test_kadokawa_alias(self) -> None:
        self.assertEqual(canonical_publisher("ＫＡＤＯＫＡＷＡ / 角川"), "KADOKAWA")


class ComicSearchTests(unittest.TestCase):
    def test_search_query_strips_volume(self) -> None:
        comic = Comic(title="夜は猫といっしょ(1)")
        self.assertEqual(comic.search_query, "夜は猫といっしょ")


class HtmlSearchTests(unittest.TestCase):
    def test_search_controls_and_card_index(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="初凪ヒメリウム 1",
                    author="鹿冬",
                    publisher="芳文社",
                    pubdate="2026-08-27",
                    isbn="978-4-8322-0000-1",
                )
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(reports, path, "test")
            html = path.read_text(encoding="utf-8")
        self.assertIn(f'<link rel="icon" type="image/png" href="icon-3.png?v={ASSET_VER}">', html)
        self.assertIn(f'data-build="{ASSET_VER}"', html)
        self.assertIn(
            'content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"',
            html,
        )
        self.assertIn("@media (max-width: 768px)", html)
        self.assertIn('id="comic-search"', html)
        self.assertIn('id="fav-list-btn"', html)
        self.assertIn("お気に入り一覧", html)
        self.assertIn('get("fav") === "1"', html)
        self.assertIn('params.get("cal") === "1"', html)
        self.assertIn('params.get("q")', html)
        self.assertIn("ichikomi-favorites-v1", html)
        self.assertIn('class="fav-btn"', html)
        self.assertIn('id="search-suggest"', html)
        self.assertIn('id="search-go"', html)
        self.assertIn("search-icon.png", html)
        self.assertIn('class="ext mercari"', html)
        self.assertIn("jp.mercari.com/search", html)
        self.assertIn("afid=7668762322", html)
        self.assertIn(">mercari</a>", html)
        self.assertNotIn("buy-amazon.png", html)
        self.assertNotIn("buy-rakuten.png", html)
        self.assertNotIn("buy-mercari.png", html)
        self.assertIn("min-height: 44px", html)
        self.assertIn("#1877f2", html)
        self.assertIn("#c41e3a", html)
        self.assertIn("#4ba7ee", html)
        self.assertIn("grid-template-columns: 1fr 1fr 1fr", html)
        self.assertNotIn('class="ext-stack"', html)
        self.assertIn('class="date-row"', html)
        self.assertIn("ichikomi-list-pos-v1", html)
        self.assertIn("position: absolute", html)
        self.assertIn("updateSuggest", html)
        self.assertIn("1件中 1件表示", html)
        self.assertIn("【イチコミ特典＋の説明】", html)
        self.assertIn('class="intro-heading"', html)
        self.assertIn("第1巻の各書店の特典情報", html)
        self.assertNotIn("【第1巻】", html)
        self.assertIn("過去に掲載した月は残し、現在月から前後３カ月も合わせて掲載しております", html)
        self.assertLess(
            html.find("過去に掲載した月は残し、現在月から前後３カ月も合わせて掲載しております"),
            html.find("当サイトはアフィリエイト広告(PR)を利用しています。"),
        )
        self.assertIn("情報収集エラー", html)
        self.assertIn("検知できなかった店舗は『特典なし』", html)
        self.assertNotIn("『未確認』の表示", html)
        self.assertIn("アフィリエイト広告(PR)", html)
        self.assertNotIn("イチコミ特典＋はアフィリエイト広告（Amazonアソシエイト", html)
        self.assertNotIn('class="affiliate-note"', html)
        self.assertIn("イチコミ特典＋｜新刊コミック第1巻 書店特典チェック", html)
        self.assertIn('alt="イチコミ特典＋ 新刊コミック第1巻 書店特典チェック"', html)
        self.assertIn('src="logo.png', html)
        self.assertIn('class="ext mercari"', html)
        self.assertIn("jp.mercari.com/search", html)
        self.assertIn("afid=7668762322", html)
        self.assertIn(">mercari</a>", html)
        self.assertIn("#1877f2", html)
        self.assertIn("#c41e3a", html)
        self.assertIn("#4ba7ee", html)
        self.assertIn("grid-template-columns: 1fr 1fr 1fr", html)
        self.assertNotIn('class="ext-stack"', html)
        self.assertIn('class="intro-notes"', html)
        self.assertIn("当サイトはアフィリエイト広告(PR)を利用しています。", html)
        self.assertIn("data-search=", html)
        self.assertIn("初凪ヒメリウム", html)
        self.assertIn("fold(s)", html)
        self.assertIn("0x30A1", html)
        self.assertIn('class="ad-container ad-header"', html)
        self.assertIn('class="ad-container ad-footer"', html)
        self.assertIn("px.a8.net", html)
        self.assertIn("px.a8.net/svt/ejp?a8mat=4BCDBO+UD4MQ+37DC+5ZMCH", html)
        self.assertIn("px.a8.net/svt/ejp?a8mat=4BCDBO+5DHWDU+4RNG+5ZU29", html)
        self.assertIn("px.a8.net/svt/ejp?a8mat=4BCL42+1U34XE+4Y6G+5ZEMP", html)
        self.assertIn("px.a8.net/svt/ejp?a8mat=4BCL42+5CB16A+41ZK+601S1", html)
        self.assertNotIn("px.a8.net/svt/ejp?a8mat=4BCDBO+5DHWDU+4RNG+61Z81", html)
        self.assertNotIn("px.a8.net/svt/ejp?a8mat=4BCDBO+3KMEQ+1892+6BMG1", html)
        self.assertLess(html.find("ad-header"), html.find("<main"))
        self.assertGreater(html.find('class="ad-container ad-footer"'), html.find("</main>"))
        self.assertLess(html.find('class="ad-container ad-footer"'), html.find("</body>"))
        self.assertIn('id="pager"', html)
        self.assertIn('id="pager-top"', html)
        self.assertIn('id="month-count"', html)
        self.assertIn("この月", html)
        self.assertIn("pager-prev", html)
        self.assertIn("pager-next", html)
        self.assertIn("PAGE_SIZE = 50", html)
        self.assertIn("currentPage = 1", html)
        self.assertNotIn("windowSize", html)
        self.assertIn('id="back-to-top"', html)
        self.assertIn("TOPに戻る", html)
        self.assertIn("position: fixed", html)
        self.assertIn("behavior: \"smooth\"", html)
        self.assertNotIn("TSUTAYA", html)
        self.assertNotIn('class="index-tabs"', html)
        self.assertNotIn("凡例", html)
        self.assertNotIn("特典一覧", html)
        self.assertIn('id="cal-btn"', html)
        self.assertIn('id="cal-modal"', html)
        self.assertIn("data-pubdate=", html)
        self.assertIn("ichikomi-list-pos-v1", html)
        self.assertLess(html.find("ad-header"), html.find('id="pager-top"'))
        self.assertLess(html.find('id="pager-top"'), html.find('id="month-count"'))
        self.assertLess(html.find('id="month-count"'), html.find("<main"))
        self.assertGreater(html.find('id="pager"'), html.find('class="ad-container ad-footer"'))
        self.assertGreater(html.find('class="ad-container ad-footer"'), html.find("</main>"))

    def test_unknown_store_status_shows_as_no(self) -> None:
        reports = [
            ComicReport(
                Comic(title="未確認作品 1", isbn="9784000000001"),
                checks=[
                    StoreCheck(
                        "animate",
                        "アニメイト",
                        STATUS_UNKNOWN,
                        "未取得",
                        "https://example.com/a",
                    )
                ],
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            html = (Path(tmp) / "out.html")
            write_html(reports, html, "test")
            text = html.read_text(encoding="utf-8")
        self.assertIn("class=\"badge no\"", text)
        self.assertIn("<span class='status'>特典なし</span>", text)
        self.assertNotIn("<span class='status'>未確認</span>", text)
        self.assertIn("📋 コピー", text)
        self.assertIn("</a><button type=\"button\" class=\"copy-title\"", text)
        self.assertIn("grid-template-columns: 92px minmax(0, 1fr) auto", text)
        self.assertIn("grid-template-columns: 1fr;", text)

    def test_rakuten_credit_and_lazy_cover(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="予約新刊 1",
                    author="作者",
                    publisher="集英社",
                    pubdate="2026-09-19",
                    cover_url="https://thumbnail.image.rakuten.co.jp/cover.jpg",
                    cover_source="rakuten",
                    source="rakuten",
                )
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(reports, path, "test")
            html = path.read_text(encoding="utf-8")
        self.assertIn("出典: 楽天ブックス", html)
        self.assertIn("Supported by Rakuten Developers", html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('id="comic-search"', html)
        self.assertNotIn("出典: openBD", html)
        self.assertNotIn('class="cover-link"', html)
        self.assertNotIn("<a class=\"cover", html)
        self.assertIn("<img src=", html)

    def test_on_kun_in_data_search(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="風と雲",
                    publisher="小学館",
                    pubdate="2026-09-01",
                    title_kana="カゼトクモ",
                )
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(reports, path, "test")
            html = path.read_text(encoding="utf-8")
        self.assertIn("ふう", html)
        self.assertIn("かぜ", html)
        self.assertIn("kazetokumo", html)
        self.assertIn("comic-card-0", html)
        self.assertIn("focus-flash", html)

    def test_month_tabs_and_independent_panels(self) -> None:
        sep = [
            ComicReport(
                Comic(title="九月の本 1", publisher="集英社", pubdate="2026-09-04"),
                period_year=2026,
                period_month=9,
            )
        ]
        oct_ = [
            ComicReport(
                Comic(title="十月の本 1", publisher="講談社", pubdate="2026-10-04"),
                period_year=2026,
                period_month=10,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(
                sep + oct_,
                path,
                "test",
                month_panels=[(2026, 9, sep), (2026, 10, oct_)],
            )
            html = path.read_text(encoding="utf-8")
        self.assertIn("2026年9月", html)
        self.assertIn("2026年10月", html)
        self.assertNotIn(">10月<", html)
        self.assertIn('class="month-tabs"', html)
        self.assertIn('data-month="2026-09"', html)
        self.assertIn('data-month="2026-10"', html)
        self.assertIn("九月の本", html)
        self.assertIn('data-pubdate="2026-09-04"', html)
        self.assertIn("十月の本", html)
        self.assertIn("switchMonth", html)
        self.assertIn("monthState", html)
        self.assertLess(html.find('id="comic-search"'), html.find('class="month-tabs"'))
        self.assertIn('class="site-top"', html)
        self.assertIn('data-month="2026-09" aria-selected="true"', html)
        self.assertNotIn("月タブで切り替えられます", html)
        self.assertNotIn("初期表示は", html)

    def test_wrong_month_pubdate_is_not_rendered_in_tab(self) -> None:
        reports = [
            ComicReport(
                Comic(title="八月の本 1", publisher="小学館", pubdate="2026-08-28"),
                period_year=2026,
                period_month=9,
            ),
            ComicReport(
                Comic(title="九月の本 1", publisher="集英社", pubdate="2026-09-10"),
                period_year=2026,
                period_month=9,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(
                reports,
                path,
                "test",
                month_panels=[(2026, 9, reports)],
            )
            html = path.read_text(encoding="utf-8")
        self.assertIn("九月の本 1", html)
        self.assertNotIn("八月の本 1", html)
        self.assertIn('data-month="2026-09"', html)
        self.assertIn('data-release-month="2026-09"', html)
        self.assertIn('data-total="1"', html)

    def test_month_tabs_always_include_year_and_open_on_current(self) -> None:
        panels = []
        for year, month in [
            (2026, 11),
            (2026, 12),
            (2027, 1),
            (2027, 2),
        ]:
            reports = [
                ComicReport(
                    Comic(title=f"{year}-{month} 1", publisher="集英社", pubdate=f"{year}-{month:02d}-04"),
                    period_year=year,
                    period_month=month,
                )
            ]
            panels.append((year, month, reports))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.html"
            write_html(
                [item for _, _, items in panels for item in items],
                path,
                "test",
                month_panels=panels,
                active_period=(2027, 1),
            )
            html = path.read_text(encoding="utf-8")
        self.assertIn(">2026年11月<", html)
        self.assertIn(">2026年12月<", html)
        self.assertIn(">2027年1月<", html)
        self.assertIn(">2027年2月<", html)
        self.assertNotIn("2026年11月、2026年12月、2027年1月、2027年2月", html)
        self.assertNotIn("初期表示は", html)
        self.assertIn('class="month-panel is-active" id="month-2027-01"', html)
        self.assertIn('class="month-tab is-active" role="tab" data-month="2027-01"', html)
        self.assertNotIn(">1月<", html)
        self.assertNotIn(">12月<", html)

    def test_kana_case_width_fold_matches(self) -> None:
        def fold(s: str) -> str:
            s = s.casefold()
            import unicodedata

            s = unicodedata.normalize("NFKC", s).lower()
            out = []
            for ch in s:
                code = ord(ch)
                out.append(chr(code - 0x60) if 0x30A1 <= code <= 0x30F6 else ch)
            return re.sub(r"[\s・/／\-−_.,.'\"「」『』()（）\[\]]+", "", "".join(out))

        haystack = fold("初凪ヒメリウム 1 鹿冬 芳文社")
        self.assertIn(fold("ひめりうむ"), haystack)
        self.assertIn(fold("ヒメリウム"), haystack)
        self.assertIn(fold("ＨＩＭＥ"), fold("hime"))
        self.assertIn(fold("芳文社"), haystack)


if __name__ == "__main__":
    unittest.main()
