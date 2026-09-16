"""主要書店の特典ページ／検索結果を確認する骨組み。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import requests

from bs4 import BeautifulSoup

from manga_checker.animate import evaluate_animate_detail, first_animate_detail_url
from manga_checker.http import get_with_retry, make_session
from manga_checker.links import isbn_search_query
from manga_checker.models import Comic, StoreCheck
from manga_checker.search_title import toranoana_search_word
from manga_checker.melon import evaluate_melon_detail, first_melon_detail_url
from manga_checker.official import OfficialIndex, lookup_status
from manga_checker.privilege import STATUS_UNKNOWN, STATUS_YES, evaluate_privilege
from manga_checker.store_cache import cached_check, remember_check
from manga_checker.title_match import listing_matches_work
from manga_checker.toranoana import evaluate_toranoana_detail, first_toranoana_detail_url

# 公式一覧を正とし、未掲載なら「通常/なし」にする店
STRICT_OFFICIAL_STORES = frozenset({"kumazawa", "kikuya"})
DETAIL_PAGE_STORES = frozenset({"animate", "melonbooks", "toranoana"})
# 検索結果ページを常に取得し、ヒット済みなら特典語なしを「通常/なし」にする店
LISTING_FETCH_STORES = frozenset({"gamers", "kinokuniya"})


@dataclass
class Store:
    store_id: str
    name: str
    search_url: Callable[[Comic], str]
    privilege_index_url: str = ""


def _q(comic: Comic) -> str:
    return comic.search_query


def _search_term(comic: Comic) -> str:
    return isbn_search_query(comic.isbn) or _q(comic)


def _kinokuniya_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        return f"https://www.kinokuniya.co.jp/f/dsg-01-{isbn}"
    return (
        "https://www.kinokuniya.co.jp/disp/CSfDispListPage_001.jsp"
        f"?qsd=true&ptk=01&q={quote(_q(comic))}"
    )


def _gamers_url(comic: Comic) -> str:
    params = {"mode": "search", "smt": _search_term(comic), "spc": "4"}
    return "https://www.gamers.co.jp/products/list.php?" + urlencode(params)


def _animate_url(comic: Comic) -> str:
    return (
        "https://www.animate-onlineshop.jp/products/list.php"
        f"?mode=search&smt={quote(_search_term(comic))}"
    )


def _animate_title_url(comic: Comic) -> str:
    return (
        "https://www.animate-onlineshop.jp/products/list.php"
        f"?mode=search&smt={quote(_q(comic))}"
    )


def _melon_isbn_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if not isbn:
        return ""
    return (
        "https://www.melonbooks.co.jp/search/search.php?"
        + urlencode({"name": isbn, "text_type": "all", "category_id": "4"})
    )


def _melon_title_url(comic: Comic) -> str:
    return (
        "https://www.melonbooks.co.jp/search/search.php?"
        + urlencode({"name": _q(comic), "text_type": "title", "category_id": "4"})
    )


def _melon_url(comic: Comic) -> str:
    return _melon_isbn_url(comic) or _melon_title_url(comic)


def _kumazawa_url(comic: Comic) -> str:
    return (
        "https://www.search.kumabook.com/kumazawa/html/products/list?"
        + urlencode({"mode": "books", "name": _search_term(comic)})
    )


def _toranoana_url(comic: Comic) -> str:
    word = toranoana_search_word(comic.title, comic.volume)
    return (
        "https://ecs.toranoana.jp/tora/ec/app/catalog/list/"
        f"?searchWord={quote(word)}"
    )


STORES: list[Store] = [
    Store(
        store_id="animate",
        name="アニメイト",
        search_url=_animate_url,
        privilege_index_url="https://www.animate-onlineshop.jp/products/privilege_list.php",
    ),
    Store(
        store_id="melonbooks",
        name="メロンブックス",
        search_url=_melon_url,
        privilege_index_url="https://www.melonbooks.co.jp/privilege/privilege.php",
    ),
    Store(
        store_id="gamers",
        name="ゲーマーズ",
        search_url=_gamers_url,
        privilege_index_url="https://www.gamers.co.jp/products/privilege_list.php",
    ),
    Store(
        store_id="toranoana",
        name="とらのあな",
        search_url=_toranoana_url,
    ),
    Store(
        store_id="kikuya",
        name="喜久屋書店",
        search_url=lambda c: (
            "https://kikuyashoten.myshopify.com/search?q=" + quote(_q(c))
        ),
        privilege_index_url="https://kikuyashoten.myshopify.com",
    ),
    Store(
        store_id="kinokuniya",
        name="紀伊國屋書店",
        search_url=_kinokuniya_url,
        privilege_index_url="https://www.kinokuniya.co.jp/",
    ),
    Store(
        store_id="kumazawa",
        name="くまざわ書店",
        search_url=_kumazawa_url,
        privilege_index_url="https://www.search.kumabook.com/kumazawa/html/products/list",
    ),
]


def check_stores(
    comic: Comic,
    fetch: bool = False,
    delay_sec: float = 1.5,
    session: requests.Session | None = None,
    catalog: OfficialIndex | None = None,
    cache: dict | None = None,
) -> list[StoreCheck]:
    session = session or make_session(
        extra_headers={"Accept-Language": "ja,en;q=0.8"}
    )
    if catalog is None:
        catalog = OfficialIndex()
    if not catalog.loaded:
        catalog.load(session)

    results: list[StoreCheck] = []
    for store in STORES:
        url = store.search_url(comic)
        official_yes, detail, official_url = lookup_status(
            catalog,
            store.store_id,
            comic.search_query,
            comic.isbn,
            url,
        )
        if official_yes == STATUS_YES and (
            store.store_id not in DETAIL_PAGE_STORES or not fetch
        ):
            results.append(
                StoreCheck(store.store_id, store.name, official_yes, detail, official_url)
            )
            continue
        if store.store_id in STRICT_OFFICIAL_STORES:
            results.append(
                StoreCheck(store.store_id, store.name, official_yes, detail, url)
            )
            continue
        remembered = cached_check(cache, comic, store.store_id)
        if remembered is not None:
            results.append(remembered)
            continue
        if store.store_id in DETAIL_PAGE_STORES or store.store_id in LISTING_FETCH_STORES:
            if not fetch:
                results.append(
                    StoreCheck(
                        store.store_id,
                        store.name,
                        STATUS_UNKNOWN,
                        "未取得。リンク先の商品カードで確認してください。",
                        url,
                    )
                )
                continue
            fetched = _fetch_store(store, comic, url, session)
            if fetched.status == STATUS_UNKNOWN and official_yes == STATUS_YES:
                fetched = StoreCheck(
                    store.store_id,
                    store.name,
                    STATUS_YES,
                    detail,
                    fetched.url or official_url,
                )
            remember_check(cache, fetched, comic)
            results.append(fetched)
            time.sleep(delay_sec)
            continue
        if not fetch:
            results.append(
                StoreCheck(
                    store.store_id,
                    store.name,
                    STATUS_UNKNOWN,
                    "未取得。リンク先の商品カードで確認してください。",
                    url,
                )
            )
            continue
        fetched = _fetch_store(store, comic, url, session)
        remember_check(cache, fetched, comic)
        results.append(fetched)
        time.sleep(delay_sec)
    return results


def _fetch_store(store: Store, comic: Comic, url: str, session: requests.Session) -> StoreCheck:
    if store.store_id == "melonbooks":
        return _fetch_melonbooks(comic, url, session)
    if store.store_id == "animate":
        return _fetch_animate(comic, url, session)
    if store.store_id == "toranoana":
        return _fetch_toranoana(comic, url, session)
    try:
        response = get_with_retry(session, url, timeout=25, label=f"{store.name} {comic.display_title}")
        if response.status_code >= 400:
            status, detail = evaluate_privilege(
                "",
                title_for_match=comic.search_query,
                isbn=comic.isbn,
                author=comic.author,
                source_url=url,
                http_ok=False,
            )
            return StoreCheck(
                store.store_id,
                store.name,
                status,
                f"HTTP {response.status_code}。{detail}",
                url,
            )
        status, detail = evaluate_privilege(
            response.text,
            title_for_match=comic.search_query,
            isbn=comic.isbn,
            author=comic.author,
            source_url=url,
            store_id=store.store_id,
        )
        return StoreCheck(store.store_id, store.name, status, detail, url)
    except requests.RequestException as exc:
        return StoreCheck(
            store.store_id,
            store.name,
            STATUS_UNKNOWN,
            f"取得失敗: {exc}",
            url,
        )


def _fetch_animate(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    name = "アニメイト"
    attempts: list[tuple[str, bool]] = []
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        attempts.append(
            (
                "https://www.animate-onlineshop.jp/products/list.php"
                f"?mode=search&smt={quote(isbn)}",
                True,
            )
        )
    attempts.append((_animate_title_url(comic), False))
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="animate",
        name=name,
        fallback_url=search_url,
        attempts=attempts,
        extract=first_animate_detail_url,
        evaluate=evaluate_animate_detail,
        missing="検索結果から一致する商品詳細（/pd/）を特定できませんでした。",
    )


def _fetch_melonbooks(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    name = "メロンブックス"
    attempts: list[tuple[str, bool]] = []
    isbn_url = _melon_isbn_url(comic)
    if isbn_url:
        attempts.append((isbn_url, True))
    attempts.append((_melon_title_url(comic), False))
    session.cookies.set("adult_check", "1", domain="www.melonbooks.co.jp")
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="melonbooks",
        name=name,
        fallback_url=search_url,
        attempts=attempts,
        extract=first_melon_detail_url,
        evaluate=evaluate_melon_detail,
        missing="検索結果から一致する商品詳細（detail.php?product_id=）を特定できませんでした。",
    )


def _fetch_toranoana(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    title_url = _toranoana_url(comic)
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="toranoana",
        name="とらのあな",
        fallback_url=title_url,
        attempts=[(title_url, False)],
        extract=first_toranoana_detail_url,
        evaluate=evaluate_toranoana_detail,
        missing="検索結果から一致する商品詳細（/tora/ec/item/）を特定できませんでした。",
        match_title=toranoana_search_word(comic.title, comic.volume),
    )


def _fetch_detail_attempts(
    comic: Comic,
    session: requests.Session,
    *,
    store_id: str,
    name: str,
    fallback_url: str,
    attempts: list[tuple[str, bool]],
    extract,
    evaluate,
    missing: str,
    match_title: str = "",
) -> StoreCheck:
    last_search = fallback_url
    title = match_title or comic.search_query
    last_http = 0
    try:
        for index, (list_url, from_isbn) in enumerate(attempts):
            last_search = list_url
            if index:
                time.sleep(0.8)
            search_resp = get_with_retry(
                session, list_url, timeout=25, label=f"{name} 検索 {comic.display_title}"
            )
            if search_resp.status_code >= 400:
                last_http = search_resp.status_code
                continue
            detail_url = extract(
                search_resp.text,
                list_url,
                title,
                comic.isbn,
                comic.author,
                allow_first=False,
            )
            need_detail_check = bool(from_isbn and detail_url)
            if not detail_url and from_isbn:
                detail_url = extract(
                    search_resp.text,
                    list_url,
                    title,
                    comic.isbn,
                    comic.author,
                    allow_first=True,
                )
                need_detail_check = True
            if not detail_url:
                continue
            time.sleep(0.8)
            detail_resp = get_with_retry(
                session,
                detail_url,
                timeout=25,
                headers={"Referer": list_url},
                label=f"{name} 詳細 {comic.display_title}",
            )
            if detail_resp.status_code >= 400:
                last_http = detail_resp.status_code
                continue
            if need_detail_check and not _detail_page_matches(comic, detail_resp.text):
                continue
            status, detail = evaluate(detail_resp.text)
            # メロンは検索カード判定を使わず、特典ありのときだけ詳細URLを返す。
            if store_id == "melonbooks" and status != STATUS_YES:
                return StoreCheck(store_id, name, status, detail, last_search)
            return StoreCheck(store_id, name, status, detail, detail_url)
        if last_http >= 400:
            return StoreCheck(
                store_id,
                name,
                STATUS_UNKNOWN,
                f"HTTP {last_http}。ページを取得できませんでした。",
                fallback_url,
            )
        return StoreCheck(store_id, name, STATUS_UNKNOWN, missing, fallback_url)
    except requests.RequestException as exc:
        return StoreCheck(store_id, name, STATUS_UNKNOWN, f"取得失敗: {exc}", last_search)


def _detail_page_matches(comic: Comic, html: str) -> bool:
    digits = "".join(ch for ch in (comic.isbn or "") if ch.isdigit())
    blob = html or ""
    if len(digits) >= 10 and digits in blob.replace("-", "").replace(" ", ""):
        return True
    soup = BeautifulSoup(blob, "html.parser")
    parts: list[str] = []
    for tag in soup.find_all(["h1", "title"]):
        text = tag.get_text(" ", strip=True)
        if text:
            parts.append(text)
    heading = " ".join(parts)
    body = soup.get_text(" ", strip=True)[:8000]
    return listing_matches_work(
        comic.search_query, heading, comic.isbn, comic.author
    ) or listing_matches_work(comic.search_query, body, comic.isbn, comic.author)
