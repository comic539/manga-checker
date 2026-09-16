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
        comic = Comic(title="2年B組 勇者デストロイヤーず 1", isbn="9784088852280")
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
