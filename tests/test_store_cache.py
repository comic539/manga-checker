import unittest
from unittest.mock import MagicMock, patch

from manga_checker.http import get_with_retry
from manga_checker.models import Comic, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES
from manga_checker.store_cache import cached_check, remember_check


class GetWithRetryTests(unittest.TestCase):
    def test_retries_429_then_returns_ok(self) -> None:
        session = MagicMock()
        blocked = MagicMock()
        blocked.status_code = 429
        ok = MagicMock()
        ok.status_code = 200
        session.get.side_effect = [blocked, ok]
        with patch("manga_checker.http.time.sleep"):
            response = get_with_retry(session, "https://example.test/", retries=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.get.call_count, 2)


class StoreCacheTests(unittest.TestCase):
    def test_unknown_is_not_reused(self) -> None:
        comic = Comic(title="2年B組 勇者デストロイヤーず 1", isbn="9784088852280")
        cache: dict = {}
        remember_check(
            cache,
            StoreCheck("animate", "アニメイト", STATUS_UNKNOWN, "未取得", "https://a"),
            comic,
        )
        self.assertIsNone(cached_check(cache, comic, "animate"))

    def test_yes_and_no_are_reused(self) -> None:
        comic = Comic(
            title="2年B組 勇者デストロイヤーず 1",
            isbn="9784088852280",
            pubdate="2020-01-04",
        )
        cache: dict = {}
        remember_check(
            cache,
            StoreCheck("animate", "アニメイト", STATUS_YES, "あり", "https://a"),
            comic,
        )
        remember_check(
            cache,
            StoreCheck("gamers", "ゲーマーズ", STATUS_NO, "なし", "https://g"),
            comic,
        )
        yes = cached_check(cache, comic, "animate")
        no = cached_check(cache, comic, "gamers")
        assert yes is not None
        assert no is not None
        self.assertEqual(yes.status, STATUS_YES)
        self.assertEqual(no.status, STATUS_NO)

    def test_no_is_reused_before_release_unless_refreshing(self) -> None:
        comic = Comic(
            title="アニマルシグナル 1",
            isbn="9784088852690",
            pubdate="2099-12-31",
        )
        cache: dict = {}
        remember_check(
            cache,
            StoreCheck("animate", "アニメイト", STATUS_NO, "なし", "https://a"),
            comic,
        )
        kept = cached_check(cache, comic, "animate")
        assert kept is not None
        self.assertEqual(kept.status, STATUS_NO)
        self.assertIsNone(
            cached_check(cache, comic, "animate", refresh_unreleased_no=True)
        )

    def test_load_drops_unknown_entries(self) -> None:
        import tempfile
        from pathlib import Path

        from manga_checker.store_cache import load_checks_cache, save_checks_cache

        payload = {
            "9784|animate": {
                "status": STATUS_UNKNOWN,
                "detail": "古い未確認",
                "url": "https://a",
                "store_name": "アニメイト",
            },
            "9784|gamers": {
                "status": STATUS_NO,
                "detail": "なし",
                "url": "https://g",
                "store_name": "ゲーマーズ",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")
            loaded = load_checks_cache(path)
        self.assertNotIn("9784|animate", loaded)
        self.assertEqual(loaded["9784|gamers"]["status"], STATUS_NO)

    def test_legacy_no_label_is_treated_as_privilege_none(self) -> None:
        comic = Comic(
            title="発売済み 1",
            isbn="9784000000001",
            pubdate="2020-01-04",
        )
        cache = {
            "9784000000001|animate": {
                "status": "通常/なし",
                "detail": "なし",
                "url": "https://a",
                "store_name": "アニメイト",
            }
        }
        check = cached_check(cache, comic, "animate")
        assert check is not None
        self.assertEqual(check.status, STATUS_NO)
