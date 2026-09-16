import unittest
from unittest.mock import MagicMock

from manga_checker.models import Comic
from manga_checker.openbd import enrich_with_openbd


class OpenBdCoverTests(unittest.TestCase):
    def test_does_not_overwrite_rakuten_cover(self) -> None:
        comic = Comic(
            title="九月の本 1",
            isbn="9784000000000",
            cover_url="https://thumbnail.image.rakuten.co.jp/@0_mall/book/cover.jpg",
            cover_source="rakuten",
            pubdate="2026-09-04",
        )
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [
            {
                "summary": {
                    "isbn": "9784000000000",
                    "title": "九月の本",
                    "cover": "https://cover.openbd.jp/9784000000000.jpg",
                    "pubdate": "2026-09-10",
                }
            }
        ]
        session.post.return_value = response
        enrich_with_openbd([comic], session=session)
        self.assertIn("rakuten.co.jp", comic.cover_url)
        self.assertEqual(comic.cover_source, "rakuten")
        self.assertEqual(comic.pubdate, "2026-09-10")

    def test_restores_rakuten_cover_source(self) -> None:
        comic = Comic(
            title="九月の本 1",
            isbn="9784000000000",
            cover_url="https://thumbnail.image.rakuten.co.jp/@0_mall/book/cover.jpg",
            cover_source="openbd",
        )
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [
            {"summary": {"isbn": "9784000000000", "cover": "https://cover.openbd.jp/9784000000000.jpg"}}
        ]
        session.post.return_value = response
        enrich_with_openbd([comic], session=session)
        self.assertIn("rakuten.co.jp", comic.cover_url)
        self.assertEqual(comic.cover_source, "rakuten")

    def test_does_not_invent_openbd_fallback_url(self) -> None:
        comic = Comic(title="九月の本 1", isbn="9784000000000")
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [{"summary": {"isbn": "9784000000000", "title": "九月の本"}}]
        session.post.return_value = response
        enrich_with_openbd([comic], session=session)
        self.assertEqual(comic.cover_url, "")
        self.assertNotIn("cover.openbd.jp", comic.cover_url)
