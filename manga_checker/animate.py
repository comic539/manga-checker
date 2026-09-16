"""アニメイトの検索結果 → 商品詳細ページ（/pd/数字/）の特典判定。"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES
from manga_checker.title_match import listing_matches_work

_PD_PATH = re.compile(r"/pd/(\d+)/?", re.I)
_DETAIL_HITS = (
    "特典について",
    "アニメイト特典",
    "描き下ろしイラストカード",
    "イラストカード",
    "描き下ろし",
)
_NONE = re.compile(r"特典は?[な無]し|特典はありません|特典の設定はありません")


def first_animate_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    """検索結果から作品に一致する /pd/ URL を返す。"""
    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url or "https://www.animate-onlineshop.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        abs_url = _animate_pd_url(str(tag.get("href") or ""), base)
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        parent = tag.find_parent(["li", "div", "article", "td", "section"]) or tag
        blob = " ".join(
            part for part in (tag.get_text(" ", strip=True), parent.get_text(" ", strip=True)) if part
        )
        score = 2 if listing_matches_work(title, blob, isbn, author=author) else 0
        ranked.append((score, abs_url))
    ranked.sort(key=lambda item: item[0], reverse=True)
    matching = [url for score, url in ranked if score]
    if matching:
        return matching[0]
    isbn_digits = re.sub(r"\D", "", isbn or "")
    if (allow_first or len(isbn_digits) >= 10) and ranked:
        return ranked[0][1]
    return ""


def evaluate_animate_detail(html: str) -> tuple[str, str]:
    if not html:
        return STATUS_UNKNOWN, "詳細ページを取得できませんでした。"
    soup = BeautifulSoup(html, "html.parser")
    blocks: list[str] = []
    for node in soup.select(
        "#tokuten, [id='tokuten'], [id*='tokuten'], "
        "[class*='tokuten'], .item_tokuten, [class*='privilege']"
    ):
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    heading = soup.find(string=re.compile(r"特典について|アニメイト特典"))
    if heading:
        parent = heading.find_parent(["div", "section", "table", "dl", "li", "td"]) or heading.parent
        if parent:
            text = parent.get_text(" ", strip=True)
            if text:
                blocks.append(text)
    combined = " ".join(blocks)
    raw = html or ""
    scope = combined or soup.get_text(" ", strip=True)
    if combined and _NONE.search(combined) and not any(word in combined for word in _DETAIL_HITS[2:]):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    for word in _DETAIL_HITS:
        if word in scope or word in raw:
            snippet = _snippet(scope if word in scope else raw, word)
            return STATUS_YES, f"詳細ページで検出: {snippet}"
    if re.search(r"tokuten", raw, re.I) and not _NONE.search(scope):
        return STATUS_YES, "詳細ページで検出: tokuten"
    if soup.select_one("#tokuten") and combined and not _NONE.search(combined):
        return STATUS_YES, "詳細ページの #tokuten ブロックを検出"
    return STATUS_NO, "詳細ページに特典情報はありません。"


def _animate_pd_url(href: str, base: str) -> str:
    match = _PD_PATH.search(href or "")
    if not match:
        return ""
    abs_url = urljoin(base, href).split("#")[0].split("?")[0]
    product_id = match.group(1)
    return f"https://www.animate-onlineshop.jp/pd/{product_id}/"


def _snippet(text: str, word: str, radius: int = 40) -> str:
    idx = text.find(word)
    if idx < 0:
        return word
    start = max(0, idx - 8)
    end = min(len(text), idx + len(word) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()
