"""主要書店の特典ページ／検索結果を確認する骨組み。"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

import requests

from bs4 import BeautifulSoup

from manga_checker.animate import evaluate_animate_detail, first_animate_detail_url
from manga_checker.http import get_with_retry, make_session
from manga_checker.links import isbn_search_query
from manga_checker.models import Comic, StoreCheck
from manga_checker.search_title import toranoana_search_word
from manga_checker.melon import evaluate_melon_detail, first_melon_detail_url
from manga_checker.official import OfficialIndex, lookup_status
from manga_checker.privilege import (
    STATUS_NO,
    STATUS_UNKNOWN,
    STATUS_YES,
    evaluate_detail_privilege,
    evaluate_gamers_detail,
    evaluate_privilege,
    listing_has_products,
    pick_ranked_detail_url,
    search_is_no_hit,
)
from manga_checker.store_cache import cached_check, remember_check
from manga_checker.title_match import listing_matches_work
from manga_checker.toranoana import evaluate_toranoana_detail, first_toranoana_detail_url

# 公式一覧を正とし、未掲載なら「特典なし」にする店
STRICT_OFFICIAL_STORES = frozenset({"kumazawa", "kikuya"})
DETAIL_PAGE_STORES = frozenset({"animate", "melonbooks", "toranoana"})
# 検索結果ページを常に取得し、ヒット済みなら特典語なしを「特典なし」にする店
LISTING_FETCH_STORES = frozenset({"gamers", "kinokuniya"})
# ISBN検索が0件なら取り扱いなし（タイトル検索に落とさない）
ISBN_NO_HIT_IS_ABSENT = frozenset({"animate", "melonbooks", "gamers", "kinokuniya"})


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


def _kinokuniya_list_url(query: str) -> str:
    return (
        "https://www.kinokuniya.co.jp/disp/CSfDispListPage_001.jsp"
        f"?qsd=true&ptk=01&q={quote(query)}"
    )


def _kinokuniya_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    return _kinokuniya_list_url(isbn or _q(comic))


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
        + urlencode({"name": isbn, "text_type": "all"})
    )


def _melon_title_url(comic: Comic) -> str:
    return (
        "https://www.melonbooks.co.jp/search/search.php?"
        + urlencode({"name": _q(comic), "text_type": "title"})
    )


def _melon_url(comic: Comic) -> str:
    return _melon_isbn_url(comic) or _melon_title_url(comic)


def _kumazawa_url(comic: Comic) -> str:
    return (
        "https://www.search.kumabook.com/kumazawa/html/products/list?"
        + urlencode({"mode": "books", "name": _search_term(comic)})
    )


def _toranoana_list_url(word: str, *, books: bool = False) -> str:
    query = f"?searchWord={quote(word)}"
    if books:
        query += "&searchCategoryCode=bok"
    return "https://ecs.toranoana.jp/tora/ec/app/catalog/list/" + query


def _toranoana_url(comic: Comic) -> str:
    word = toranoana_search_word(comic.title, comic.volume)
    return _toranoana_list_url(word, books=True)


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
            check = StoreCheck(
                store.store_id, store.name, official_yes, detail, official_url
            )
            remember_check(cache, check, comic)
            results.append(check)
            continue
        if store.store_id in STRICT_OFFICIAL_STORES:
            if not catalog.entries.get(store.store_id):
                remembered = cached_check(
                    cache, comic, store.store_id, refresh_unreleased_no=fetch
                )
                if remembered is not None:
                    results.append(remembered)
                    continue
                results.append(
                    StoreCheck(
                        store.store_id,
                        store.name,
                        STATUS_UNKNOWN,
                        "公式特典一覧を取得できていないため未確認。",
                        url,
                    )
                )
                continue
            check = StoreCheck(store.store_id, store.name, official_yes, detail, url)
            remember_check(cache, check, comic)
            results.append(check)
            continue
        remembered = cached_check(
            cache, comic, store.store_id, refresh_unreleased_no=fetch
        )
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
    if store.store_id == "gamers":
        return _fetch_gamers(comic, url, session)
    if store.store_id == "kinokuniya":
        return _fetch_kinokuniya(comic, url, session)
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
        missing="検索結果から一致する商品詳細を特定できませんでした。",
    )


def _fetch_melonbooks(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    name = "メロンブックス"
    attempts: list[tuple[str, bool]] = []
    isbn_url = _melon_isbn_url(comic)
    if isbn_url:
        attempts.append((isbn_url, True))
        attempts.append((isbn_url + "&category_id=4", True))
    title_url = _melon_title_url(comic)
    attempts.append((title_url, False))
    attempts.append((title_url + "&category_id=4", False))
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
    attempts: list[tuple[str, bool]] = []
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        attempts.append((_toranoana_list_url(isbn, books=True), True))
        attempts.append((_toranoana_list_url(isbn, books=False), True))
    word = toranoana_search_word(comic.title, comic.volume)
    title_url = _toranoana_url(comic)
    attempts.append((title_url, False))
    if word:
        attempts.append((_toranoana_list_url(word, books=False), False))
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="toranoana",
        name="とらのあな",
        fallback_url=search_url or title_url,
        attempts=attempts,
        extract=first_toranoana_detail_url,
        evaluate=evaluate_toranoana_detail,
        missing="検索結果から商品詳細（/tora/ec/item/）を特定できませんでした。",
        match_title=toranoana_search_word(comic.title, comic.volume),
        retries=1,
    )


def _fetch_gamers(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="gamers",
        name="ゲーマーズ",
        fallback_url=search_url,
        attempts=[(search_url, bool(isbn_search_query(comic.isbn)))],
        extract=first_gamers_detail_url,
        evaluate=evaluate_gamers_detail,
        missing="検索結果から商品詳細を特定できませんでした。",
    )


def _fetch_kinokuniya(comic: Comic, search_url: str, session: requests.Session) -> StoreCheck:
    attempts: list[tuple[str, bool]] = []
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        attempts.append((_kinokuniya_list_url(isbn), True))
    attempts.append((_kinokuniya_list_url(_q(comic)), False))
    if search_url and all(search_url != url for url, _ in attempts):
        attempts.append((search_url, bool(isbn)))
    return _fetch_detail_attempts(
        comic,
        session,
        store_id="kinokuniya",
        name="紀伊國屋書店",
        fallback_url=search_url,
        attempts=attempts,
        extract=first_kinokuniya_detail_url,
        evaluate=evaluate_detail_privilege,
        missing="検索結果から商品詳細を特定できませんでした。",
        timeout=15,
        retries=1,
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
    timeout: int = 25,
    retries: int = 3,
) -> StoreCheck:
    last_search = fallback_url
    title = match_title or comic.search_query
    last_http = 0
    had_product_hit = False
    saw_search_page = False
    saw_no_hit = False
    last_error: Exception | None = None
    no_hit_url = fallback_url
    last_detail_url = ""
    try:
        for index, (list_url, from_isbn) in enumerate(attempts):
            last_search = list_url
            if index:
                time.sleep(0.8)
            try:
                search_resp = get_with_retry(
                    session,
                    list_url,
                    timeout=timeout,
                    retries=retries,
                    label=f"{name} 検索 {comic.display_title}",
                )
            except requests.RequestException as exc:
                last_error = exc
                continue
            html = search_resp.text or ""
            no_hit = search_is_no_hit(html) and not listing_has_products(html)
            if no_hit:
                saw_search_page = True
                saw_no_hit = True
                no_hit_url = list_url
                if from_isbn and store_id in ISBN_NO_HIT_IS_ABSENT:
                    return StoreCheck(
                        store_id,
                        name,
                        STATUS_NO,
                        "ISBN検索が0件のため、取り扱いなし（特典なし）と扱います。",
                        list_url,
                    )
                continue
            if search_resp.status_code < 400:
                last_http = 0
                saw_search_page = True
            else:
                last_http = search_resp.status_code
            detail_url = extract(
                html,
                list_url,
                title,
                comic.isbn,
                comic.author,
                allow_first=True,
            )
            if not detail_url:
                if listing_has_products(html):
                    had_product_hit = True
                continue
            last_detail_url = detail_url
            had_product_hit = True
            time.sleep(0.8)
            try:
                detail_resp = get_with_retry(
                    session,
                    detail_url,
                    timeout=timeout,
                    retries=retries,
                    headers={"Referer": list_url},
                    label=f"{name} 詳細 {comic.display_title}",
                )
            except requests.RequestException as exc:
                last_error = exc
                continue
            if detail_resp.status_code >= 400:
                last_http = detail_resp.status_code
                continue
            if store_id == "gamers" and not _detail_page_matches(
                comic, detail_resp.text or ""
            ):
                continue
            status, detail = evaluate(detail_resp.text)
            return StoreCheck(store_id, name, status, detail, detail_url)
        if had_product_hit:
            return StoreCheck(
                store_id,
                name,
                STATUS_NO,
                "検索ヒットあり。詳細ページへ進めなかったため特典なしと扱います。",
                last_detail_url or fallback_url,
            )
        if saw_no_hit:
            return StoreCheck(
                store_id,
                name,
                STATUS_NO,
                "検索結果が0件のため、取り扱いなし（特典なし）と扱います。",
                no_hit_url,
            )
        if last_http >= 400:
            return StoreCheck(
                store_id,
                name,
                STATUS_UNKNOWN,
                f"HTTP {last_http}。ページを取得できませんでした。",
                fallback_url,
            )
        if saw_search_page:
            return StoreCheck(
                store_id,
                name,
                STATUS_UNKNOWN,
                "検索ヒットが見つかりませんでした。",
                fallback_url,
            )
        if last_error is not None:
            return StoreCheck(
                store_id, name, STATUS_UNKNOWN, f"取得失敗: {last_error}", last_search
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
    return listing_matches_work(comic.search_query, heading, comic.isbn, comic.author)


_GAMERS_PD = re.compile(r"/pd/(\d+)/?", re.I)
_GAMERS_PID = re.compile(r"(?:[?&]product_id=)(\d+)", re.I)
_KINO_DSG = re.compile(r"/f/dsg-01-(\d+)", re.I)
_GAMERS_CHROME = re.compile(
    r"popular_keyword|swiper|bnr_|banner|fp_fair|global.?nav|gnav|"
    r"header_nav|footer_nav",
    re.I,
)
_GAMERS_LISTING = re.compile(r"list_product|search_item_list|item_list", re.I)


def _gamers_node_ident(node) -> str:
    if node is None or not getattr(node, "get", None):
        return ""
    classes = " ".join(str(c) for c in (node.get("class") or []))
    return f"{classes} {node.get('id') or ''}"


def _is_gamers_chrome_link(tag) -> bool:
    for parent in (tag, *getattr(tag, "parents", [])):
        name = getattr(parent, "name", None)
        if not name:
            break
        if name in ("header", "footer", "nav", "aside"):
            return True
        ident = _gamers_node_ident(parent)
        if _GAMERS_CHROME.search(ident):
            return True
    return False


def _is_gamers_listing_link(tag) -> bool:
    for parent in (tag, *getattr(tag, "parents", [])):
        if not getattr(parent, "name", None):
            break
        if _GAMERS_LISTING.search(_gamers_node_ident(parent)):
            return True
    return False


def first_gamers_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.select(
        ".popular_keyword, .popular_keyword_box, header, footer, nav, aside, "
        ".swiper, [class*='bnr_'], #fp_fair"
    ):
        node.decompose()
    base = page_url or "https://www.gamers.co.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    isbn_digits = re.sub(r"\D", "", isbn or "")
    for tag in soup.find_all("a", href=True):
        if _is_gamers_chrome_link(tag):
            continue
        abs_url = _gamers_detail_url(str(tag.get("href") or ""), base)
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        parent = tag.find_parent(["li", "div", "article", "td", "section"]) or tag
        blob = " ".join(
            part for part in (tag.get_text(" ", strip=True), parent.get_text(" ", strip=True)) if part
        )
        blob_digits = re.sub(r"\D", "", blob)
        score = 0
        if isbn_digits and isbn_digits in blob_digits:
            score += 5
        if listing_matches_work(title, blob, isbn, author=author):
            score += 2
        if _is_gamers_listing_link(tag):
            score += 1
        if score == 0 and not _is_gamers_listing_link(tag):
            continue
        ranked.append((score, abs_url))
    return pick_ranked_detail_url(ranked, allow_first=False)


def _gamers_detail_url(href: str, base: str) -> str:
    if not href:
        return ""
    abs_url = urljoin(base, href).split("#")[0]
    pd = _GAMERS_PD.search(abs_url)
    if pd:
        return f"https://www.gamers.co.jp/pd/{pd.group(1)}/"
    parsed = urlparse(abs_url)
    query = parse_qs(parsed.query)
    product_id = (query.get("product_id") or [""])[0]
    if not product_id:
        match = _GAMERS_PID.search(abs_url)
        if match:
            product_id = match.group(1)
    if not product_id:
        return ""
    if "detail.php" in parsed.path.lower() or query.get("product_id"):
        return f"https://www.gamers.co.jp/products/detail.php?product_id={product_id}"
    return f"https://www.gamers.co.jp/products/detail.php?product_id={product_id}"


def first_kinokuniya_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    page = (page_url or "").split("?")[0]
    if _KINO_DSG.search(page):
        if "見つかりません" in (html or "") and not listing_matches_work(
            title, html or "", isbn, author=author
        ):
            return ""
        return page
    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url or "https://www.kinokuniya.co.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    isbn_digits = re.sub(r"\D", "", isbn or "")
    for tag in soup.find_all("a", href=True):
        abs_url = urljoin(base, str(tag.get("href") or "")).split("#")[0]
        match = _KINO_DSG.search(abs_url)
        if not match:
            continue
        canon = f"https://www.kinokuniya.co.jp/f/dsg-01-{match.group(1)}"
        if canon in seen:
            continue
        seen.add(canon)
        parent = tag.find_parent(["li", "div", "article", "td", "section"]) or tag
        blob = " ".join(
            part for part in (tag.get_text(" ", strip=True), parent.get_text(" ", strip=True)) if part
        )
        blob_digits = re.sub(r"\D", "", blob)
        score = 0
        if isbn_digits and isbn_digits in blob_digits:
            score += 5
        if listing_matches_work(title, blob, isbn, author=author):
            score += 2
        ranked.append((score, canon))
    return pick_ranked_detail_url(ranked, allow_first=True)
