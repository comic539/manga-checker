import os
import unittest
from unittest.mock import patch

from manga_checker import config
from manga_checker.catalog import fetch_month_volume_ones
from manga_checker.models import Comic
from manga_checker.rakuten_books import (
    BOOKS_BOOK_SEARCH,
    COMIC_GENRE_ID,
    RAKUTEN_HITS_PER_PAGE,
    _paginate_month,
    _paginate_window,
    _search_params,
    fetch_rakuten_volume_ones,
    fetch_rakuten_volume_ones_by_month,
    normalize_sales_date,
    parse_rakuten_item,
    rakuten_configured,
    sales_in_month,
)
from manga_checker.volume import is_volume_one


class RakutenParseTests(unittest.TestCase):
    def test_parse_item_and_cover(self) -> None:
        comic = parse_rakuten_item(
            {
                "title": "初凪ヒメリウム (1)",
                "author": "鹿冬",
                "publisherName": "芳文社",
                "salesDate": "2026年09月27日",
                "isbn": "978-4-8322-9748-7",
                "seriesName": "まんがタイムKR",
                "titleKana": "ハツナギヒメリウム",
                "largeImageUrl": "https://thumbnail.image.rakuten.co.jp/cover.jpg",
                "itemUrl": "https://books.rakuten.co.jp/rb/example/",
            }
        )
        assert comic is not None
        self.assertEqual(comic.publisher, "芳文社")
        self.assertEqual(comic.isbn, "9784832297487")
        self.assertEqual(comic.pubdate, "2026-09-27")
        self.assertEqual(comic.cover_source, "rakuten")
        self.assertEqual(comic.title_kana, "ハツナギヒメリウム")
        self.assertTrue(comic.cover_url.startswith("https://thumbnail.image.rakuten.co.jp"))
        self.assertTrue(is_volume_one(comic.title, comic.volume))

    def test_skips_noimage(self) -> None:
        comic = parse_rakuten_item(
            {
                "title": "テスト (1)",
                "publisherName": "集英社",
                "salesDate": "2026年09月頃",
                "largeImageUrl": "https://thumbnail.image.rakuten.co.jp/@0_mall/book/noimage.jpg",
            }
        )
        assert comic is not None
        self.assertEqual(comic.cover_url, "")
        self.assertEqual(comic.cover_source, "")
        self.assertTrue(sales_in_month("2026年09月頃", 2026, 9))
        self.assertEqual(normalize_sales_date("2026年09月頃"), "2026-09")

    def test_reservation_month_match(self) -> None:
        self.assertTrue(sales_in_month("2026年9月5日", 2026, 9))
        self.assertFalse(sales_in_month("2026年08月01日", 2026, 9))

    def test_loose_sales_date_variants(self) -> None:
        for value in (
            "2026年09月04日頃",
            "2026年09月中旬",
            "2026年9月下旬",
            "2026年09月",
            "2026-09",
            "2026/09",
            "２０２６年０９月０４日頃",
        ):
            self.assertTrue(sales_in_month(value, 2026, 9), value)
        self.assertTrue(sales_in_month("", 2026, 9))
        self.assertTrue(sales_in_month("発売日未定", 2026, 9))

    def test_paginate_keeps_approx_sales_dates(self) -> None:
        items = [
            {
                "title": "頃表記 (1)",
                "publisherName": "集英社",
                "salesDate": "2026年09月04日頃",
                "isbn": "9784000000001",
            },
            {
                "title": "中旬表記 (1)",
                "publisherName": "小学館",
                "salesDate": "2026年09月中旬",
                "isbn": "9784000000002",
            },
            {
                "title": "別月 (1)",
                "publisherName": "講談社",
                "salesDate": "2026年08月01日",
                "isbn": "9784000000003",
            },
        ]

        def fake_request(_session, extra):
            return {"pageCount": 1, "Items": items}

        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            found = _paginate_month(
                None, 2026, 9, 0, extra={"booksGenreId": "001001"}, max_pages=1
            )
        titles = [c.title for c in found]
        self.assertIn("頃表記 (1)", titles)
        self.assertIn("中旬表記 (1)", titles)
        self.assertNotIn("別月 (1)", titles)


class RakutenConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        config._CACHE = None
        os.environ.pop("MANGA_CHECKER_RAKUTEN_APPLICATION_ID", None)
        os.environ.pop("MANGA_CHECKER_RAKUTEN_ACCESS_KEY", None)

    def test_placeholder_is_unconfigured(self) -> None:
        config._CACHE = {
            "rakuten_application_id": "YOUR_APPLICATION_ID",
            "rakuten_affiliate_id": "",
            "amazon_tag": "",
            "rakuten_access_key": "",
        }
        self.assertEqual(config.rakuten_application_id(), "")
        self.assertFalse(rakuten_configured())

    def test_env_application_id(self) -> None:
        config._CACHE = None
        os.environ["MANGA_CHECKER_RAKUTEN_APPLICATION_ID"] = "app-123"
        with patch("manga_checker.config.Path.is_file", return_value=False):
            self.assertEqual(config.rakuten_application_id(), "app-123")

    def test_access_key_from_cache_and_query_params(self) -> None:
        config._CACHE = {
            "rakuten_application_id": "app-123",
            "rakuten_access_key": "secret-key",
            "rakuten_affiliate_id": "aff-1",
            "amazon_tag": "",
        }
        self.assertTrue(rakuten_configured())
        self.assertEqual(config.rakuten_access_key(), "secret-key")
        self.assertIn("openapi.rakuten.co.jp", BOOKS_BOOK_SEARCH)
        params = _search_params({"booksGenreId": "001001"})
        self.assertEqual(params["applicationId"], "app-123")
        self.assertEqual(params["accessKey"], "secret-key")
        self.assertEqual(params["affiliateId"], "aff-1")


class CatalogFallbackTests(unittest.TestCase):
    def test_falls_back_to_ndl_when_unconfigured(self) -> None:
        ndl_comics = [
            Comic(title="後発 (1)", publisher="竹書房", pubdate="2026-09-01"),
            Comic(title="ジャンプ新刊 (1)", publisher="集英社", pubdate="2026-09-04"),
        ]
        with patch("manga_checker.catalog.rakuten_configured", return_value=False), patch(
            "manga_checker.catalog.fetch_ndl_comics", return_value=ndl_comics
        ), patch("manga_checker.catalog.enrich_with_openbd", side_effect=lambda comics, session=None: comics), patch(
            "manga_checker.catalog.fill_missing_pubdates", side_effect=lambda comics, session=None: comics
        ):
            result = fetch_month_volume_ones(year=2026, month=9)
        self.assertEqual([c.publisher for c in result], ["集英社", "竹書房"])


