import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from manga_checker.models import Comic
from manga_checker.privilege import STATUS_NO, STATUS_YES
from manga_checker.stores import STORES, _fetch_animate, _fetch_melonbooks, _fetch_toranoana


class StoreListTests(unittest.TestCase):
    def test_required_stores_are_registered(self) -> None:
        names = [store.name for store in STORES]
        for required in (
            "アニメイト",
            "メロンブックス",
            "ゲーマーズ",
            "とらのあな",
            "喜久屋書店",
            "紀伊國屋書店",
            "くまざわ書店",
        ):
            self.assertIn(required, names)
        self.assertNotIn("TSUTAYA", names)
        self.assertNotIn("tsutaya", [store.store_id for store in STORES])

    def test_animate_privilege_index_is_privilege_list(self) -> None:
        animate = next(store for store in STORES if store.store_id == "animate")
        self.assertIn("privilege_list.php", animate.privilege_index_url)
        self.assertNotIn("/special/privilege", animate.privilege_index_url)

    def test_search_urls_point_to_catalogs(self) -> None:
        comic = Comic(title="初凪ヒメリウム", isbn="9784000000000")
        by_id = {store.store_id: store.search_url(comic) for store in STORES}
        gamers = urlparse(by_id["gamers"])
        self.assertEqual(gamers.path, "/products/list.php")
        self.assertEqual(parse_qs(gamers.query).get("smt"), ["9784000000000"])
        kumazawa = urlparse(by_id["kumazawa"])
        self.assertEqual(kumazawa.netloc, "www.search.kumabook.com")
        self.assertEqual(kumazawa.path, "/kumazawa/html/products/list")
        self.assertEqual(parse_qs(kumazawa.query).get("mode"), ["books"])
        self.assertEqual(parse_qs(kumazawa.query).get("name"), ["9784000000000"])
        self.assertNotIn("comic_tokuten", by_id["kumazawa"])
        animate = urlparse(by_id["animate"])
        self.assertEqual(parse_qs(animate.query).get("smt"), ["9784000000000"])
        melon = urlparse(by_id["melonbooks"])
        self.assertEqual(parse_qs(melon.query).get("name"), ["9784000000000"])
        self.assertEqual(parse_qs(melon.query).get("text_type"), ["all"])
        self.assertEqual(parse_qs(melon.query).get("category_id"), ["4"])
        comic_title = Comic(title="初凪ヒメリウム")
        melon_title = urlparse(
            {store.store_id: store.search_url(comic_title) for store in STORES}["melonbooks"]
        )
        self.assertEqual(parse_qs(melon_title.query).get("name"), ["初凪ヒメリウム"])
        self.assertEqual(parse_qs(melon_title.query).get("text_type"), ["title"])
        self.assertEqual(parse_qs(melon_title.query).get("category_id"), ["4"])

    def test_toranoana_query_uses_title_not_isbn(self) -> None:
        comic = Comic(title="ヒトナー 1", isbn="9784088852317")
        by_id = {store.store_id: store.search_url(comic) for store in STORES}
        from urllib.parse import unquote

        q = unquote(by_id["toranoana"])
        self.assertIn("searchWord=ヒトナー", q)
        self.assertNotIn("9784088852317", q)

    def test_toranoana_query_strips_wave_dash(self) -> None:
        comic = Comic(title="この世界の顔面偏差値が高すぎて目が痛い〜突然始まる異世界溺愛生活〜")
        by_id = {store.store_id: store.search_url(comic) for store in STORES}
        from urllib.parse import unquote

        q = unquote(by_id["toranoana"])
        self.assertNotIn("〜", q)
        self.assertNotIn("～", q)
        self.assertIn("目が痛い", q)


