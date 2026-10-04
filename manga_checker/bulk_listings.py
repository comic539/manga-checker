"""入荷・特典一覧を一括取得して、作品と突き合わせる。"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from manga_checker.comiczin import ZinItem, load_comiczin_items
from manga_checker.comirano import ComiranoItem, load_comirano_items
from manga_checker.dates import privilege_months
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
    loaded: bool = False

    def load(
        self,
        session: requests.Session,
        months: list[tuple[int, int]],
        privilege_months_window: list[tuple[int, int]] | None = None,
    ) -> None:
        if self.loaded:
            return
        priv_months = privilege_months_window or privilege_months()
        print("書店特典一覧を一括取得します…")
        zin = [
            ListingItem(title=item.title, url=item.url, extra=item.extra, isbn=item.isbn)
            for item in load_comiczin_items(session, months)
            if is_volume_one(item.title)
        ]
        comirano = [
            ListingItem(title=item.title, url=item.url, extra=item.extra)
            for item in load_comirano_items(session)
            if is_volume_one(item.title)
        ]
        animate = [
            ListingItem(title=item.title, url=item.url, extra=item.extra)
            for item in load_animate_privileges(session, priv_months)
        ]
        melon = [
            ListingItem(title=item.title, url=item.url, extra=item.extra)
            for item in load_melon_privileges(session, priv_months)
        ]
        gamers = [
            ListingItem(title=item.title, url=item.url, extra=item.extra)
            for item in load_gamers_privileges(session, priv_months)
        ]
        tora = [
            ListingItem(title=item.title, url=item.url, extra=item.extra)
            for item in load_toranoana_privileges(session, priv_months)
        ]
        self.items["comiczin"] = zin
        self.items["comirano"] = comirano
        self.items["animate"] = animate
        self.items["melonbooks"] = melon
        self.items["gamers"] = gamers
        self.items["toranoana"] = tora
        self.loaded = True
        print(
            "  一覧件数: "
            f"アニメイト={len(animate)}, メロン={len(melon)}, ゲーマーズ={len(gamers)}, "
            f"とらのあな={len(tora)}, COMIC ZIN={len(zin)}, こみらの！={len(comirano)}"
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
