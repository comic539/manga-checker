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
from manga_checker.dates import add_months, today_jst, year_month_from_pubdate
from manga_checker.http import get_with_retry, make_session
from manga_checker.links import isbn_search_query
from manga_checker.models import Comic, StoreCheck
from manga_checker.search_title import toranoana_search_word
from manga_checker.melon import evaluate_melon_detail, first_melon_detail_url
from manga_checker.bulk_listings import BulkListingIndex
from manga_checker.official import OfficialIndex, lookup_status
from manga_checker.privilege import (
    STATUS_NO,
    STATUS_UNKNOWN,
    STATUS_YES,
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
STRICT_OFFICIAL_STORES = frozenset({"kikuya"})
DETAIL_PAGE_STORES = frozenset()
# 検索結果ページを常に取得し、ヒット済みなら特典語なしを「特典なし」にする店
LISTING_FETCH_STORES = frozenset()
# ISBN検索が0件なら取り扱いなし（タイトル検索に落とさない）
ISBN_NO_HIT_IS_ABSENT = frozenset()
# 入荷カレンダー／特典一覧を一括取得する店
BULK_LISTING_STORES = frozenset(
    {"animate", "melonbooks", "gamers", "toranoana", "comiczin", "comirano"}
)
def listing_covers_comic(store_id: str, comic: Comic, today=None) -> bool:
    """一覧走査がその作品の月を完全に覆うなら、未ヒットを特典なしにしてよい。"""
    if store_id in {"comirano", "kikuya"}:
        return False
    ym = year_month_from_pubdate(comic.pubdate)
    current_date = today or today_jst()
    current = (current_date.year, current_date.month)
    nxt = add_months(current_date.year, current_date.month, 1)
    if ym is None:
        return store_id not in {"toranoana", "comiczin"}
    if store_id == "toranoana":
        return ym == current
    if store_id == "comiczin":
        return current <= ym <= nxt
    return True


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


def _gamers_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        return "https://www.gamers.co.jp/products/list.php?" + urlencode(
            {"mode": "search", "smt": isbn}
        )
    return "https://www.gamers.co.jp/products/privilege_list.php"


def _animate_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        return (
            "https://www.animate-onlineshop.jp/products/list.php"
            f"?mode=search&smt={quote(isbn)}"
        )
    return "https://www.animate-onlineshop.jp/products/privilege_list.php"


def _animate_title_url(comic: Comic) -> str:
    return (
        "https://www.animate-onlineshop.jp/products/list.php"
        f"?mode=search&smt={quote(_q(comic))}"
    )


def _melon_isbn_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if not isbn:
        return ""
    return "https://www.melonbooks.co.jp/search/search.php?" + urlencode({"name": isbn})


def _melon_url(comic: Comic) -> str:
    return _melon_isbn_url(comic) or "https://www.melonbooks.co.jp/privilege/privilege.php"


def _toranoana_list_url(word: str, *, books: bool = False) -> str:
    query = f"?searchWord={quote(word)}"
    if books:
        query += "&searchCategoryCode=bok"
    return "https://ecs.toranoana.jp/tora/ec/app/catalog/list/" + query


def _toranoana_url(comic: Comic) -> str:
    isbn = isbn_search_query(comic.isbn)
    if isbn:
        return "https://ecs.toranoana.jp/tora/ec/app/catalog/list?searchWord=" + quote(isbn)
    return (
        "https://ecs.toranoana.jp/tora/ec/bok/pages/all/item/standard/calendar/1/"
        "?withBenefitsFlg=1"
    )


def _comiczin_url(comic: Comic) -> str:
    return "https://shop.comiczin.jp/products/list.php"


def _comirano_url(comic: Comic) -> str:
    return "https://comirano.info/category/comic/"


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
        store_id="comiczin",
        name="COMIC ZIN",
        search_url=_comiczin_url,
        privilege_index_url="https://shop.comiczin.jp/products/list.php",
    ),
    Store(
        store_id="comirano",
        name="こみらの！",
        search_url=_comirano_url,
        privilege_index_url="https://comirano.info/category/comic/",
    ),
    Store(
        store_id="kikuya",
        name="喜久屋書店",
        search_url=lambda c: (
            "https://kikuyashoten.myshopify.com/search?q=" + quote(_q(c))
        ),
        privilege_index_url="https://kikuyashoten.myshopify.com",
    ),
]