class DetailFetchTests(unittest.TestCase):
    def test_animate_uses_pd_url_and_tokuten(self) -> None:
        comic = Comic(title="初凪ヒメリウム 1", isbn="9784000000000")
        search_html = """
        <ul><li class="item"><a href="/pd/222/">初凪ヒメリウム 1</a></li></ul>
        """
        detail_html = """
        <div id="tokuten"><h2>特典について</h2><p>アニメイト特典</p></div>
        """

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = detail_html if "/pd/" in url else search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_animate(
                comic,
                "https://www.animate-onlineshop.jp/products/list.php?mode=search&smt=x",
                session,
            )
        self.assertEqual(check.status, STATUS_YES)
        self.assertEqual(check.url, "https://www.animate-onlineshop.jp/pd/222/")

    def test_melon_uses_detail_url_even_without_privilege(self) -> None:
        comic = Comic(title="初凪ヒメリウム 1", isbn="9784000000000")
        search_html = """
        <li class="item"><a href="/detail/detail.php?product_id=222">初凪ヒメリウム</a></li>
        """
        detail_html = "<h1>初凪ヒメリウム</h1><p>在庫あり</p>"

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = detail_html if "product_id=222" in url else search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_melonbooks(
                comic,
                "https://www.melonbooks.co.jp/search/search.php?name=x",
                session,
            )
        self.assertEqual(check.status, STATUS_NO)
        self.assertIn("search.php", check.url)
        self.assertNotIn("product_id=222", check.url)

    def test_melon_picks_matching_title_not_related_privilege_card(self) -> None:
        comic = Comic(title="息子の彼女 1")
        search_html = """
        <ul>
          <li class="item"><a href="/detail/detail.php?product_id=1">息子の彼女 1</a></li>
          <li class="item"><a href="/detail/detail.php?product_id=9">だれでも抱けるキミが好き 描き下ろしイラストカード</a></li>
        </ul>
        """
        detail_html = "<div class='item_detail'><h1>息子の彼女 1</h1><p>在庫あり</p></div>"

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = detail_html if "product_id=1" in url else search_html
            if "product_id=9" in url:
                resp.text = "<h1>だれでも抱けるキミが好き</h1><p>描き下ろしイラストカード</p>"
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_melonbooks(
                comic,
                "https://www.melonbooks.co.jp/search/search.php?name=x",
                session,
            )
        fetched = [call.args[0] for call in session.get.call_args_list]
        self.assertTrue(any("product_id=1" in url for url in fetched))
        self.assertFalse(any("product_id=9" in url for url in fetched))
        self.assertEqual(check.status, STATUS_NO)
        self.assertIn("search.php", check.url)

    def test_melon_isbn_search_is_tried_before_title(self) -> None:
        comic = Comic(title="ヒトナー 1", isbn="9784088852317")
        isbn_html = """
        <li class="item"><a href="/detail/detail.php?product_id=999">ひと夏limited</a></li>
        """
        title_html = """
        <li class="item"><a href="/detail/detail.php?product_id=222">ヒトナー</a></li>
        """
        detail_html = "<h1>ヒトナー</h1><p>在庫あり</p>"
        seen: list[str] = []

        def fake_get(url, timeout=25, **kwargs):
            seen.append(url)
            resp = MagicMock()
            resp.status_code = 200
            if "product_id=999" in url:
                resp.text = "<h1>ひと夏limited</h1>"
            elif "product_id=222" in url:
                resp.text = detail_html
            elif "9784088852317" in url:
                resp.text = isbn_html
            else:
                resp.text = title_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_melonbooks(
                comic,
                "https://www.melonbooks.co.jp/search/search.php?name=x",
                session,
            )
        self.assertTrue(any("9784088852317" in url for url in seen))
        isbn_pos = next(i for i, url in enumerate(seen) if "9784088852317" in url)
        title_pos = next(
            i for i, url in enumerate(seen) if "text_type=title" in url
        )
        self.assertLess(isbn_pos, title_pos)
        self.assertTrue(any("product_id=222" in url for url in seen))
        self.assertNotIn("product_id=999", check.url)

    def test_melon_skips_unrelated_first_hit(self) -> None:
        comic = Comic(title="ヒトナー 1")
        search_html = """
        <li class="item"><a href="/detail/detail.php?product_id=999">ひと夏limited</a></li>
        """

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_melonbooks(
                comic,
                "https://www.melonbooks.co.jp/search/search.php?name=x",
                session,
            )
        self.assertNotIn("product_id=999", check.url)
        self.assertIn("search.php", check.url)

    def test_melon_detects_privilege_on_detail(self) -> None:
        comic = Comic(title="初凪ヒメリウム 1")
        search_html = """
        <li class="item"><a href="/detail/detail.php?product_id=222">初凪ヒメリウム</a></li>
        """
        detail_html = '<div class="privilege"><h2>特典情報</h2><p>描き下ろしイラストカード</p></div>'

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = detail_html if "product_id=" in url else search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_melonbooks(
                comic,
                "https://www.melonbooks.co.jp/search/search.php?name=x",
                session,
            )
        self.assertEqual(check.status, STATUS_YES)
        self.assertIn("product_id=222", check.url)

    def test_animate_and_melon_fetch_even_without_fetch_flag(self) -> None:
        from manga_checker.official import OfficialIndex
        from manga_checker.stores import check_stores

        comic = Comic(title="初凪ヒメリウム 1")
        search_a = '<a href="/pd/222/">初凪ヒメリウム</a>'
        detail_a = '<div id="tokuten">アニメイト特典</div>'
        search_m = '<a href="/detail/detail.php?product_id=333">初凪ヒメリウム</a>'
        detail_m = "<div>特典情報 描き下ろしイラストカード</div>"

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "/pd/" in url:
                resp.text = detail_a
            elif "product_id=333" in url:
                resp.text = detail_m
            elif "animate" in url:
                resp.text = search_a
            elif "melonbooks" in url:
                resp.text = search_m
            else:
                resp.text = "<html></html>"
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        catalog = OfficialIndex()
        catalog.loaded = True
        with patch("manga_checker.stores.time.sleep"):
            checks = check_stores(comic, fetch=True, session=session, catalog=catalog)
        by_id = {c.store_id: c for c in checks}
        self.assertEqual(by_id["animate"].url, "https://www.animate-onlineshop.jp/pd/222/")
        self.assertEqual(by_id["animate"].status, STATUS_YES)
        self.assertIn("product_id=333", by_id["melonbooks"].url)
        self.assertEqual(by_id["melonbooks"].status, STATUS_YES)
        self.assertEqual(by_id["gamers"].status, STATUS_NO)
        self.assertEqual(by_id["kinokuniya"].status, STATUS_NO)

    def test_official_melon_yes_survives_without_fetch(self) -> None:
        from manga_checker.official import OfficialHit, OfficialIndex
        from manga_checker.privilege import STATUS_UNKNOWN
        from manga_checker.stores import check_stores

        comic = Comic(title="初凪ヒメリウム 1")
        catalog = OfficialIndex()
        catalog.loaded = True
        catalog.entries["melonbooks"] = [
            OfficialHit(
                "melonbooks",
                "『初凪ヒメリウム』メロンブックス限定特典",
                "https://www.melonbooks.co.jp/privilege/privilege.php",
                ["メロン特典"],
            )
        ]
        checks = check_stores(comic, fetch=False, delay_sec=0, catalog=catalog)
        by_id = {c.store_id: c for c in checks}
        self.assertEqual(by_id["melonbooks"].status, STATUS_YES)
        self.assertEqual(by_id["animate"].status, STATUS_UNKNOWN)

    def test_toranoana_uses_item_url_and_privilege(self) -> None:
        comic = Comic(title="ヒトナー 1", isbn="9784088852317")
        search_html = """
        <ul class="product-list-container">
          <li class="product-list-item">
            <h3 class="product-list-title">
              <a href="/tora/ec/item/200012817361/">ヒトナー 1</a>
            </h3>
          </li>
        </ul>
        """
        detail_html = """
        <section class="product-detail">
          <h1>ヒトナー 1</h1>
          <div class="privilege-info">とらのあな特典 描き下ろしイラストカード</div>
        </section>
        """
        seen: list[str] = []

        def fake_get(url, timeout=25, **kwargs):
            seen.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.text = detail_html if "/item/" in url else search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_toranoana(
                comic,
                "https://ecs.toranoana.jp/tora/ec/app/catalog/list/?searchWord=x",
                session,
            )
        self.assertTrue(any("searchWord=" in url and "9784088852317" not in url for url in seen))
        self.assertEqual(check.status, STATUS_YES)
        self.assertEqual(check.url, "https://ecs.toranoana.jp/tora/ec/item/200012817361/")

    def test_toranoana_skips_unrelated_first_hit(self) -> None:
        comic = Comic(title="ヒトナー 1")
        search_html = """
        <li class="product-list-item">
          <a href="/tora/ec/item/111/">ひと夏limited</a>
        </li>
        """

        def fake_get(url, timeout=25, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = search_html
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        with patch("manga_checker.stores.time.sleep"):
            check = _fetch_toranoana(
                comic,
                "https://ecs.toranoana.jp/tora/ec/app/catalog/list/?searchWord=x",
                session,
            )
        self.assertNotIn("/item/111", check.url)
        self.assertIn("searchWord=", check.url)

    def test_detail_page_matches_by_isbn_without_title(self) -> None:
        from manga_checker.stores import _detail_page_matches

        comic = Comic(title="別表記の作品 1", isbn="9784088852287")
        html = "<html><head><title>商品</title></head><body>ISBN 978-4-08-885228-7</body></html>"
        self.assertTrue(_detail_page_matches(comic, html))

    def test_isbn_search_uses_first_product_link(self) -> None:
        from manga_checker.animate import first_animate_detail_url
        from manga_checker.melon import first_melon_detail_url

        html_a = '<ul><li><a href="/pd/111/">別作品</a></li></ul>'
        url_a = first_animate_detail_url(
            html_a,
            "https://www.animate-onlineshop.jp/products/list.php",
            "初凪ヒメリウム",
            isbn="9784000000000",
        )
        self.assertEqual(url_a, "https://www.animate-onlineshop.jp/pd/111/")
        html_m = '<li><a href="/detail/detail.php?product_id=222">別作品</a></li>'
        url_m = first_melon_detail_url(
            html_m,
            "https://www.melonbooks.co.jp/search/search.php",
            "初凪ヒメリウム",
            isbn="9784000000000",
        )
        self.assertIn("product_id=222", url_m)


if __name__ == "__main__":
    unittest.main()


