"""こみらの！特典付きコミック一覧を一括取得する。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from manga_checker.http import get_with_retry
from manga_checker.volume import normalize_text

COMIC_LIST_URL = "https://comirano.info/category/comic/"
HOME_URL = "https://comirano.info/"


@dataclass
class ComiranoItem:
    title: str
    url: str
    extra: str = ""


def parse_comirano_listing(html: str, page_url: str = COMIC_LIST_URL) -> list[ComiranoItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[ComiranoItem] = []
    seen: set[str] = set()
    links = soup.select("h2.omc-blog-one-heading a[href]")
    if not links:
        links = [
            heading.find("a", href=True)
            for heading in soup.select("article h2")
            if heading.find("a", href=True)
        ]
    for link in links:
        if link is None:
            continue
        href = str(link.get("href") or "")
        if not href:
            continue
        url = urljoin(page_url, href).split("#")[0]
        if not _is_comirano_post(url):
            continue
        title = normalize_text(link.get_text(" ", strip=True))
        if not title or url in seen:
            continue
        article = link.find_parent("article")
        extra = _comirano_extra(article, title)
        seen.add(url)
        items.append(ComiranoItem(title=title, url=url, extra=extra))
    return items


def _comirano_extra(article, title: str) -> str:
    if article is None:
        return title
    for node in article.select("li, p, span"):
        text = normalize_text(node.get_text(" ", strip=True))
        if text.startswith("特典"):
            return text[:120]
    blob = normalize_text(article.get_text(" ", strip=True))
    match = re.search(r"特典[：:]\s*\S+", blob)
    if match:
        return match.group(0)[:120]
    return title


def _is_comirano_post(url: str) -> bool:
    if "comirano.info" not in url:
        return False
    if url.rstrip("/") in {COMIC_LIST_URL.rstrip("/"), HOME_URL.rstrip("/")}:
        return False
    if "/category/" in url or "/tag/" in url or "?cat=" in url:
        return False
    return True


def next_comirano_page(html: str, page_url: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    link = soup.select_one("a.next, a[rel='next'], .pagination a.next")
    if link and link.get("href"):
        return urljoin(page_url, str(link.get("href")))
    match = re.search(r"/page/(\d+)/?", urlparse_path(page_url))
    current = int(match.group(1)) if match else 1
    candidate = urljoin(COMIC_LIST_URL, f"page/{current + 1}/")
    if candidate in (html or "") or f"page/{current + 1}" in (html or ""):
        return candidate
    return ""


def urlparse_path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path


def load_comirano_items(
    session: requests.Session,
    delay_sec: float = 0.25,
    max_pages: int = 40,
) -> list[ComiranoItem]:
    items: list[ComiranoItem] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = COMIC_LIST_URL if page == 1 else urljoin(COMIC_LIST_URL, f"page/{page}/")
        html = _get(session, url)
        if not html:
            break
        page_items = parse_comirano_listing(html, url)
        added = 0
        for item in page_items:
            if item.url in seen:
                continue
            seen.add(item.url)
            items.append(item)
            added += 1
        if added == 0:
            break
        time.sleep(delay_sec)
    print(f"こみらの！: 特典付きコミック {len(items)} 件")
    return items


def _get(session: requests.Session, url: str) -> str:
    try:
        response = get_with_retry(session, url, timeout=20, retries=2, label="こみらの")
        if response.status_code >= 400:
            return ""
        return response.text or ""
    except requests.RequestException:
        return ""