def check_stores(
    comic: Comic,
    fetch: bool = False,
    delay_sec: float = 1.5,
    session: requests.Session | None = None,
    catalog: OfficialIndex | None = None,
    cache: dict | None = None,
    listings: BulkListingIndex | None = None,
    rematch: bool = True,
) -> list[StoreCheck]:
    session = session or make_session(
        extra_headers={"Accept-Language": "ja,en;q=0.8"}
    )
    if rematch:
        if catalog is None:
            catalog = OfficialIndex()
        if not catalog.loaded:
            catalog.load(session)
    elif catalog is None:
        catalog = OfficialIndex()

    results: list[StoreCheck] = []
    for store in STORES:
        url = store.search_url(comic)
        if not rematch:
            remembered = cached_check(cache, comic, store.store_id)
            if remembered is not None:
                results.append(remembered)
                continue
            results.append(
                StoreCheck(
                    store.store_id,
                    store.name,
                    STATUS_UNKNOWN,
                    "過去月のため再照合していません。",
                    url,
                )
            )
            continue
        if store.store_id in BULK_LISTING_STORES:
            if listings is not None and store.store_id in listings.items:
                check = listings.check(store.store_id, store.name, comic, url)
                if check.status != STATUS_YES and not listing_covers_comic(
                    store.store_id, comic
                ):
                    remembered = cached_check(cache, comic, store.store_id)
                    if remembered is not None:
                        results.append(remembered)
                        continue
                    results.append(
                        StoreCheck(
                            store.store_id,
                            store.name,
                            STATUS_UNKNOWN,
                            "新着一覧の走査範囲に未掲載のため未確認。",
                            url,
                        )
                    )
                    continue
                remember_check(cache, check, comic)
                results.append(check)
                continue
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
                    "入荷・特典一覧を取得できていません。",
                    url,
                )
            )
            continue
        official_yes, detail, official_url = lookup_status(
            catalog,
            store.store_id,
            comic.search_query,
            comic.isbn,
            url,
        )
        if official_yes == STATUS_YES and store.store_id not in (
            DETAIL_PAGE_STORES | LISTING_FETCH_STORES
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
            if official_yes == STATUS_YES:
                check = StoreCheck(
                    store.store_id, store.name, official_yes, detail, official_url
                )
                remember_check(cache, check, comic)
                results.append(check)
                continue
            remembered = cached_check(cache, comic, store.store_id)
            if remembered is not None:
                results.append(remembered)
                continue
            results.append(
                StoreCheck(
                    store.store_id,
                    store.name,
                    STATUS_UNKNOWN,
                    "新着カタログ2ページに未掲載のため未確認。",
                    url,
                )
            )
            continue
        remembered = cached_check(
            cache, comic, store.store_id, refresh_unreleased_no=fetch
        )
        if remembered is not None:
            results.append(remembered)
            continue
        needs_product_page = (
            store.store_id in DETAIL_PAGE_STORES or store.store_id in LISTING_FETCH_STORES
        )
        if needs_product_page or fetch:
            try:
                fetched = _fetch_store(store, comic, url, session)
            except Exception as exc:
                fetched = StoreCheck(
                    store.store_id,
                    store.name,
                    STATUS_UNKNOWN,
                    f"判定中に失敗: {exc}",
                    url,
                )
            if official_yes == STATUS_YES:
                fetched = _merge_official_product(
                    fetched,
                    official_status=official_yes,
                    official_detail=detail,
                    official_url=official_url,
                )
            remember_check(cache, fetched, comic)
            results.append(fetched)
            time.sleep(delay_sec)
            continue
        if official_yes == STATUS_YES:
            check = StoreCheck(
                store.store_id, store.name, official_yes, detail, official_url
            )
            remember_check(cache, check, comic)
            results.append(check)
            continue
        results.append(
            StoreCheck(
                store.store_id,
                store.name,
                STATUS_UNKNOWN,
                "未取得。リンク先の商品カードで確認してください。",
                url,
            )
        )
    return results


def _is_store_product_url(store_id: str, url: str) -> bool:
    target = url or ""
    if store_id == "melonbooks":
        return "detail.php" in target and "product_id=" in target
    if store_id == "animate":
        return (
            "/pd/" in target
            or "/pn/" in target
            or "privilege_detail.php" in target
        )
    if store_id == "toranoana":
        return "/tora/ec/item/" in target
    if store_id == "gamers":
        return "/pd/" in target or "product_id=" in target or "privilege_detail.php" in target
    if store_id == "comiczin":
        return "shop.comiczin.jp" in target and "product_id=" in target
    if store_id == "comirano":
        return "comirano.info" in target and "/category/" not in target
    return False


def _merge_official_product(
    fetched: StoreCheck,
    *,
    official_status: str,
    official_detail: str,
    official_url: str,
) -> StoreCheck:
    product_url = (
        fetched.url
        if _is_store_product_url(fetched.store_id, fetched.url)
        else official_url
    )
    if fetched.status in {STATUS_YES, STATUS_NO} and _is_store_product_url(
        fetched.store_id, fetched.url
    ):
        return fetched
    if official_status == STATUS_YES:
        return StoreCheck(
            fetched.store_id,
            fetched.store_name,
            STATUS_YES,
            official_detail,
            product_url,
        )
    return fetched


def _privilege_from_listing_card(
    html: str, detail_url: str, evaluate
) -> tuple[str, str] | None:
    if not html or not detail_url:
        return None
    markers: list[str] = []
    parsed = urlparse(detail_url)
    query = parse_qs(parsed.query)
    for key in ("product_id", "id"):
        if query.get(key) and query[key][0]:
            markers.append(query[key][0])
    for match in re.finditer(r"/(?:pd|item)/(\d+)", parsed.path, re.I):
        markers.append(match.group(1))
    if not markers:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "")
        if not any(marker in href for marker in markers):
            continue
        parent = tag.find_parent(["li", "article", "section", "div"]) or tag
        status, detail = evaluate(str(parent))
        if status == STATUS_YES:
            return status, detail.replace("詳細ページで検出", "検索カードで検出")
    return None


