"""入荷・特典一覧を一括取得して、作品と突き合わせる。"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from manga_checker.comiczin import ZinItem, load_comiczin_items
from manga_checker.comirano import ComiranoItem, load_comirano_items
from manga_checker.models import Comic, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_YES
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
    ) -> None:
        if self.loaded:
            return
        print("COMIC ZIN・こみらの！の一覧を一括取得します…")
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
        self.items["comiczin"] = zin
        self.items["comirano"] = comirano
        self.loaded = True
        print(f"  一覧件数: COMIC ZIN={len(zin)}, こみらの！={len(comirano)}")

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
                "入荷・特典一覧で検出",
                item.url,
            )
        return StoreCheck(
            store_id,
            store_name,
            STATUS_NO,
            "入荷・特典一覧に該当タイトルはありません。",
            fallback_url,
        )
