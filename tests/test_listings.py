import unittest

from manga_checker.bulk_listings import BulkListingIndex, ListingItem
from manga_checker.comiczin import calendar_days_from_html, parse_zin_listing
from manga_checker.comirano import parse_comirano_listing
from manga_checker.models import Comic
from manga_checker.privilege import STATUS_NO, STATUS_YES


class ComiczinParseTests(unittest.TestCase):
    def test_parses_calendar_listing_cards(self) -> None:
        html = """
        <a href="/products/list.php?name=2026/10/2">2</a>
        <a href="/products/list.php?name=2026/10/05">5</a>
        <ul>
          <li class="vb_space_5px">
            <div class="list_item">
              <a href="/products/detail.php?product_id=10043611" class="img_area">
                <img src="/upload/save_image/9784088852621_s.jpg" alt="ルノリータ 第1巻" />
              </a>
              <a href="/products/detail.php?product_id=10043611" class="title_area">ルノリータ 第1巻</a>
            </div>
          </li>
          <li>
            <a href="/products/detail.php?product_id=10043617">
              To Loveる―とらぶる― 短編集 Parade
            </a>
          </li>
        </ul>
        """
        items = parse_zin_listing(html)
        urls = {item.url for item in items}
        self.assertIn(
            "https://shop.comiczin.jp/products/detail.php?product_id=10043611", urls
        )
        self.assertTrue(any(item.title == "ルノリータ 第1巻" for item in items))
        self.assertTrue(any("短編集 Parade" in item.title for item in items))
        days = calendar_days_from_html(html, 2026, 10)
        self.assertEqual(days, [(2026, 10, 2), (2026, 10, 5)])


class ComiranoParseTests(unittest.TestCase):
    def test_parses_article_permalinks(self) -> None:
        html = """
        <article class="omc-blog-one">
          <h3 class="omc-blog-one-cat"><a href="https://comirano.info/?cat=1071">カード</a></h3>
          <h2 class="omc-blog-one-heading">
            <a href="https://comirano.info/アンデッドさんの不器用な青春（1）/">アンデッドさんの不器用な青春（1）</a>
          </h2>
          <p>特典：A6ペーパー</p>
        </article>
        <article>
          <h2><a href="/category/comic/">一覧</a></h2>
        </article>
        """
        items = parse_comirano_listing(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "アンデッドさんの不器用な青春(1)")
        self.assertIn("comirano.info", items[0].url)
        self.assertNotIn("/category/", items[0].url)
        self.assertNotIn("?cat=", items[0].url)


class BulkListingLookupTests(unittest.TestCase):
    def test_matches_title_and_sets_product_url(self) -> None:
        index = BulkListingIndex()
        index.loaded = True
        index.items["comiczin"] = [
            ListingItem(
                title="ルノリータ 第1巻",
                url="https://shop.comiczin.jp/products/detail.php?product_id=10043611",
            )
        ]
        index.items["comirano"] = [
            ListingItem(
                title="アンデッドさんの不器用な青春（1）",
                url="https://comirano.info/アンデッドさんの不器用な青春（1）/",
            )
        ]
        zin = index.check(
            "comiczin",
            "COMIC ZIN",
            Comic(title="ルノリータ 1"),
            "https://shop.comiczin.jp/products/list.php",
        )
        self.assertEqual(zin.status, STATUS_YES)
        self.assertIn("product_id=10043611", zin.url)
        missing = index.check(
            "comiczin",
            "COMIC ZIN",
            Comic(title="存在しない作品 1"),
            "https://shop.comiczin.jp/products/list.php",
        )
        self.assertEqual(missing.status, STATUS_NO)
        comirano = index.check(
            "comirano",
            "こみらの！",
            Comic(title="アンデッドさんの不器用な青春(1)"),
            "https://comirano.info/category/comic/",
        )
        self.assertEqual(comirano.status, STATUS_YES)
        self.assertIn("アンデッドさん", comirano.url)
