"""openBD に日が無いとき、楽天ブックス / Amazon の発売日を補完する。"""

from __future__ import annotations

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from manga_checker.covers import isbn13_to_isbn10
from manga_checker.dates import has_full_day, prefer_pubdate
from manga_checker.models import Comic

_SKIP_KEYS = re.compile(r"(created|modified|koukai|update|insert)", re.I)
_DATE_KEY = re.compile(r"(publication.?date|publishing.?date|published.?date|^date$)", re.I)
_RELEASE = re.compile(
    r"発売日.{0,40}?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
_RELEASE_SLASH = re.compile(
    r"発売日.{0,40}?(\d{4})[./](\d{1,2})[./](\d{1,2})"
)


def fill_missing_pubdates(comics: list[Comic], session: requests.Session) -> list[Comic]:
    missing = [c for c in comics if c.isbn and not has_full_day(c.pubdate)]
    if not missing:
        return comics
    print(f"発売日の日次を楽天ブックス/Amazonから補完しています… {len(missing)} 件")
    for i, comic in enumerate(missing, start=1):
        try:
            found = fetch_retail_pubdate(comic, session)
        except Exception as exc:
            print(f"  [{i}/{len(missing)}] {comic.search_query}: 発売日補完失敗 ({exc})")
            found = ""
        if found:
            comic.pubdate = prefer_pubdate(found, comic.pubdate)
            print(f"  [{i}/{len(missing)}] {comic.search_query}: {comic.pubdate}")
        time.sleep(0.7)
    return comics


def fetch_retail_pubdate(comic: Comic, session: requests.Session) -> str:
    digits = "".join(ch for ch in comic.isbn if ch.isdigit())
    urls: list[str] = []
    if len(digits) == 13:
        urls.append(
            "https://books.rakuten.co.jp/search?sitem=" + digits + "&g=001"
        )
        isbn10 = isbn13_to_isbn10(digits)
        if isbn10:
            urls.append(f"https://www.amazon.co.jp/dp/{isbn10}")
    for url in urls:
        html = _get(session, url)
        parsed = parse_retail_pubdate(html)
        if parsed:
            return parsed
    return ""


def parse_retail_pubdate(html: str) -> str:
    if not html:
        return ""
    for blob in _json_ld_blobs(html):
        published = _date_from_json(blob)
        if published:
            return published
    text = re.sub(r"\s+", " ", html)
    match = _RELEASE.search(text) or _RELEASE_SLASH.search(text)
    if match:
        y, m, d = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return f"{y:04d}-{m:02d}-{d:02d}"
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"property": "book:release_date"}) or soup.find(
        "meta", attrs={"itemprop": "datePublished"}
    )
    if meta and meta.get("content"):
        return str(meta.get("content"))
    return ""


def collect_onix_pubdates(record: dict) -> list[str]:
    found: list[str] = []
    _walk_dates(record, found)
    return found


def _walk_dates(obj: object, found: list[str], key: str = "") -> None:
    if isinstance(obj, dict):
        for child_key, value in obj.items():
            if _SKIP_KEYS.search(str(child_key)):
                continue
            if _DATE_KEY.search(str(child_key)):
                _take_date_value(value, found)
            _walk_dates(value, found, str(child_key))
        return
    if isinstance(obj, list):
        for item in obj:
            _walk_dates(item, found, key)


def _take_date_value(value: object, found: list[str]) -> None:
    if isinstance(value, str) and re.search(r"\d{4}", value):
        found.append(value.strip())
        return
    if isinstance(value, dict):
        raw = value.get("Date") or value.get("#text") or value.get("content") or value.get("value")
        if isinstance(raw, dict):
            raw = raw.get("#text") or raw.get("content") or ""
        if raw:
            found.append(str(raw).strip())
        for nested in value.values():
            if nested is not value:
                _take_date_value(nested, found)
        return
    if isinstance(value, list):
        for item in value:
            _take_date_value(item, found)


def _json_ld_blobs(html: str) -> list[object]:
    soup = BeautifulSoup(html or "", "html.parser")
    blobs: list[object] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            blobs.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blobs


def _date_from_json(obj: object) -> str:
    if isinstance(obj, dict):
        for key in ("datePublished", "releaseDate", "dateCreated"):
            value = obj.get(key)
            if isinstance(value, str) and re.search(r"\d{4}.\d{1,2}.\d{1,2}", value):
                if key == "dateCreated":
                    continue
                return value
        for nested in obj.values():
            found = _date_from_json(nested)
            if found:
                return found
    if isinstance(obj, list):
        for nested in obj:
            found = _date_from_json(nested)
            if found:
                return found
    return ""


def _get(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, timeout=20)
        if response.status_code >= 400:
            return ""
        return response.text
    except requests.RequestException:
        return ""
