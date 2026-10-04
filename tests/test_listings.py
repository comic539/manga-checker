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
        self.assertIn("特典", items[0].extra)
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


class PrivilegeListParseTests(unittest.TestCase):
    def test_animate_cards(self) -> None:
        from manga_checker.privilege_index import parse_animate_privilege_list

        html = """
        <div class="prize_list"><ul><li>
          <div class="prize_list_detail">
            <p class="release">2026/10/01 発売</p>
            <p class="release">【コミック】アンデッドさんの不器用な青春 1</p>
            <p class="release">アニメイト特典</p>
            <h3><a href="/products/privilege_detail.php?id=1">イラストカード(B7サイズ)</a></h3>
          </div>
        </li></ul></div>
        """
        items = parse_animate_privilege_list(html)
        self.assertEqual(len(items), 1)
        self.assertIn("アンデッドさん", items[0].title)
        self.assertIn("privilege_detail.php", items[0].url)
        self.assertIn("イラストカード", items[0].extra)

    def test_melon_cards(self) -> None:
        from manga_checker.privilege_index import parse_melon_privilege_list

        html = """
        <div class="item-list"><ul>
          <li class="product_3810284">
            <div class="privilege_title">描き下ろし箔押しポスター</div>
            <a href="/detail/detail.php?product_id=3810284" title="To LOVEる -とらぶる- 短編集 Parade"></a>
            <p class="item-ttl product_title">To LOVEる -とらぶる- 短編集 Parade</p>
          </li>
        </ul></div>
        """
        items = parse_melon_privilege_list(html)
        self.assertEqual(len(items), 1)
        self.assertIn("To LOVEる", items[0].title)
        self.assertIn("product_id=3810284", items[0].url)
        self.assertIn("ポスター", items[0].extra)

    def test_gamers_cards(self) -> None:
        from manga_checker.privilege_index import parse_gamers_privilege_list

        html = """
        <ul>
          <li class="list_product">
            <h3><span class="tokuten_ttl_icon_list">特典</span>
              <a href="/products/privilege_detail.php?id=1" class="a_line">描き下ろしブロマイド</a></h3>
            <a class="txt_wrap" href="/products/privilege_detail.php?id=1">【コミック】あたらよのほし</a>
          </li>
        </ul>
        """
        items = parse_gamers_privilege_list(html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "あたらよのほし")
        self.assertIn("privilege_detail.php", items[0].url)
        self.assertIn("ブロマイド", items[0].extra)

    def test_toranoana_cards(self) -> None:
        from manga_checker.privilege_index import parse_toranoana_calendar

        html = """
        <li class="product-list-item catalog-item-card">
          <h3 class="product-list-title">
            <a href="/tora/ec/item/200012826267/">アンデッドさんの不器用な青春 1</a>
          </h3>
        </li>
        """
        items = parse_toranoana_calendar(html)
        self.assertEqual(len(items), 1)
        self.assertIn("アンデッドさん", items[0].title)
        self.assertIn("/tora/ec/item/200012826267/", items[0].url)

    def test_toranoana_benefit_json(self) -> None:
        from manga_checker.privilege_index import parse_toranoana_benefit_json

        raw = """toraBenefitScheduleCallback({
          "info": {"prev": true, "next": false},
          "list": [
            {
              "benefitId": "1",
              "titleId": "200012823053",
              "date": 8,
              "title": "解除師カンナの魔術録 1",
              "publisher": "講談社",
              "benefit": "【特典】共通描き下ろしイラストカード"
            }
          ]
        });"""
        items = parse_toranoana_benefit_json(raw)
        self.assertEqual(len(items), 1)
        self.assertIn("解除師カンナ", items[0].title)
        self.assertIn("/tora/ec/item/200012823053/", items[0].url)
        self.assertIn("イラストカード", items[0].extra)

    def test_catalog_issue_dates_are_unique_yyyymmdd(self) -> None:
        from manga_checker.privilege_index import catalog_issue_dates

        comics = [
            Comic(title="A", pubdate="2026年10月15日"),
            Comic(title="B", pubdate="2026/10/15"),
            Comic(title="C", pubdate="20261016"),
            Comic(title="D", pubdate=""),
        ]
        self.assertEqual(catalog_issue_dates(comics), ["20261015", "20261016"])
        self.assertEqual(
            catalog_issue_dates(comics, months=[(2026, 10)]),
            ["20261015", "20261016"],
        )