def _raw_first_product_url(store_id: str, html: str, page_url: str) -> str:
    markup = html or ""
    if store_id == "melonbooks":
        match = re.search(r"product_id\s*[=:]\s*[\"']?(\d+)", markup, re.I)
        if match:
            return (
                "https://www.melonbooks.co.jp/detail/detail.php?product_id="
                + match.group(1)
            )
        match = re.search(r"(?:^|\s)product_(\d+)(?:\s|$)", markup)
        if match:
            return (
                "https://www.melonbooks.co.jp/detail/detail.php?product_id="
                + match.group(1)
            )
    if store_id == "animate":
        match = re.search(r"/pd/(\d+)/?", markup, re.I)
        if match:
            return f"https://www.animate-onlineshop.jp/pd/{match.group(1)}/"
        match = re.search(r"product_id=(\d+)", markup, re.I)
        if match:
            return f"https://www.animate-onlineshop.jp/pd/{match.group(1)}/"
    if store_id == "toranoana":
        match = re.search(r"/tora/ec/item/(\d+)/?", markup, re.I)
        if match:
            return f"https://ecs.toranoana.jp/tora/ec/item/{match.group(1)}/"
    if store_id == "gamers":
        match = re.search(r"/pd/(\d+)/?", markup, re.I)
        if match:
            return f"https://www.gamers.co.jp/pd/{match.group(1)}/"
        match = re.search(r"product_id=(\d+)", markup, re.I)
        if match:
            return (
                "https://www.gamers.co.jp/products/detail.php?product_id="
                + match.group(1)
            )
    return ""


def _fetch_store(store: Store, comic: Comic, url: str, session: requests.Session) -> StoreCheck:
    if store.store_id == "melonbooks":
        return _fetch_melonbooks(comic, url, session)
    if store.store_id == "animate":
        return _fetch_animate(comic, url, session)
    if store.store_id == "toranoana":
        return _fetch_toranoana(comic, url, session)
    if store.store_id == "gamers":
        return _fetch_gamers(comic, url, session)
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
    isbn_absent = False
    try:
        for index, (list_url, from_isbn) in enumerate(attempts):
            last_search = list_url
            if index:
                time.sleep(0.8)
            if not from_isbn and isbn_absent:
                continue
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
                    isbn_absent = True
                continue
            if from_isbn:
                isbn_absent = False
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
                detail_url = _raw_first_product_url(store_id, html, list_url)
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
                listing_hit = _privilege_from_listing_card(html, detail_url, evaluate)
                if listing_hit is not None:
                    status, detail = listing_hit
                    return StoreCheck(store_id, name, status, detail, detail_url)
                continue
            if detail_resp.status_code >= 400:
                last_http = detail_resp.status_code
                listing_hit = _privilege_from_listing_card(html, detail_url, evaluate)
                if listing_hit is not None:
                    status, detail = listing_hit
                    return StoreCheck(store_id, name, status, detail, detail_url)
                continue
            if (
                store_id == "gamers"
                and not from_isbn
                and not _detail_page_matches(comic, detail_resp.text or "")
            ):
                continue
            status, detail = evaluate(detail_resp.text)
            return StoreCheck(store_id, name, status, detail, detail_url)
        if had_product_hit:
            return StoreCheck(
                store_id,
                name,
                STATUS_UNKNOWN,
                "検索ヒットあり。詳細ページを開けなかったため未確認です。",
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
        if score == 0 and not _is_gamers_listing_link(tag) and not isbn_digits:
            continue
        ranked.append((score, abs_url))
    return pick_ranked_detail_url(ranked, allow_first=bool(isbn_digits) or allow_first)


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