class PaginateLimitTests(unittest.TestCase):
    def test_continues_through_future_month_pages(self) -> None:
        calls = {"n": 0}

        def fake_request(_session, extra):
            calls["n"] += 1
            page = int(extra["page"])
            if page <= 2:
                sales = "2026年10月01日"
                title = f"未来 {page} (1)"
            elif page == 3:
                sales = "2026年09月10日"
                title = "九月の新刊 (1)"
            else:
                sales = "2026年08月01日"
                title = f"八月 {page} (1)"
            return {
                "pageCount": 10,
                "Items": [
                    {
                        "title": title,
                        "publisherName": "集英社",
                        "salesDate": sales,
                        "isbn": f"978400000000{page}",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            found = _paginate_month(
                None,
                2026,
                9,
                0,
                extra={"booksGenreId": "001001"},
                max_pages=10,
            )
        titles = [c.title for c in found]
        self.assertIn("九月の新刊 (1)", titles)
        self.assertNotIn("未来 1 (1)", titles)
        self.assertEqual(calls["n"], 4)

    def test_window_collects_four_months_in_one_scan(self) -> None:
        calls = {"n": 0}

        def fake_request(_session, extra):
            calls["n"] += 1
            page = int(extra["page"])
            sales = {
                1: "2026年12月01日",
                2: "2026年11月01日",
                3: "2026年10月01日",
                4: "2026年09月10日",
                5: "2026年08月01日",
            }[page]
            title = {
                1: "十二月の本 (1)",
                2: "十一月の本 (1)",
                3: "十月の本 (1)",
                4: "九月の本 (1)",
                5: "八月の本 (1)",
            }[page]
            return {
                "pageCount": 10,
                "Items": [
                    {
                        "title": title,
                        "publisherName": "集英社",
                        "salesDate": sales,
                        "isbn": f"978400000000{page}",
                    }
                ],
            }

        months = [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]
        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            buckets, reached_older, hit_cap, reached_past, oldest = _paginate_window(
                None,
                months,
                0,
                extra={"booksGenreId": "001001"},
                max_pages=10,
            )
        self.assertEqual([c.title for c in buckets[(2026, 12)]], ["十二月の本 (1)"])
        self.assertEqual([c.title for c in buckets[(2026, 11)]], ["十一月の本 (1)"])
        self.assertEqual([c.title for c in buckets[(2026, 10)]], ["十月の本 (1)"])
        self.assertEqual([c.title for c in buckets[(2026, 9)]], ["九月の本 (1)"])
        self.assertEqual(calls["n"], 5)
        self.assertTrue(reached_older)
        self.assertFalse(hit_cap)
        self.assertIn((2026, 9), reached_past)
        self.assertEqual(oldest.isoformat(), "2026-08-01")

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            calls["n"] = 0
            result = fetch_rakuten_volume_ones_by_month(months, session=None, delay_sec=0)
        self.assertGreaterEqual(calls["n"], 4)
        self.assertTrue(any(c.title == "十月の本 (1)" for c in result[(2026, 10)]))
        self.assertTrue(any(c.title == "九月の本 (1)" for c in result[(2026, 9)]))
        self.assertFalse(any(c.title == "八月の本 (1)" for c in result[(2026, 9)]))

    def test_stops_immediately_when_first_item_is_before_target_month(self) -> None:
        calls = {"n": 0}

        def fake_request(_session, extra):
            calls["n"] += 1
            return {
                "pageCount": 100,
                "Items": [
                    {
                        "title": "古い本 (1)",
                        "publisherName": "集英社",
                        "salesDate": "2015年04月01日",
                        "isbn": "9784000000001",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            found = _paginate_month(
                None, 2026, 9, 0, extra={"booksGenreId": "001001"}, max_pages=100
            )
        self.assertEqual(found, [])
        self.assertEqual(calls["n"], 1)

    def test_empty_page_does_not_abort_scan(self) -> None:
        def fake_request(_session, extra):
            page = int(extra["page"])
            if page == 2:
                return {"pageCount": 4, "Items": []}
            sales = "2026年09月10日" if page != 4 else "2026年08月01日"
            title = "対象 (1)" if page != 4 else "過去 (1)"
            return {
                "pageCount": 4,
                "Items": [
                    {
                        "title": title,
                        "publisherName": "小学館",
                        "salesDate": sales,
                        "isbn": f"978400000000{page}",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            found = _paginate_month(
                None,
                2026,
                9,
                0,
                extra={"booksGenreId": "001001"},
                max_pages=10,
            )
        self.assertTrue(any(c.title == "対象 (1)" for c in found))

    def test_paginate_keeps_going_past_api_page_size(self) -> None:
        def fake_request(_session, extra):
            page = int(extra["page"])
            items = [
                {
                    "title": f"作品{page}-{i} (1)",
                    "publisherName": "集英社",
                    "salesDate": "2026年09月10日",
                    "isbn": f"97840{page:02d}{i:05d}",
                }
                for i in range(RAKUTEN_HITS_PER_PAGE)
            ]
            return {"pageCount": 3, "Items": items}

        with patch("manga_checker.rakuten_books._request", side_effect=fake_request):
            found = _paginate_month(
                None, 2026, 9, 0, extra={"booksGenreId": "001001"}, max_pages=10
            )
        self.assertGreater(len(found), RAKUTEN_HITS_PER_PAGE)
        self.assertEqual(len(found), RAKUTEN_HITS_PER_PAGE * 3)

    def test_genre_scan_has_no_title_keyword(self) -> None:
        extras: list[dict[str, str]] = []

        def fake_request(_session, extra):
            extras.append(dict(extra))
            return {
                "pageCount": 1,
                "Items": [
                    {
                        "title": "架空の新刊 (1)",
                        "publisherName": "架空書房",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000007",
                    },
                    {
                        "title": "ヒトナー 1",
                        "publisherName": "集英社",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000008",
                    },
                    {
                        "title": "TOブックス新刊 (1)",
                        "publisherName": "TOブックス",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000006",
                    },
                    {
                        "title": "11巻は除外 (11)",
                        "publisherName": "集英社",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000005",
                    },
                    {
                        "title": "KADOKAWA新刊 (1)",
                        "publisherName": "KADOKAWA",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000004",
                    },
                    {
                        "title": "小学館新刊 1巻",
                        "publisherName": "小学館",
                        "salesDate": "2026年09月01日",
                        "isbn": "9784000000003",
                    },
                    {
                        "title": "講談社新刊 第1巻",
                        "publisherName": "講談社",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000002",
                    },
                    {
                        "title": "ジャンプ新刊 (1)",
                        "publisherName": "集英社",
                        "salesDate": "2026年09月10日",
                        "isbn": "9784000000001",
                    },
                ],
            }

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            result = fetch_rakuten_volume_ones(2026, 9, session=None, delay_sec=0)

        self.assertTrue(extras)
        self.assertTrue(all("title" not in extra for extra in extras))
        self.assertTrue(all(extra.get("booksGenreId") == COMIC_GENRE_ID for extra in extras))
        self.assertTrue(all("publisherName" not in extra for extra in extras))
        self.assertEqual(_search_params({"booksGenreId": COMIC_GENRE_ID})["sort"], "-releaseDate")
        self.assertEqual(_search_params({"booksGenreId": COMIC_GENRE_ID})["hits"], str(RAKUTEN_HITS_PER_PAGE))
        self.assertEqual(
            [c.publisher for c in result],
            ["集英社", "集英社", "講談社", "小学館", "KADOKAWA", "TOブックス", "架空書房"],
        )
        self.assertTrue(any(c.title == "ヒトナー 1" for c in result))
        self.assertFalse(any("(11)" in c.title for c in result))

    def test_does_not_overwrite_earlier_results(self) -> None:
        def fake_request(_session, extra):
            return {
                "pageCount": 1,
                "Items": [
                    {
                        "title": "ジャンプ新刊 (1)",
                        "publisherName": "集英社",
                        "salesDate": "2026年09月01日",
                        "isbn": "9784000000001",
                    },
                    {
                        "title": "TOブックス新刊 (1)",
                        "publisherName": "TOブックス",
                        "salesDate": "2026年09月01日",
                        "isbn": "9784000000002",
                    },
                ],
            }

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            result = fetch_rakuten_volume_ones(2026, 9, session=None, delay_sec=0)
        publishers = [c.publisher for c in result]
        self.assertEqual(publishers, ["集英社", "TOブックス"])

    def test_past_month_uses_instock_scan_when_genre_hits_page_cap(self) -> None:
        extras: list[dict[str, str]] = []

        def fake_request(_session, extra):
            extras.append(dict(extra))
            if extra.get("availability") == "1":
                page = int(extra["page"])
                if page == 1:
                    sales, title = "2026年06月10日", "六月の本 (1)"
                else:
                    sales, title = "2026年05月01日", "五月の本 (1)"
                return {
                    "pageCount": 2,
                    "Items": [
                        {
                            "title": title,
                            "publisherName": "集英社",
                            "salesDate": sales,
                            "isbn": f"97840{page:08d}",
                        }
                    ],
                }
            page = int(extra["page"])
            return {
                "pageCount": 100,
                "Items": [
                    {
                        "title": f"予約 {page} (1)",
                        "publisherName": "集英社",
                        "salesDate": "3099年01月01日",
                        "isbn": f"97841{page:08d}",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            result = fetch_rakuten_volume_ones_by_month(
                [(2026, 6)], session=None, delay_sec=0
            )
        self.assertFalse(any(extra.get("publisherName") for extra in extras))
        self.assertTrue(any(extra.get("availability") == "1" for extra in extras))
        self.assertTrue(any("六月の本" in c.title for c in result[(2026, 6)]))
        self.assertFalse(any("予約" in c.title for c in result[(2026, 6)]))
        self.assertFalse(any("五月の本" in c.title for c in result[(2026, 6)]))
        genre_pages = [
            extra
            for extra in extras
            if extra.get("availability") != "1" and extra.get("booksGenreId") == COMIC_GENRE_ID
        ]
        self.assertEqual(len(genre_pages), 100)

    def test_partial_past_month_still_triggers_instock_scan(self) -> None:
        extras: list[dict[str, str]] = []

        def fake_request(_session, extra):
            extras.append(dict(extra))
            if extra.get("availability") == "1":
                page = int(extra["page"])
                sales = "2026年08月01日" if page == 1 else "2026年05月01日"
                title = "八月月初 (1)" if page == 1 else "五月の本 (1)"
                return {
                    "pageCount": 2,
                    "Items": [
                        {
                            "title": title,
                            "publisherName": "集英社",
                            "salesDate": sales,
                            "isbn": f"97842{page:08d}",
                        }
                    ],
                }
            page = int(extra["page"])
            return {
                "pageCount": 100,
                "Items": [
                    {
                        "title": f"八月末 {page} (1)",
                        "publisherName": "集英社",
                        "salesDate": "2026年08月31日",
                        "isbn": f"97843{page:08d}",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            result = fetch_rakuten_volume_ones_by_month(
                [(2026, 6), (2026, 7), (2026, 8)], session=None, delay_sec=0
            )
        self.assertTrue(any(extra.get("availability") == "1" for extra in extras))
        self.assertTrue(any("八月末" in c.title for c in result[(2026, 8)]))
        self.assertTrue(any("八月月初" in c.title for c in result[(2026, 8)]))
        self.assertFalse(any(extra.get("publisherName") for extra in extras))

    def test_page_cap_before_month_start_splits_by_publisher(self) -> None:
        extras: list[dict[str, str]] = []

        def fake_request(_session, extra):
            extras.append(dict(extra))
            page = int(extra["page"])
            publisher = extra.get("publisherName") or "集英社"
            if extra.get("publisherName"):
                if page == 1:
                    sales, title = "2026年09月09日", "九月九日 (1)"
                elif page == 2:
                    sales, title = "2026年09月01日", f"九月一日 {publisher} (1)"
                else:
                    sales, title = "2026年08月01日", "八月の本 (1)"
                return {
                    "pageCount": 3,
                    "Items": [
                        {
                            "title": title,
                            "publisherName": publisher,
                            "salesDate": sales,
                            "isbn": f"97845{page:04d}{len(publisher):04d}",
                        }
                    ],
                }
            if extra.get("availability") == "1":
                return {
                    "pageCount": 100,
                    "Items": [
                        {
                            "title": f"在庫九月九日 {page} (1)",
                            "publisherName": "集英社",
                            "salesDate": "2026年09月09日",
                            "isbn": f"97846{page:08d}",
                        }
                    ],
                }
            return {
                "pageCount": 100,
                "Items": [
                    {
                        "title": f"九月九日 {page} (1)",
                        "publisherName": "集英社",
                        "salesDate": "2026年09月09日",
                        "isbn": f"97847{page:08d}",
                    }
                ],
            }

        with patch("manga_checker.rakuten_books.rakuten_configured", return_value=True), patch(
            "manga_checker.rakuten_books._request", side_effect=fake_request
        ):
            result = fetch_rakuten_volume_ones_by_month(
                [(2026, 9)], session=None, delay_sec=0
            )
        self.assertTrue(any(extra.get("publisherName") for extra in extras))
        titles = [c.title for c in result[(2026, 9)]]
        self.assertTrue(any("九月一日" in title for title in titles))
        self.assertTrue(any("九月九日" in title for title in titles))
        self.assertGreater(len(result[(2026, 9)]), 37)
        self.assertFalse(any("八月の本" in title for title in titles))


if __name__ == "__main__":
    unittest.main()

