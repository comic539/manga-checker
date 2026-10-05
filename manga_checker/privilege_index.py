"""アニメイト／メロン／ゲーマーズ／とらのあなの特典一覧を一括取得する。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from manga_checker.dates import (
    add_months,
    iter_month_days,
    month_bounds,
    parse_release_date,
    privilege_rematch_months,
    today_jst,
    year_month_from_pubdate,
)
from manga_checker.http import get_with_retry
from manga_checker.models import Comic
from manga_checker.search_title import toranoana_search_word
from manga_checker.title_match import titles_match
from manga_checker.volume import normalize_text

ANIMATE_LIST = "https://www.animate-onlineshop.jp/products/privilege_list.php"
MELON_LIST = "https://www.melonbooks.co.jp/new/privilege.php"
MELON_LIST_LEGACY = "https://www.melonbooks.co.jp/privilege/privilege.php"
GAMERS_LIST = "https://www.gamers.co.jp/products/privilege_list.php"
TORA_CALENDAR = (
    "https://ecs.toranoana.jp/tora/ec/bok/pages/all/item/standard/calendar/{page}/"
)
TORA_BENEFIT_PAGE = (
    "https://ecs.toranoana.jp/tora/ec/bok/pages/all/announce/schedule/"
    "{year}/{month}/benefit/{page}/"
)
TORA_BENEFIT_JSON = (
    "https://contents.toranoana.jp/ec/json/benefitSchedule/bok/{year}/"
    "benefitSchedule-tora-{month}.js"
)
TORA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ecs.toranoana.jp/",
}
_COMIC_PREFIX = re.compile(r"^【[^】]*】")
_PAGEN = re.compile(r"[?&]pageno=(\d+)", re.I)
_LIMITED_EDITION = re.compile(r"『[^』]*限定版[^』]*』")
_VOLUME_SET = re.compile(r"\[全\d+冊セット\]")
_SKIP_BUNDLE = re.compile(r"全巻セット|同時購入セット")


def melon_work_title(title: str) -> str:
    """限定版・全巻セット表記を除いた照合用タイトル。"""
    text = normalize_text(title)
    text = _LIMITED_EDITION.sub(" ", text)
    text = _VOLUME_SET.sub(" ", text)
    return normalize_text(text)


@dataclass
class PrivilegeItem:
    title: str
    url: str
    extra: str = ""
    isbn: str = ""
    pubdate: str = ""


def load_animate_privileges(
    session: requests.Session,
    months: list[tuple[int, int]] | None = None,
    delay_sec: float = 1.2,
) -> list[PrivilegeItem]:
    months = months or privilege_rematch_months()
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for year, month in months:
        start, end = month_bounds(year, month)
        url = (
            f"{ANIMATE_LIST}?nf=1&mode=8&sl=80&ss=2&spc=4&spt="
            f"&start_date={start:%Y/%m/%d}&end_date={end:%Y/%m/%d}"
        )
        added = _walk_pages(
            session,
            url,
            parse_animate_privilege_list,
            seen,
            items,
            delay_sec,
            label="アニメイト特典",
        )
        print(f"アニメイト特典: {year}年{month}月 {added} 件（累計 {len(items)}）")
    return items


def parse_animate_privilege_list(
    html: str, page_url: str = ANIMATE_LIST
) -> list[PrivilegeItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for card in soup.select(".prize_list li"):
        title = ""
        for para in card.select("p.release"):
            text = normalize_text(para.get_text(" ", strip=True))
            if "発売" in text:
                continue
            if text in {"アニメイト特典", "アニメイト限定版特典", "アニメイト通販限定特典", "メーカー特典", "封入特典"}:
                continue
            if text:
                title = _COMIC_PREFIX.sub("", text).strip()
                break
        heading = card.select_one("h3 a, h3")
        extra = normalize_text(heading.get_text(" ", strip=True) if heading else "")
        link = card.select_one("a[href*='privilege_detail.php'], a[href*='/pd/']")
        href = str(link.get("href") or "") if link else ""
        url = urljoin(page_url, href).split("#")[0] if href else ""
        if not title or not url or url in seen:
            continue
        seen.add(url)
        label = extra if extra.startswith("アニメイト") else (f"アニメイト特典: {extra}" if extra else "アニメイト特典")
        items.append(PrivilegeItem(title=title, url=url, extra=label))
    return items


def load_melon_privileges(
    session: requests.Session,
    months: list[tuple[int, int]] | None = None,
    delay_sec: float = 1.2,
) -> list[PrivilegeItem]:
    months = months or privilege_rematch_months()
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    session.cookies.set("adult_check", "1", domain="www.melonbooks.co.jp")
    base = MELON_LIST
    probe_url = f"{MELON_LIST}?category=4&disp_number=100&pageno=1"
    probe_html = _get(session, probe_url, "メロン特典")
    time.sleep(delay_sec)
    if probe_html and not parse_melon_privilege_list(probe_html, probe_url):
        print("メロン特典: 新URLが空のため従来URLで取り直します")
        base = MELON_LIST_LEGACY
    for day in iter_month_days(months):
        url = (
            f"{base}?category=4&is_sp_view=&sort_type=&orderby="
            f"&disp_number=100&pageno=1&mode=&picker_date={day:%Y/%m/%d}"
        )
        before = len(items)
        added = _walk_pages(
            session,
            url,
            parse_melon_privilege_list,
            seen,
            items,
            delay_sec,
            label="メロン特典",
        )
        stamp = f"{day:%Y-%m-%d}"
        for item in items[before:]:
            if not item.pubdate:
                item.pubdate = stamp
        if day.day == 1 or added:
            print(f"メロン特典: {day:%Y/%m/%d} +{added} 件（累計 {len(items)}）")
    print(f"メロンブックス特典: {len(items)} 件")
    return items


def parse_melon_privilege_list(
    html: str, page_url: str = MELON_LIST
) -> list[PrivilegeItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for card in soup.select(".item-list li, li[class^='product_']"):
        folder = normalize_text(
            " ".join(a.get_text(" ", strip=True) for a in card.select("a[href*='category_id=']"))
        )
        if "ノベル" in folder and "コミック" not in folder:
            continue
        if "全巻セット" in folder:
            continue
        title_node = card.select_one(".product_title, .item-ttl, a[title]")
        title = ""
        if title_node:
            title = normalize_text(
                title_node.get("title") or title_node.get_text(" ", strip=True)
            )
        extra_node = card.select_one(".privilege_title")
        extra = normalize_text(extra_node.get_text(" ", strip=True) if extra_node else "")
        link = card.select_one("a[href*='detail.php'][href*='product_id=']")
        if not link:
            continue
        url = urljoin("https://www.melonbooks.co.jp/", str(link.get("href"))).split("#")[0]
        if not title:
            img = card.select_one("img[alt]")
            title = normalize_text(
                str(link.get("title") or (img.get("alt") if img else "") or link.get_text(" ", strip=True))
            )
        if not title or url in seen:
            continue
        if _SKIP_BUNDLE.search(title):
            continue
        title = melon_work_title(title) or title
        if not title:
            continue
        seen.add(url)
        items.append(PrivilegeItem(title=title, url=url, extra=extra or "メロンブックス特典"))
    return items


def load_gamers_privileges(
    session: requests.Session,
    months: list[tuple[int, int]] | None = None,
    delay_sec: float = 1.2,
) -> list[PrivilegeItem]:
    months = months or privilege_rematch_months()
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for year, month in months:
        start, end = month_bounds(year, month)
        url = (
            f"{GAMERS_LIST}?c_term=1&mode=period&spc=4&scc=166"
            f"&start_date={start:%Y/%m/%d}&end_date={end:%Y/%m/%d}&kwd=&spt=0"
        )
        added = _walk_pages(
            session,
            url,
            parse_gamers_privilege_list,
            seen,
            items,
            delay_sec,
            label="ゲーマーズ特典",
        )
        print(f"ゲーマーズ特典: {year}年{month}月 {added} 件（累計 {len(items)}）")
    return items


def parse_gamers_privilege_list(
    html: str, page_url: str = GAMERS_LIST
) -> list[PrivilegeItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for card in soup.select("li.list_product"):
        product = card.select_one("a.txt_wrap")
        title = _COMIC_PREFIX.sub(
            "", normalize_text(product.get_text(" ", strip=True) if product else "")
        ).strip()
        extra = normalize_text(
            (card.select_one("h3 a, h3") or card).get_text(" ", strip=True)
        )
        extra = extra.replace("特典", "", 1).strip() if extra.startswith("特典") else extra
        link = card.select_one("a[href*='/pd/'], a[href*='privilege_detail.php'], a.txt_wrap")
        href = str(link.get("href") or "") if link else ""
        url = urljoin(page_url, href).split("#")[0] if href else ""
        if not title or not url or url in seen:
            continue
        seen.add(url)
        items.append(
            PrivilegeItem(
                title=title,
                url=url,
                extra=f"ゲーマーズ特典: {extra}" if extra else "ゲーマーズ特典",
            )
        )
    return items


def catalog_issue_dates(
    comics: list[Comic],
    months: list[tuple[int, int]] | None = None,
) -> list[str]:
    """カタログの発売日から YYYYMMDD のユニーク一覧を作る。"""
    allowed = set(months) if months else None
    found: set[str] = set()
    for comic in comics:
        parsed = parse_release_date(comic.pubdate)
        if parsed is None:
            continue
        if allowed is not None and (parsed.year, parsed.month) not in allowed:
            continue
        found.add(parsed.strftime("%Y%m%d"))
    return sorted(found)


def load_toranoana_privileges(
    session: requests.Session,
    months: list[tuple[int, int]] | None = None,
    delay_sec: float = 1.0,
    issue_dates: list[str] | None = None,
    comics: list[Comic] | None = None,
) -> list[PrivilegeItem]:
    del issue_dates
    del months
    today = today_jst()
    current = (today.year, today.month)
    next_month = add_months(today.year, today.month, 1)
    items: list[PrivilegeItem] = []
    seen: set[str] = set()

    print(f"とらのあな特典: 当月カレンダー {current[0]}年{current[1]}月を取得します")
    year, month = current
    page_url = TORA_BENEFIT_PAGE.format(year=year, month=f"{month:02d}", page=1)
    html = _get_tora(session, page_url, f"とらのあな特典カレンダー {year}/{month:02d}")
    time.sleep(delay_sec)
    for item in _load_toranoana_month_json(session, year, month):
        if item.url in seen:
            continue
        seen.add(item.url)
        items.append(item)
    time.sleep(delay_sec)
    if html:
        for item in parse_toranoana_calendar(html, page_url):
            if item.url in seen:
                continue
            seen.add(item.url)
            items.append(item)
    print(f"  当月カレンダー {len(items)} 件")

    future_comics = [
        comic
        for comic in (comics or [])
        if year_month_from_pubdate(comic.pubdate) == next_month
    ]
    print(f"とらのあな特典: 翌月タイトル検索 {len(future_comics)} 件")
    for comic in future_comics:
        item = search_toranoana_title_privilege(session, comic, delay_sec=delay_sec)
        if item is None or item.url in seen:
            continue
        seen.add(item.url)
        items.append(item)
    print(f"とらのあな特典: {len(items)} 件")
    return items


def search_toranoana_title_privilege(
    session: requests.Session,
    comic: Comic,
    delay_sec: float = 1.0,
) -> PrivilegeItem | None:
    word = toranoana_search_word(comic.title, comic.volume) or comic.search_query
    if not word:
        return None
    url = (
        "https://ecs.toranoana.jp/tora/ec/app/catalog/list/"
        f"?searchWord={quote(word)}&searchCategoryCode=bok"
    )
    html = _get_tora(session, url, f"とらのあな検索 {word}")
    time.sleep(delay_sec)
    if not html:
        return None
    for item in parse_toranoana_calendar(html, url):
        blob = f"{item.title} {item.extra}"
        if titles_match(comic.search_query, blob, comic.isbn, comic.author):
            return item
        if titles_match(comic.title, blob, comic.isbn, comic.author):
            return item
    return None


def _load_toranoana_month_json(
    session: requests.Session, year: int, month: int
) -> list[PrivilegeItem]:
    url = TORA_BENEFIT_JSON.format(year=year, month=f"{month:02d}")
    raw = _get_tora(session, url, f"とらのあな特典JSON {year}/{month:02d}")
    if not raw:
        return []
    return parse_toranoana_benefit_json(raw)


def parse_toranoana_benefit_json(raw: str) -> list[PrivilegeItem]:
    text = (raw or "").strip()
    match = re.search(r"^[^(]+\((.*)\)\s*;?\s*$", text, re.S)
    payload = match.group(1) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for row in data.get("list") or []:
        title = normalize_text(str(row.get("title") or ""))
        title_id = str(row.get("titleId") or "").strip()
        extra = normalize_text(str(row.get("benefit") or ""))
        if not title or not title_id:
            continue
        url = f"https://ecs.toranoana.jp/tora/ec/item/{title_id}/"
        if url in seen:
            continue
        seen.add(url)
        items.append(PrivilegeItem(title=title, url=url, extra=extra or "特典付き"))
    return items


def parse_toranoana_calendar(
    html: str, page_url: str = TORA_CALENDAR.format(page=1)
) -> list[PrivilegeItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[PrivilegeItem] = []
    seen: set[str] = set()
    for card in soup.select("li.product-list-item, .catalog-item-card"):
        heading = card.select_one("h3.product-list-title a, .product-list-title a")
        if heading is None:
            heading = card.select_one("a[href*='/tora/ec/item/']")
        if heading is None:
            continue
        title = normalize_text(
            heading.get_text(" ", strip=True) or heading.get("title") or ""
        )
        href = str(heading.get("href") or "")
        url = urljoin("https://ecs.toranoana.jp/", href).split("#")[0]
        if "/tora/ec/item/" not in url or not title or url in seen:
            continue
        seen.add(url)
        extra = normalize_text(
            " ".join(span.get_text(" ", strip=True) for span in card.select(".product-list-labels li"))
        )
        items.append(
            PrivilegeItem(title=title, url=url, extra=extra or "特典付き")
        )
    return items


def _walk_pages(
    session: requests.Session,
    start_url: str,
    parser,
    seen: set[str],
    items: list[PrivilegeItem],
    delay_sec: float,
    label: str,
    max_pages: int = 40,
) -> int:
    url = start_url
    added_total = 0
    for _ in range(max_pages):
        html = _get(session, url, label)
        time.sleep(delay_sec)
        if not html:
            break
        page_items = parser(html, url)
        added = 0
        for item in page_items:
            if item.url in seen:
                continue
            seen.add(item.url)
            items.append(item)
            added += 1
            added_total += 1
        nxt = _next_page_url(html, url)
        if not nxt or nxt == url or added == 0:
            break
        url = nxt
    return added_total


def _keep_list_query(current_url: str, next_url: str) -> str:
    """ページャが category / picker_date を落とすので、現在の絞り込みを引き継ぐ。"""
    current = urlparse(current_url)
    nxt = urlparse(next_url)
    query = dict(parse_qsl(current.query, keep_blank_values=True))
    next_query = dict(parse_qsl(nxt.query, keep_blank_values=True))
    if "pageno" in next_query:
        query["pageno"] = next_query["pageno"]
    path = nxt.path or current.path
    return urljoin(
        f"{current.scheme}://{current.netloc}{path}",
        "?" + urlencode(query),
    )


def _next_page_url(html: str, page_url: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    current = _page_number(page_url)
    best = ""
    best_n = current
    for tag in soup.select("a[href*='pageno=']"):
        href = urljoin(page_url, str(tag.get("href") or "")).split("#")[0]
        number = _page_number(href)
        if number == current + 1:
            return _keep_list_query(page_url, href)
        if number > best_n:
            best_n = number
            best = href
    nxt = soup.select_one("a.next, p.next a, .content_pager a")
    text = normalize_text(nxt.get_text(" ", strip=True) if nxt else "")
    if nxt and "次" in text and nxt.get("href"):
        return _keep_list_query(
            page_url, urljoin(page_url, str(nxt.get("href"))).split("#")[0]
        )
    return _keep_list_query(page_url, best) if best_n > current else ""


def _page_number(url: str) -> int:
    match = _PAGEN.search(url or "")
    return int(match.group(1)) if match else 1


def _tora_max_page(html: str) -> int:
    soup = BeautifulSoup(html or "", "html.parser")
    pager = soup.select_one("#pager")
    if pager and pager.get("data-maxpage"):
        try:
            return max(1, int(str(pager.get("data-maxpage"))))
        except ValueError:
            return 1
    return 1


def _get(session: requests.Session, url: str, label: str) -> str:
    try:
        response = get_with_retry(session, url, timeout=25, retries=2, label=label)
        if response.status_code >= 400:
            return ""
        return response.text or ""
    except requests.RequestException:
        return ""


def _get_tora(session: requests.Session, url: str, label: str) -> str | None:
    try:
        response = get_with_retry(
            session,
            url,
            timeout=25,
            retries=2,
            headers=TORA_HEADERS,
            label=label,
        )
    except requests.RequestException as exc:
        print(f"  とらのあな: 例外のためスキップ {label}: {exc}")
        return None
    if response.status_code >= 400:
        print(f"  とらのあな: HTTP {response.status_code} のためスキップ {label}")
        return None
    return response.content.decode("utf-8", errors="replace") if response.content else ""
