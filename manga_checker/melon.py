"""メロンブックスの検索結果 → 商品詳細ページの特典判定。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES
from manga_checker.title_match import listing_matches_work

_DETAIL_HREF = re.compile(r"detail\.php", re.I)
_PRODUCT_ID = re.compile(r"(?:[?&](?:product_)?id=)(\d+)", re.I)
_BOX_CONCRETE = (
    "メロンブックス特典",
    "メロンブックス限定",
    "メロン限定版",
    "メロン限定",
    "描き下ろしイラストカード",
    "イラストカード",
    "描き下ろし",
    "リーフレット",
    "特典ペーパー",
    "有償特典",
    "アクリルスタンド",
    "ブロマイド",
    "購入特典",
    "店舗特典",
    "特典付き",
    "特典付",
    "特典（",
    "【特典",
)
_PAGE_CONCRETE = (
    "メロンブックス特典",
    "メロンブックス限定",
    "メロン限定版",
    "メロン限定",
    "描き下ろしイラストカード",
    "描き下ろし",
    "有償特典",
    "購入特典",
    "店舗特典",
    "特典ペーパー",
    "特典付き",
    "特典付",
    "特典（",
    "【特典",
    "特典",
)
_ENDED = re.compile(
    r"特典.{0,12}(なし|無し|終了|ございません|ありません|お付けできません)|"
    r"(なし|無し|終了).{0,8}特典|"
    r"配布終了"
)
_RELATED_ATTR = re.compile(
    r"(recommend|related|relation|carousel|other[_-]?item|also[_-]?buy)",
    re.I,
)
_RELATED_HEADING = re.compile(
    r"このレーベルの他の作品|この作家の他の作品|この作者の他の作品|"
    r"関連商品|おすすめ商品|おすすめの商品|一緒に購入|"
    r"最近チェック|閲覧履歴|他のお客様"
)
_MAIN_SELECTORS = (
    ".item_detail",
    "#item_detail",
    ".item-detail",
    "#item",
    ".product_detail",
    ".product-detail",
    ".detail_data",
    "#detail",
    "#contents",
)
_MAIN_WRAPPER_IDS = frozenset({"contents", "item", "item_detail", "detail", "wrapper"})


def first_melon_detail_url(
    html: str,
    page_url: str,
    title: str = "",
    isbn: str = "",
    author: str = "",
    allow_first: bool = False,
) -> str:
    """検索結果から作品に一致する detail.php?product_id= を返す。"""
    soup = BeautifulSoup(html or "", "html.parser")
    base = page_url or "https://www.melonbooks.co.jp/"
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    isbn_digits = re.sub(r"\D", "", isbn or "")
    for tag in soup.find_all("a", href=True):
        abs_url = _melon_detail_url(str(tag.get("href") or ""), base)
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
    ranked.sort(key=lambda item: item[0], reverse=True)
    matching = [url for score, url in ranked if score]
    if matching:
        return matching[0]
    if (allow_first or len(isbn_digits) >= 10) and ranked:
        return ranked[0][1]
    return ""


def evaluate_melon_detail(html: str) -> tuple[str, str]:
    if not html:
        return STATUS_UNKNOWN, "詳細ページを取得できませんでした。"
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("header", "footer", "nav", "aside")):
        tag.decompose()
    _decompose_related(soup)
    root = _main_product_root(soup)
    blocks: list[str] = []
    for node in root.select(
        ".privilege, .privilege_box, [class*='privilege'], [id*='privilege'], "
        ".tokuten_box, [class*='tokuten'], [id*='tokuten']"
    ):
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    heading = root.find(string=re.compile(r"特典情報|店舗特典|購入特典"))
    if heading:
        parent = heading.find_parent(["div", "section", "table", "dl", "li", "td"])
        if parent and parent.name not in {"body", "html"}:
            text = parent.get_text(" ", strip=True)
            if text and len(text) <= 2500:
                blocks.append(text)
    for spec in root.select("table, .item_spec, .spec, dl"):
        text = spec.get_text(" ", strip=True)
        if text and ("特典" in text or "限定" in text) and len(text) <= 4000:
            blocks.append(text)
    combined = " ".join(dict.fromkeys(blocks))
    if combined and _ENDED.search(combined) and not _concrete_hits(combined, _BOX_CONCRETE):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    hits = _concrete_hits(combined, _BOX_CONCRETE)
    if hits:
        snippet = _snippet(combined, hits[0])
        return STATUS_YES, f"詳細ページで検出: {snippet}"
    body = root.get_text(" ", strip=True)
    if _ENDED.search(body) and not _concrete_hits(body, _PAGE_CONCRETE):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    body_hits = _concrete_hits(body, _PAGE_CONCRETE)
    if body_hits:
        snippet = _snippet(body, body_hits[0])
        return STATUS_YES, f"詳細ページで検出: {snippet}"
    return STATUS_NO, "詳細ページに特典情報はありません。"


def _decompose_related(soup: BeautifulSoup) -> None:
    to_drop = []
    for tag in soup.find_all(True):
        cid = f"{tag.get('id') or ''} {' '.join(tag.get('class') or [])}"
        if _RELATED_ATTR.search(cid):
            to_drop.append(tag)
    for tag in to_drop:
        if tag.parent is not None:
            tag.decompose()
    for node in list(soup.find_all(string=_RELATED_HEADING)):
        heading = node.parent
        if heading is None or getattr(heading, "name", None) in {"body", "html", "[document]"}:
            continue
        for sib in list(heading.find_next_siblings()):
            if getattr(sib, "name", None) in {"h1", "h2"}:
                break
            sib.decompose()
        box = heading.find_parent(["section", "aside", "ul", "div"])
        if box is not None and not _is_main_wrapper(box) and box.find(string=_RELATED_HEADING):
            box.decompose()
        elif heading.name not in {"body", "html"}:
            heading.decompose()


def _is_main_wrapper(tag) -> bool:
    if tag is None or tag.name in {"body", "html", "[document]"}:
        return True
    tid = str(tag.get("id") or "").lower()
    tclass = " ".join(tag.get("class") or []).lower()
    if tid in _MAIN_WRAPPER_IDS:
        return True
    return "item_detail" in tclass or "item-detail" in tclass or "product_detail" in tclass


def _main_product_root(soup: BeautifulSoup):
    for selector in _MAIN_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup


def _concrete_hits(text: str, words: tuple[str, ...] = _BOX_CONCRETE) -> list[str]:
    hits: list[str] = []
    for word in words:
        if word in text and word not in hits:
            hits.append(word)
    return hits


def _melon_detail_url(href: str, base: str) -> str:
    if not href:
        return ""
    if not _DETAIL_HREF.search(href) and not _PRODUCT_ID.search(href):
        return ""
    abs_url = urljoin(base, href).split("#")[0]
    parsed = urlparse(abs_url)
    query = parse_qs(parsed.query)
    product_id = (query.get("product_id") or query.get("id") or [""])[0]
    if not product_id:
        match = _PRODUCT_ID.search(abs_url)
        if match:
            product_id = match.group(1)
    if not product_id:
        return ""
    if "detail.php" not in parsed.path.lower() and not query.get("product_id"):
        return ""
    return f"https://www.melonbooks.co.jp/detail/detail.php?product_id={product_id}"


def _snippet(text: str, word: str, radius: int = 40) -> str:
    idx = text.find(word)
    if idx < 0:
        return word
    start = max(0, idx - 8)
    end = min(len(text), idx + len(word) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()
