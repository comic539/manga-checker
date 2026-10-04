"""COMIC ZIN 入荷カレンダー一覧から商品を一括取得する。"""

from __future__ import annotations

import re
import time
from calendar import monthrange
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from manga_checker.http import get_with_retry
from manga_checker.volume import normalize_text

LIST_URL = "https://shop.comiczin.jp/products/list.php"
DETAIL_URL = "https://shop.comiczin.jp/products/detail.php"
_DAY_QUERY = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_PRODUCT_ID = re.compile(r"product_id=(\d+)", re.I)
_ISBN = re.compile(r"(97[89]\d{10})")


@dataclass
class ZinItem:
    title: str
    url: str
    isbn: str = ""
    extra: str = ""


def zin_day_url(year: int, month: int, day: int) -> str:
    return f"{LIST_URL}?name={year:04d}/{month:02d}/{day:02d}"


def parse_zin_listing(html: str, page_url: str = LIST_URL) -> list[ZinItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    by_id: dict[str, ZinItem] = {}
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "")
        product_id = _product_id(href)
        if not product_id:
            continue
        url = f"{DETAIL_URL}?product_id={product_id}"
        classes = {str(value) for value in (tag.get("class") or [])}
        img = tag.find("img")
        img_alt = _usable_alt(img)
        if img_alt:
            title = img_alt
        elif "title_area" in classes:
            title = normalize_text(tag.get_text(" ", strip=True))
        else:
            title = normalize_text(tag.get_text(" ", strip=True))
        parent = tag.find_parent(["li", "div", "td", "article", "tr"]) or tag
        extra = normalize_text(parent.get_text(" ", strip=True))
        isbn = _isbn_from(parent)
        current = by_id.get(product_id)
        if current is None:
            if not title:
                continue
            by_id[product_id] = ZinItem(
                title=_clean_title(title),
                url=url,
                isbn=isbn,
                extra=extra,
            )
            continue
        if img_alt:
            current.title = _clean_title(img_alt)
        elif "title_area" in classes and title and ".." not in title:
            if ".." in current.title or len(title) > len(current.title):
                current.title = _clean_title(title)
        if isbn:
            current.isbn = isbn
        if extra and len(extra) > len(current.extra):
            current.extra = extra
    return list(by_id.values())


def calendar_days_from_html(html: str, year: int, month: int) -> list[tuple[int, int, int]]:
    found: set[tuple[int, int, int]] = set()
    for match in _DAY_QUERY.finditer(html or ""):
        y, m, d = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if (y, m) == (year, month):
            found.add((y, m, d))
    return sorted(found)


def load_comiczin_items(
    session: requests.Session,
    months: list[tuple[int, int]],
    delay_sec: float = 0.2,
) -> list[ZinItem]:
    items: list[ZinItem] = []
    seen_urls: set[str] = set()
    for year, month in months:
        seed = zin_day_url(year, month, 1)
        html = _get(session, seed)
        last = monthrange(year, month)[1]
        days = [(year, month, day) for day in range(1, last + 1)]
        if html:
            for item in parse_zin_listing(html, seed):
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    items.append(item)
        for y, m, d in days:
            if d == 1 and html:
                continue
            url = zin_day_url(y, m, d)
            page = _get(session, url)
            time.sleep(delay_sec)
            if not page:
                continue
            for item in parse_zin_listing(page, url):
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    items.append(item)
        print(f"COMIC ZIN: {year}年{month}月の入荷一覧 {len(items)} 件（累計）")
    return items


def _product_id(href: str) -> str:
    if "detail.php" not in href.lower() and "product_id=" not in href.lower():
        return ""
    abs_url = urljoin(DETAIL_URL, href)
    query = parse_qs(urlparse(abs_url).query)
    pid = (query.get("product_id") or [""])[0]
    if pid:
        return pid
    match = _PRODUCT_ID.search(abs_url)
    return match.group(1) if match else ""


def _isbn_from(node) -> str:
    blob = str(node)
    match = _ISBN.search(blob)
    return match.group(1) if match else ""


def _usable_alt(img) -> str:
    if img is None:
        return ""
    alt = normalize_text(str(img.get("alt") or ""))
    if not alt or alt in {"全年齢", "購入する", "購入不可"}:
        return ""
    return alt


def _clean_title(blob: str) -> str:
    text = normalize_text(blob)
    text = re.sub(r"\d+\s*円.*$", "", text)
    text = re.sub(r"(購入する|税込|円 \( 税込 \)|全年齢|購入不可)", " ", text)
    return normalize_text(text)[:180]


def _get(session: requests.Session, url: str) -> str:
    try:
        response = get_with_retry(session, url, timeout=20, retries=2, label="COMIC ZIN")
        if response.status_code >= 400:
            return ""
        return response.text or ""
    except requests.RequestException:
        return ""
