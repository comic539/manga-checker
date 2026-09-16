import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from manga_checker.catalog import (
    _parse_ndl_item,
    load_catalog_json,
    month_range,
    redistribute_by_pubdate,
    write_catalog_json,
)
from manga_checker.models import Comic


SAMPLE = """
<item xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:dcndl="http://ndl.go.jp/dcndl/terms/"
      xmlns:dcterms="http://purl.org/dc/terms/"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <title>リベンジアクト</title>
  <link>https://ndlsearch.ndl.go.jp/books/example</link>
  <dc:title>リベンジアクト</dc:title>
  <dc:creator>作者</dc:creator>
  <dcndl:volume>第1巻</dcndl:volume>
  <dc:publisher>出版社</dc:publisher>
  <dcterms:issued>2026.9</dcterms:issued>
  <dc:identifier xsi:type="dcndl:ISBN">978-4-0000-0000-0</dc:identifier>
</item>
"""


class CatalogParseTests(unittest.TestCase):
    def test_parse_ndl_item(self) -> None:
        item = ET.fromstring(SAMPLE)
        comic = _parse_ndl_item(item)
        self.assertIsNotNone(comic)
        assert comic is not None
        self.assertEqual(comic.title, "リベンジアクト")
        self.assertEqual(comic.volume, "第1巻")
        self.assertEqual(comic.isbn, "9784000000000")
        self.assertEqual(comic.publisher, "出版社")

    def test_redistribute_moves_filled_date_to_real_month(self) -> None:
        august = Comic(title="風と雲 1", publisher="小学館", pubdate="2026-08-28")
        september = Comic(title="九月の本 1", publisher="集英社", pubdate="2026-09-10")
        by_month = {
            (2026, 8): [],
            (2026, 9): [august, september],
        }
        moved = redistribute_by_pubdate(by_month, [(2026, 8), (2026, 9)])
        self.assertEqual([c.title for c in moved[(2026, 8)]], ["風と雲 1"])
        self.assertEqual([c.title for c in moved[(2026, 9)]], ["九月の本 1"])

    def test_month_range_is_first_through_last_day(self) -> None:
        self.assertEqual(month_range(2026, 8), ("2026-08-01", "2026-08-31"))
        self.assertEqual(month_range(2026, 2), ("2026-02-01", "2026-02-28"))

    def test_load_catalog_json_roundtrip(self) -> None:
        comic = Comic(
            title="風と雲 1",
            author="著者",
            publisher="小学館",
            pubdate="2026-08-28",
            isbn="9784000000000",
            source="rakuten",
            cover_url="https://thumbnail.image.rakuten.co.jp/cover.jpg",
            cover_source="openbd",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            write_catalog_json(path, {(2026, 8): [comic], (2026, 9): []})
            loaded = load_catalog_json(path, [(2026, 8), (2026, 9)])
        self.assertEqual(loaded[(2026, 8)][0].title, "風と雲 1")
        self.assertEqual(loaded[(2026, 8)][0].isbn, "9784000000000")
        self.assertEqual(loaded[(2026, 8)][0].cover_url, "https://thumbnail.image.rakuten.co.jp/cover.jpg")
        self.assertEqual(loaded[(2026, 8)][0].cover_source, "rakuten")
        self.assertEqual(loaded[(2026, 9)], [])


if __name__ == "__main__":
    unittest.main()
