import tempfile
import unittest
from pathlib import Path

from manga_checker.book_pages import SITE_BASE, book_href, isbn_slug, write_book_pages, write_sitemap
from manga_checker.models import Comic, ComicReport, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_YES
from manga_checker.report import write_html


class BookPageTests(unittest.TestCase):
    def test_isbn_slug_strips_hyphens(self) -> None:
        self.assertEqual(isbn_slug("978-4-08-885232-4"), "9784088852324")
        self.assertEqual(book_href("978-4-08-885232-4"), "books/9784088852324.html")
        self.assertEqual(book_href(""), "")

    def test_write_html_links_title_and_emits_pages(self) -> None:
        reports = [
            ComicReport(
                Comic(
                    title="初凪ヒメリウム 1",
                    author="鹿冬",
                    publisher="芳文社",
                    pubdate="2026-08-27",
                    isbn="978-4-8322-0000-1",
                ),
                checks=[
                    StoreCheck("animate", "アニメイト", STATUS_YES, "公式特典ページで確認", "https://example.com/a"),
                    StoreCheck("kikuya", "喜久屋書店", STATUS_NO, "なし", "https://example.com/k"),
                ],
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_path = root / "index.html"
            books = root / "books"
            sitemap = root / "sitemap.xml"
            write_html(
                reports,
                html_path,
                "test",
                book_dir=books,
                sitemap_path=sitemap,
                site_base=SITE_BASE,
            )
            listing = html_path.read_text(encoding="utf-8")
            self.assertIn('href="books/9784832200001.html"', listing)
            self.assertIn('class="title-link"', listing)
            self.assertIn('class="cover-link"', listing)
            self.assertIn('class="fav-btn"', listing)
            self.assertIn("data-isbn=", listing)
            page = books / "9784832200001.html"
            self.assertTrue(page.is_file())
            body = page.read_text(encoding="utf-8")
            self.assertIn("<title>『初凪ヒメリウム 1』店舗別購入特典・発売日情報まとめ｜イチコミ特典＋</title>", body)
            self.assertIn('og:site_name" content="イチコミ特典＋"', body)
            self.assertIn("一覧へ戻る", body)
            self.assertIn('href="../index.html"', body)
            self.assertIn('id="fav-list-btn"', body)
            self.assertIn("../index.html?fav=1", body)
            self.assertIn('class="site-top"', body)
            self.assertIn("position: sticky", body)
            self.assertIn("978-4-8322-0000-1", body)
            self.assertIn("アニメイト", body)
            self.assertIn("試し読み", body)
            self.assertIn('class="copy-title"', body)
            self.assertIn("clipboard.writeText", body)
            self.assertIn('class="fav-btn"', body)
            self.assertIn("ichikomi-favorites-v1", body)
            self.assertIn("購入", body)
            self.assertIn("#1877f2", body)
            self.assertIn("#c41e3a", body)
            self.assertIn("#4ba7ee", body)
            self.assertIn("min-height: 44px", body)
            self.assertNotIn("buy-amazon.png", body)
            self.assertIn("各書店の特典", body)
            self.assertNotIn("ad-book-leader", body)
            self.assertNotIn("ad-pr", body)
            self.assertNotIn(">PR<", body)
            self.assertIn("hero-ad", body)
            self.assertIn('class="hero-info"', body)
            self.assertIn("px.a8.net/svt/ejp?a8mat=4BCL42+1U34XE+4Y6G+5ZMCH", body)
            self.assertIn("px.a8.net/svt/ejp?a8mat=4BCDBN+FFHG6Q+4ADS+61JSH", body)
            self.assertNotIn("px.a8.net/svt/ejp?a8mat=4BCL42+1U34XE+4Y6G+5Z6WX", body)
            self.assertIn('width="300" height="250"', body)
            self.assertIn('class="hero-actions"', body)
            self.assertIn("cover meta", body)
            self.assertIn("actions actions", body)
            self.assertNotIn("cover meta actions", body)
            self.assertNotIn("max-width: 15.5rem", body)
            self.assertIn('id="cal-btn"', body)
            self.assertIn("../index.html?cal=1", body)
            self.assertNotIn('id="comic-search"', body)
            self.assertNotIn("../search-icon.png", body)
            self.assertNotIn('id="book-search"', body)
            self.assertIn("max-width: 760px", body)
            self.assertNotIn("max-width: 1180px", body)
            self.assertNotIn('class="ad-logo"', body)
            self.assertNotIn("px.a8.net/svt/ejp?a8mat=4BCDBO+3KMEQ+1892+6BMG1", body)
            self.assertNotIn("px.a8.net/svt/ejp?a8mat=4BCDBO+UD4MQ+37DC+5ZMCH", body)
            self.assertNotIn("detail-split", body)
            self.assertLess(body.find("hero-ad"), body.find("<h2>各書店の特典</h2>"))
            self.assertIn("flex-direction: row", body)
            self.assertNotIn("minmax(0, 1fr) 300px", body)
            self.assertLess(body.find("4BCDBN+FFHG6Q+4ADS+61JSH"), body.find("4BCL42+1U34XE+4Y6G+5ZMCH"))
            self.assertIn("公式特典ページで確認", body)
            self.assertNotIn("商品・検索ページ", body)
            self.assertNotIn("各書店の確認リンク", body)
            xml = sitemap.read_text(encoding="utf-8")
            self.assertIn(f"{SITE_BASE}/</loc>", xml)
            self.assertIn(f"{SITE_BASE}/books/9784832200001.html", xml)

    def test_no_isbn_has_plain_title(self) -> None:
        reports = [ComicReport(Comic(title="ISBNなし 1", publisher="芳文社"))]
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "out.html"
            write_html(reports, html_path, "test", book_dir=Path(tmp) / "books")
            text = html_path.read_text(encoding="utf-8")
            self.assertNotIn("class=\"title-link\"", text)
            self.assertEqual(list((Path(tmp) / "books").glob("*.html")), [])
