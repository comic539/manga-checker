import unittest
from datetime import date
from unittest.mock import MagicMock

from manga_checker.dates import (
    format_release_date,
    format_year_month,
    iter_month_offsets,
    iter_months,
    month_bounds,
    month_datetime_span,
    month_query_range,
    prefer_pubdate,
    year_month_from_pubdate,
)
from manga_checker.official import OfficialHit, OfficialIndex, _load_link_list, lookup_status
from manga_checker.privilege import STATUS_NO, STATUS_YES


class DateFormatTests(unittest.TestCase):
    def test_full_date_with_weekday(self) -> None:
        self.assertEqual(format_release_date("20260927"), "2026/09/27 (日)")
        self.assertEqual(format_release_date("2026-09-27"), "2026/09/27 (日)")

    def test_year_month_only(self) -> None:
        self.assertEqual(format_release_date("2026.9"), "2026/09")

    def test_iter_months_four_from_september(self) -> None:
        self.assertEqual(
            iter_months(2026, 9, 4),
            [(2026, 9), (2026, 10), (2026, 11), (2026, 12)],
        )

    def test_iter_months_wraps_year(self) -> None:
        self.assertEqual(
            iter_months(2026, 11, 4),
            [(2026, 11), (2026, 12), (2027, 1), (2027, 2)],
        )

    def test_format_year_month_has_no_zero_pad(self) -> None:
        self.assertEqual(format_year_month(2026, 6), "2026年6月")
        self.assertEqual(format_year_month(2027, 1), "2027年1月")

    def test_iter_month_offsets_seven_around_september(self) -> None:
        self.assertEqual(
            iter_month_offsets(2026, 9, today=date(2026, 9, 15)),
            [
                (2026, 6),
                (2026, 7),
                (2026, 8),
                (2026, 9),
                (2026, 10),
                (2026, 11),
                (2026, 12),
            ],
        )

    def test_iter_month_offsets_wraps_new_year(self) -> None:
        self.assertEqual(
            iter_month_offsets(2026, 11, today=date(2026, 11, 1)),
            [
                (2026, 8),
                (2026, 9),
                (2026, 10),
                (2026, 11),
                (2026, 12),
                (2027, 1),
                (2027, 2),
            ],
        )

    def test_iter_month_offsets_defaults_to_today(self) -> None:
        self.assertEqual(
            iter_month_offsets(today=date(2027, 1, 20)),
            [
                (2026, 10),
                (2026, 11),
                (2026, 12),
                (2027, 1),
                (2027, 2),
                (2027, 3),
                (2027, 4),
            ],
        )

    def test_month_bounds_are_calendar_first_and_last_day(self) -> None:
        self.assertEqual(month_bounds(2026, 8), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(month_bounds(2026, 2), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(month_query_range(2026, 9), ("2026-09-01", "2026-09-30"))
        start, end = month_datetime_span(2026, 6)
        self.assertEqual(start.isoformat(sep=" "), "2026-06-01 00:00:00")
        self.assertEqual(end.isoformat(sep=" "), "2026-06-30 23:59:59")

    def test_year_month_from_display_and_iso_dates(self) -> None:
        self.assertEqual(year_month_from_pubdate("2026-08-28"), (2026, 8))
        self.assertEqual(year_month_from_pubdate("2026/08/28 (金)"), (2026, 8))
        self.assertEqual(year_month_from_pubdate("2026.9"), (2026, 9))

    def test_prefer_full_openbd_date(self) -> None:
        self.assertEqual(prefer_pubdate("2026.9", "20260927"), "20260927")

    def test_openbd_onix_date_is_preferred(self) -> None:
        from manga_checker.openbd import _record_pubdates

        record = {
            "summary": {"pubdate": "2026.9"},
            "onix": {
                "PublishingDetail": {
                    "PublishingDate": {"PublishingDateRole": "01", "Date": "20260927"}
                }
            },
        }
        self.assertIn("20260927", _record_pubdates(record))
    def test_openbd_publication_date_alias(self) -> None:
        from manga_checker.retail_dates import collect_onix_pubdates

        record = {
            "onix": {
                "PublishingDetail": {
                    "PublicationDate": {"Date": "20260827"}
                }
            }
        }
        self.assertIn("20260827", collect_onix_pubdates(record))
        self.assertEqual(format_release_date("20260827"), "2026/08/27 (木)")

    def test_retail_html_release_date(self) -> None:
        from manga_checker.retail_dates import parse_retail_pubdate

        html = """
        <script type="application/ld+json">
        {"@type":"Book","datePublished":"2026-08-27"}
        </script>
        <th>発売日</th><td>2026年08月27日</td>
        """
        self.assertEqual(parse_retail_pubdate(html), "2026-08-27")


class KikuyaLookupTests(unittest.TestCase):
    def test_hit_uses_search_fallback_url(self) -> None:
        index = OfficialIndex()
        index.loaded = True
        index.entries["kikuya"] = [
            OfficialHit(
                "kikuya",
                "『初凪ヒメリウム』喜久屋書店限定特典",
                "https://kikuyashoten.myshopify.com/products/example",
                ["喜久屋特典"],
            )
        ]
        fallback = "https://kikuyashoten.myshopify.com/search?q=test"
        status, _, url = lookup_status(index, "kikuya", "初凪ヒメリウム", "", fallback)
        self.assertEqual(status, STATUS_YES)
        self.assertEqual(url, fallback)

    def test_miss_uses_inventory_search(self) -> None:
        index = OfficialIndex()
        index.loaded = True
        fallback = "https://kikuyashoten.myshopify.com/search?q=test"
        status, _, url = lookup_status(index, "kikuya", "存在しない作品", "", fallback)
        self.assertEqual(status, STATUS_NO)
        self.assertEqual(url, fallback)


class PrivilegeListParseTests(unittest.TestCase):
    def test_load_link_list_uses_card_title(self) -> None:
        html = """
        <ul>
          <li>
            <a href="/detail/detail.php?product_id=1">特典</a>
            <a href="/detail/detail.php?product_id=1">初凪ヒメリウム</a>
          </li>
        </ul>
        """
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.text = html
        session.get.return_value = response
        hits = _load_link_list(session, "https://example.com/privilege", "melonbooks")
        blob = " ".join(hit.text for hit in hits)
        self.assertIn("初凪ヒメリウム", blob)
        index = OfficialIndex()
        index.loaded = True
        index.entries["melonbooks"] = hits
        status, _, _ = lookup_status(
            index,
            "melonbooks",
            "初凪ヒメリウム 1",
            "",
            "https://fallback.example/",
        )
        self.assertEqual(status, STATUS_YES)
