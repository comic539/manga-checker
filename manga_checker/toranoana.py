"""とらのあなの検索結果 → 商品詳細ページの特典判定。"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES
from manga_checker.title_match import listing_matches_work

_ITEM_PATH = re.compile(r"/tora/ec/item/(\d+)/?", re.I)
_DETAIL_HITS = (
    "とらのあな特典",
    "とらのあな限定",
    "店舗特典",
    "購入特典",
    "特典情報",
    "描き下ろしイラストカード",
    "イラストカード",
    "描き下ろし",
    "リーフレット",
)
_NONE = re.compile(r"特典は?[な無]し|特典はありません|特典情報はありません")
_SKIP_PRIVILEGE = re.compile(r"p-benefit-floating|js-benefit-floating")


def first_toranoana_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    """検索結果から作品に一致する /tora/ec/item/ を返す。"""
    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url or "https://ecs.toranoana.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        abs_url = _toranoana_item_url(str(tag.get("href") or ""), base)
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        parent = tag.find_parent(["li", "div", "article", "section"]) or tag
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


def evaluate_toranoana_detail(html: str) -> tuple[str, str]:
    if not html:
        return STATUS_UNKNOWN, "詳細ページを取得できませんでした。"
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("#js-benefit-floating, .p-benefit-floating"):
        node.decompose()
    blocks: list[str] = []
    for node in soup.select(
        ".privilege-info, .campaign-benefit-anchor, [class*='privilege'], "
        "[id*='privilege'], [class*='tokuten'], [id*='tokuten']"
    ):
        classes = " ".join(node.get("class") or [])
        node_id = str(node.get("id") or "")
        if _SKIP_PRIVILEGE.search(classes) or _SKIP_PRIVILEGE.search(node_id):
            continue
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    heading = soup.find(string=re.compile(r"特典情報|店舗特典|購入特典|とらのあな特典"))
    if heading:
        parent = heading.find_parent(["div", "section", "table", "dl", "li", "td"]) or heading.parent
        if parent:
            text = parent.get_text(" ", strip=True)
            if text:
                blocks.append(text)
    combined = " ".join(blocks)
    detail_root = soup.select_one(".product-detail") or soup
    scope = combined or detail_root.get_text(" ", strip=True)
    if combined and _NONE.search(combined) and not any(
        word in combined for word in _DETAIL_HITS if word not in {"特典情報"}
    ):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    for word in _DETAIL_HITS:
        if word in scope:
            snippet = _snippet(scope, word)
            return STATUS_YES, f"詳細ページで検出: {snippet}"
    if combined and "特典" in combined and not _NONE.search(combined):
        return STATUS_YES, "詳細ページの特典情報エリアを検出"
    return STATUS_NO, "詳細ページに特典情報はありません。"


def _toranoana_item_url(href: str, base: str) -> str:
    match = _ITEM_PATH.search(href or "")
    if not match:
        return ""
    abs_url = urljoin(base, href).split("#")[0].split("?")[0]
    item_id = match.group(1)
    if "/item/" not in abs_url:
        return ""
    return f"https://ecs.toranoana.jp/tora/ec/item/{item_id}/"


def _snippet(text: str, word: str, radius: int = 40) -> str:
    idx = text.find(word)
    if idx < 0:
        return word
    start = max(0, idx - 8)
    end = min(len(text), idx + len(word) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()
