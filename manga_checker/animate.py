"""アニメイトの検索結果 → 商品詳細ページの特典判定。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from manga_checker.privilege import evaluate_detail_privilege, pick_ranked_detail_url
from manga_checker.title_match import listing_matches_work

_PD_PATH = re.compile(r"/pd/(\d+)/?", re.I)
_PN_PATH = re.compile(r"/pn/[^/]+/(\d+)/?", re.I)
_PRODUCT_ID = re.compile(r"(?:[?&]product_id=)(\d+)", re.I)
_DETAIL_PATH = re.compile(r"/products/detail\.php", re.I)


def first_animate_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    """検索結果から商品詳細 URL（/pd/・/pn/ または product_id）を返す。"""
    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url or "https://www.animate-onlineshop.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    isbn_digits = re.sub(r"\D", "", isbn or "")
    for tag in soup.find_all("a", href=True):
        abs_url = _animate_detail_url(str(tag.get("href") or ""), base)
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
        ranked.append((score, abs_url))
    for match in _PD_PATH.finditer(html or ""):
        abs_url = f"https://www.animate-onlineshop.jp/pd/{match.group(1)}/"
        if abs_url not in seen:
            seen.add(abs_url)
            ranked.append((0, abs_url))
    for match in _PN_PATH.finditer(html or ""):
        abs_url = f"https://www.animate-onlineshop.jp/pd/{match.group(1)}/"
        if abs_url not in seen:
            seen.add(abs_url)
            ranked.append((0, abs_url))
    for tag in soup.find_all(attrs={"data-product_id": True}):
        pid = str(tag.get("data-product_id") or "")
        if pid.isdigit():
            abs_url = f"https://www.animate-onlineshop.jp/pd/{pid}/"
            if abs_url not in seen:
                seen.add(abs_url)
                ranked.append((0, abs_url))
    return pick_ranked_detail_url(ranked, allow_first=True)


def evaluate_animate_detail(html: str) -> tuple[str, str]:
    return evaluate_detail_privilege(html)


def _animate_detail_url(href: str, base: str) -> str:
    if not href:
        return ""
    abs_url = urljoin(base, href).split("#")[0]
    pd = _PD_PATH.search(abs_url)
    if pd:
        return f"https://www.animate-onlineshop.jp/pd/{pd.group(1)}/"
    pn = _PN_PATH.search(abs_url)
    if pn:
        return f"https://www.animate-onlineshop.jp/pd/{pn.group(1)}/"
    parsed = urlparse(abs_url)
    query = parse_qs(parsed.query)
    product_id = (query.get("product_id") or [""])[0]
    if not product_id:
        match = _PRODUCT_ID.search(abs_url)
        if match:
            product_id = match.group(1)
    if product_id and (_DETAIL_PATH.search(parsed.path) or query.get("product_id")):
        return (
            "https://www.animate-onlineshop.jp/products/detail.php"
            f"?product_id={product_id}"
        )
    if product_id:
        return f"https://www.animate-onlineshop.jp/pd/{product_id}/"
    return ""
