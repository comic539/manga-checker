"""書店特典の判定結果キャッシュ。未確認は再取得対象のままにする。"""

from __future__ import annotations

import json
from pathlib import Path

from manga_checker.models import Comic, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES

_KEEP = frozenset({STATUS_YES, STATUS_NO})


def cache_key(comic: Comic, store_id: str) -> str:
    ident = comic.isbn or comic.display_title
    return f"{ident}|{store_id}"


def load_checks_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, row in payload.items():
        if isinstance(row, dict):
            result[str(key)] = {
                "status": str(row.get("status") or ""),
                "detail": str(row.get("detail") or ""),
                "url": str(row.get("url") or ""),
                "store_name": str(row.get("store_name") or ""),
            }
    return result


def save_checks_cache(path: Path, cache: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def cached_check(cache: dict[str, dict[str, str]] | None, comic: Comic, store_id: str) -> StoreCheck | None:
    if not cache:
        return None
    row = cache.get(cache_key(comic, store_id))
    if not row:
        return None
    status = row.get("status") or ""
    if status not in _KEEP:
        return None
    return StoreCheck(
        store_id,
        row.get("store_name") or store_id,
        status,
        row.get("detail") or "",
        row.get("url") or "",
    )


def remember_check(cache: dict[str, dict[str, str]] | None, check: StoreCheck, comic: Comic) -> None:
    if cache is None:
        return
    if check.status == STATUS_UNKNOWN:
        cache.pop(cache_key(comic, check.store_id), None)
        return
    cache[cache_key(comic, check.store_id)] = {
        "status": check.status,
        "detail": check.detail,
        "url": check.url,
        "store_name": check.store_name,
    }
