"""入荷・特典一覧を一括取得して、作品と突き合わせる。"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field

import requests

from manga_checker.comiczin import load_comiczin_items
from manga_checker.comirano import load_comirano_items
from manga_checker.dates import comiczin_months, privilege_rematch_months
from manga_checker.models import Comic, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_YES
from manga_checker.privilege_index import (
    load_animate_privileges,
    load_gamers_privileges,
    load_melon_privileges,
    load_toranoana_privileges,
)
from manga_checker.title_match import titles_match
from manga_checker.volume import is_volume_one


@dataclass
class ListingItem:
    title: str
    url: str
    extra: str = ""
    isbn: str = ""


@dataclass
class BulkListingIndex:
    items: dict[str, list[ListingItem]] = field(default_factory=dict)
    covered_months: dict[str, set[tuple[int, int]]] = field(default_factory=dict)
    loaded: bool = False

    def load(
        self,
        session: requests.Session,
        months: list[tuple[int, int]],
        privilege_months_window: list[tuple[int, int]] | None = None,
        comics: list[Comic] | None = None,
        only: set[str] | None = None,
    ) -> None:
        if self.loaded:
            return
        priv_months = privilege_months_window or privilege_rematch_months()
        wanted = only or {
            "comiczin",
            "comirano",
            "animate",
            "melonbooks",
            "gamers",
            "toranoana",
        }
        print("書店特典一覧を一括取得します…")
        if "comiczin" in wanted:
            zin_months = comiczin_months(catalog_months=months)
            print(
                "COMIC ZIN: 入荷日検索を "
                + "、".join(f"{y}年{m}月" for y, m in zin_months)
                + "（当月〜翌月）で取得します"
            )
            zin_raw = _load_store_list(
                "COMIC ZIN",
                lambda: load_comiczin_items(session, zin_months),
            )
            if zin_raw is not None:
                self.items["comiczin"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra, isbn=item.isbn)
                    for item in zin_raw
                    if is_volume_one(item.title)
                ]
                # 0件でも「取得済み」として残し、未ヒットをキャッシュの古い判定で埋めない。
        if "comirano" in wanted:
            comirano_raw = _load_store_list("こみらの！", lambda: load_comirano_items(session))
            if comirano_raw is not None:
                self.items["comirano"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra)
                    for item in comirano_raw
                    if is_volume_one(item.title)
                ]
                # 0件でも取得済みとして残す。
        if "animate" in wanted:
            animate_covered: set[tuple[int, int]] = set()
            animate_raw = _load_store_list(
                "アニメイト特典",
                lambda: load_animate_privileges(
                    session, priv_months, covered=animate_covered
                ),
            )
            if animate_covered:
                self.covered_months["animate"] = animate_covered
            if animate_raw is not None:
                self.items["animate"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra)
                    for item in animate_raw
                ]
                # 空一覧でもキーを残し、未確認へ落とせるようにする。
        if "melonbooks" in wanted and "melonbooks" not in self.items:
            melon_covered: set[tuple[int, int]] = set()
            melon_raw = _load_store_list(
                "メロンブックス特典",
                lambda: load_melon_privileges(
                    session, priv_months, covered=melon_covered
                ),
            )
            if melon_covered:
                self.covered_months["melonbooks"] = melon_covered
            if melon_raw is not None:
                self.items["melonbooks"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra)
                    for item in melon_raw
                ]
                # 空一覧でもキーを残す。
        if "gamers" in wanted:
            gamers_covered: set[tuple[int, int]] = set()
            gamers_raw = _load_store_list(
                "ゲーマーズ特典",
                lambda: load_gamers_privileges(
                    session, priv_months, covered=gamers_covered
                ),
            )
            if gamers_covered:
                self.covered_months["gamers"] = gamers_covered
            if gamers_raw is not None:
                self.items["gamers"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra)
                    for item in gamers_raw
                ]
                # 空一覧でもキーを残す。
        if "toranoana" in wanted:
            tora_covered: set[tuple[int, int]] = set()
            tora_raw = _load_store_list(
                "とらのあな特典",
                lambda: load_toranoana_privileges(
                    session, priv_months, comics=comics or [], covered=tora_covered
                ),
            )
            if tora_covered:
                self.covered_months["toranoana"] = tora_covered
            if tora_raw is not None:
                self.items["toranoana"] = [
                    ListingItem(title=item.title, url=item.url, extra=item.extra)
                    for item in tora_raw
                ]
                # 空一覧でもキーを残す。
        self.loaded = True
        print(
            "  一覧件数: "
            f"アニメイト={len(self.items.get('animate', []))}, "
            f"メロン={len(self.items.get('melonbooks', []))}, "
            f"ゲーマーズ={len(self.items.get('gamers', []))}, "
            f"とらのあな={len(self.items.get('toranoana', []))}, "
            f"COMIC ZIN={len(self.items.get('comiczin', []))}, "
            f"こみらの！={len(self.items.get('comirano', []))}"
        )

    def lookup(self, store_id: str, comic: Comic) -> ListingItem | None:
        for item in self.items.get(store_id, []):
            blob = f"{item.title} {item.extra} {item.isbn}"
            if item.isbn and comic.isbn:
                digits = "".join(ch for ch in comic.isbn if ch.isdigit())
                if len(digits) >= 10 and digits in item.isbn:
                    return item
            if titles_match(comic.search_query, blob, comic.isbn, comic.author):
                return item
            if titles_match(comic.title, blob, comic.isbn, comic.author):
                return item
            if titles_match(item.title, comic.title, comic.isbn, comic.author):
                return item
            if titles_match(item.title, comic.search_query, comic.isbn, comic.author):
                return item
        return None

    def check(self, store_id: str, store_name: str, comic: Comic, fallback_url: str) -> StoreCheck:
        item = self.lookup(store_id, comic)
        if item:
            return StoreCheck(
                store_id,
                store_name,
                STATUS_YES,
                item.extra or "特典一覧で検出",
                item.url,
            )
        return StoreCheck(
            store_id,
            store_name,
            STATUS_NO,
            "特典一覧に該当タイトルはありません。",
            fallback_url,
        )


def _load_store_list(label: str, loader):
    try:
        return list(loader() or [])
    except Exception as exc:
        print(f"  {label}の一覧取得に失敗しました: {exc}")
        traceback.print_exc()
        return None
