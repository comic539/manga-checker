"""検索一覧では特典判定せず、商品詳細ページの本文だけを見る。"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from manga_checker.product_cards import extract_product_card_texts
from manga_checker.title_match import titles_match

_STRONG_PRIVILEGE = [
    re.compile(r"特典あり"),
    re.compile(r"購入特典"),
    re.compile(r"店舗特典"),
    re.compile(r"有償特典"),
    re.compile(r"限定特典"),
    re.compile(r"メロン限定版"),
    re.compile(r"メロンブックス限定"),
    re.compile(r"メロンブックス特典"),
    re.compile(r"アニメイト特典"),
    re.compile(r"ゲーマーズ特典"),
    re.compile(r"ゲーマーズ限定"),
    re.compile(r"とらのあな特典"),
    re.compile(r"とらのあな限定"),
    re.compile(r"喜久屋特典"),
    re.compile(r"特典付"),
    re.compile(r"特典付き"),
    re.compile(r"【特典"),
    re.compile(r"特典（"),
    re.compile(r"特典\("),
    re.compile(r"特典ペーパー"),
    re.compile(r"イラストペーパー"),
    re.compile(r"イラストカード"),
    re.compile(r"リーフレット"),
    re.compile(r"描き下ろし"),
    re.compile(r"ブロマイド"),
    re.compile(r"G特典"),
    re.compile(r"icon_present", re.IGNORECASE),
    re.compile(r"icon_tokuten", re.IGNORECASE),
    re.compile(r"アクリルスタンド"),
    re.compile(r"メロン限定"),
]

_NEGATIONS = [
    re.compile(r"特典なし"),
    re.compile(r"特典無し"),
    re.compile(r"特典配布終了"),
    re.compile(r"【特典なし】"),
    re.compile(r"特典は終了"),
    re.compile(r"特典終了"),
    re.compile(r"特典はございません"),
    re.compile(r"特典はありません"),
    re.compile(r"特典情報はありません"),
    re.compile(r"特典はお付けできません"),
]

_ENDED_PRIVILEGE = re.compile(
    r"特典.{0,12}(なし|無し|終了|ございません|ありません|お付けできません)|"
    r"(なし|無し|終了).{0,8}特典|"
    r"配布終了"
)

_NO_HIT_PHRASES = (
    "該当する商品はございません",
    "見つかりませんでした",
    "検索結果はありません",
    "該当する商品は見つかりませんでした",
    "お探しの商品は見つかりません",
    "条件に一致する商品は見つかりませんでした",
    "一致する商品は見つかりませんでした",
    "商品が見つかりませんでした",
    "お取り扱いはございません",
    "商品のお取り扱いはございません",
)
_NO_HIT_COUNT = re.compile(
    r"(商品|検索結果|該当)[^。\n]{0,24}[（(]?0\s*件|[（(]0件[）)]"
)

_MELON_CONCRETE = (
    "メロン限定版",
    "メロンブックス限定",
    "メロンブックス特典",
    "メロン限定",
    "描き下ろしイラストカード",
    "イラストカード",
    "描き下ろし",
    "リーフレット",
    "アクリルスタンド",
    "有償特典",
    "特典ペーパー",
    "特典付き",
    "特典付",
    "購入特典",
    "店舗特典",
    "特典（",
    "【特典",
)

_KINO_YES = re.compile(r"特典|限定|ペーパー|イラストカード")
_KINO_CHROME = re.compile(
    r"(header|footer|global.?nav|gnav|utility|member|login|topicpath|"
    r"breadcrumb|sidemenu|side_nav)",
    re.I,
)

STATUS_YES = "特典あり"
STATUS_NO = "特典なし"
STATUS_UNKNOWN = "未確認"

_DETAIL_BLOCK_WORDS = (
    "有償特典",
    "購入特典",
    "店舗特典",
    "特典ペーパー",
    "描き下ろし",
    "ペーパー",
    "特典",
    "限定",
)
_DETAIL_BODY_WORDS = (
    "有償特典",
    "購入特典",
    "特典ペーパー",
    "描き下ろし",
    "イラストカード",
    "アニメイト特典",
    "メロンブックス特典",
    "とらのあな特典",
)

_DETAIL_NONE = re.compile(
    r"特典は?[な無]し|特典はありません|特典情報はありません|特典の設定はありません|"
    r"特典はお付けできません|特典をお付けできません"
)

_PRODUCT_HREF = re.compile(
    r"/pd/\d+|/pn/[^\"'\\s]+/\d+|product_id=\d+|detail\.php|/tora/ec/item/\d+|/f/dsg-01-\d+",
    re.I,
)


def pick_ranked_detail_url(
    ranked: list[tuple[int, str]], allow_first: bool = True
) -> str:
    if not ranked:
        return ""
    ordered = sorted(ranked, key=lambda item: item[0], reverse=True)
    matching = [url for score, url in ordered if score]
    if matching:
        return matching[0]
    if allow_first:
        return ordered[0][1]
    return ""


_CAMPAIGN_FAIR = re.compile(r"特典箱フェア")


def _strip_campaign_fair(soup: BeautifulSoup) -> None:
    """ゲーマーズの『特典箱フェア』案内は店舗特典ではない。"""
    for node in soup.select("#fp_fair, [id*='fp_fair']"):
        node.decompose()
    for heading in soup.find_all(["h2", "h3", "h4", "p", "strong"]):
        text = heading.get_text(" ", strip=True)
        if "特典箱フェア" not in text:
            continue
        parent = heading.find_parent(["div", "section", "article"]) or heading
        parent.decompose()


def _is_campaign_fair_text(text: str) -> bool:
    if not text or not _CAMPAIGN_FAIR.search(text):
        return False
    remainder = _CAMPAIGN_FAIR.sub(" ", text)
    return not any(word in remainder for word in ("描き下ろし", "ゲーマーズ特典", "店舗特典", "購入特典"))


def evaluate_detail_privilege(html: str) -> tuple[str, str]:
    """商品個別ページの本文・特典ブロックだけを判定する。"""
    if not html:
        return STATUS_UNKNOWN, "詳細ページを取得できませんでした。"
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("header", "footer", "nav", "aside")):
        tag.decompose()
    _strip_campaign_fair(soup)
    blocks: list[str] = []
    for node in soup.select(
        "#tokuten, [id*='tokuten'], [class*='tokuten'], [class*='privilege'], "
        "[id*='privilege'], .privilege-info, .item_tokuten"
    ):
        text = node.get_text(" ", strip=True)
        if text and not _is_campaign_fair_text(text):
            blocks.append(text)
    body = soup.get_text(" ", strip=True)
    attrs: list[str] = []
    for tag in soup.find_all(True):
        for attr in ("alt", "title", "aria-label"):
            value = str(tag.get(attr) or "").strip()
            if value and not _is_campaign_fair_text(value):
                attrs.append(value)
    attr_blob = " ".join(attrs)
    scope = " ".join(dict.fromkeys([*blocks, attr_blob] if attr_blob else blocks))
    haystack = scope or f"{body} {attr_blob}".strip()
    haystack = _CAMPAIGN_FAIR.sub(" ", haystack)
    if _DETAIL_NONE.search(haystack) and not any(
        word in haystack for word in ("描き下ろし", "ペーパー", "有償特典")
    ):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    words = _DETAIL_BLOCK_WORDS if scope else _DETAIL_BODY_WORDS
    for word in words:
        if word in haystack:
            snippet = _snippet(haystack, word)
            return STATUS_YES, f"詳細ページで検出: {snippet}"
    return STATUS_NO, "詳細ページに特典情報はありません。"


_GAMERS_YES_WORDS = ("特典情報", "ゲーマーズ特典")


def evaluate_gamers_detail(html: str) -> tuple[str, str]:
    """ゲーマーズは商品ページの『特典情報』または『ゲーマーズ特典』だけを特典ありにする。"""
    if not html:
        return STATUS_UNKNOWN, "詳細ページを取得できませんでした。"
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("header", "footer", "nav", "aside")):
        tag.decompose()
    _strip_campaign_fair(soup)
    haystack = _CAMPAIGN_FAIR.sub(" ", soup.get_text(" ", strip=True))
    if _DETAIL_NONE.search(haystack):
        return STATUS_NO, "詳細ページに特典情報はありません。"
    for word in _GAMERS_YES_WORDS:
        if word in haystack:
            return STATUS_YES, f"詳細ページで検出: {_snippet(haystack, word)}"
    return STATUS_NO, "詳細ページに特典情報はありません。"


def _snippet(text: str, word: str, radius: int = 40) -> str:
    idx = text.find(word)
    if idx < 0:
        return word
    start = max(0, idx - 8)
    end = min(len(text), idx + len(word) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def listing_has_products(html: str) -> bool:
    markup = html or ""
    if search_is_no_hit(markup):
        return False
    if _PRODUCT_HREF.search(markup):
        return True
    soup = BeautifulSoup(markup, "html.parser")
    return bool(
        soup.select(
            ".item_list .item, .product-list-item, ul.item_list li.item, "
            ".product_list > .product, .product_list .product_item"
        )
    )


def search_is_no_hit(html: str) -> bool:
    """検索結果ページが『0件』と明示しているか。"""
    text = html or ""
    if any(phrase in text for phrase in _NO_HIT_PHRASES):
        return True
    return bool(_NO_HIT_COUNT.search(text))


def evaluate_privilege(
    html: str,
    *,
    title_for_match: str,
    isbn: str = "",
    author: str = "",
    source_url: str = "",
    store_id: str = "",
    http_ok: bool = True,
) -> tuple[str, str]:
    """一覧ページでは特典ありにしない。詳細URLは stores 側で辿る。"""
    if not http_ok:
        return STATUS_UNKNOWN, "ページを取得できませんでした。"

    source = source_url or ""
    if "detail.php" in source or "/pd/" in source or "/pn/" in source or "/tora/ec/item/" in source:
        if store_id == "melonbooks" or "melonbooks.co.jp" in source:
            from manga_checker.melon import evaluate_melon_detail

            return evaluate_melon_detail(html)
        if store_id == "gamers" or "gamers.co.jp" in source:
            return evaluate_gamers_detail(html)
        return evaluate_detail_privilege(html)

    if store_id == "kinokuniya" or "kinokuniya.co.jp" in source:
        if "/f/dsg-01-" in source:
            return evaluate_detail_privilege(html)
        if listing_has_products(html) or _kinokuniya_product_titles(
            html, title_for_match, isbn, author=author
        ):
            return STATUS_NO, "検索ヒットあり。一覧では特典判定しません。"
        if _looks_like_no_hit(html, title_for_match, isbn):
            return STATUS_NO, "検索結果が0件のため、取り扱いなし（特典なし）と扱います。"
        return STATUS_UNKNOWN, "検索ヒットが見つかりませんでした。"

    if store_id == "melonbooks" or "melonbooks.co.jp" in source:
        if listing_has_products(html) or extract_product_card_texts(
            html, title_for_match, isbn, author=author
        ):
            return STATUS_NO, "検索ヒットあり。一覧では特典判定しません。"
        if search_is_no_hit(html or ""):
            return STATUS_NO, "検索結果が0件のため、取り扱いなし（特典なし）と扱います。"
        return STATUS_UNKNOWN, "検索ヒットが見つかりませんでした。"

    markup = html or ""
    if listing_has_products(markup) or extract_product_card_texts(
        markup, title_for_match, isbn, author=author
    ):
        return STATUS_NO, "検索ヒットあり。一覧では特典判定しません。"
    if _looks_like_no_hit(markup, title_for_match, isbn):
        return STATUS_NO, "検索結果が0件のため、取り扱いなし（特典なし）と扱います。"
    return STATUS_UNKNOWN, "検索ヒットが見つかりませんでした。"


def card_has_privilege(text: str) -> list[str]:
    return privilege_keywords_in(text)


def privilege_keywords_in(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in _STRONG_PRIVILEGE:
        match = pattern.search(text)
        if match:
            token = match.group(0)
            if token not in hits:
                hits.append(token)
    return hits


def _evaluate_melonbooks(
    html: str, *, title_for_match: str, isbn: str, author: str = ""
) -> tuple[str, str]:
    markup = html or ""
    if "<" not in markup:
        markup = f'<ul class="item_list"><li class="item">{markup}</li></ul>'
    if _looks_like_no_hit(markup, title_for_match, isbn):
        return STATUS_UNKNOWN, "検索ヒットが見つかりませんでした。"

    cards = extract_product_card_texts(
        markup, title_for_match, isbn, author=author, plain=True
    )
    if not cards:
        return STATUS_NO, "該当作品の商品カードが見つかりませんでした。"

    hits: list[str] = []
    for card in cards:
        if _privilege_ended(card):
            continue
        hits.extend(_melon_concrete_hits(card))
    hits = list(dict.fromkeys(hits))
    if hits:
        return STATUS_YES, "商品カードテキストで検出: " + " / ".join(hits[:4])
    return STATUS_NO, "該当商品カードに特典文言はありません。"


def _evaluate_kinokuniya(
    html: str, *, title_for_match: str, isbn: str, author: str = ""
) -> tuple[str, str]:
    markup = html or ""
    if _looks_like_no_hit(markup, title_for_match, isbn):
        return STATUS_NO, "検索結果が0件のため、取り扱いなし（特典なし）と扱います。"

    titles = _kinokuniya_product_titles(markup, title_for_match, isbn, author=author)
    if not titles:
        return STATUS_NO, "該当商品のタイトル見出しが見つかりませんでした。"

    hits: list[str] = []
    for heading in titles:
        for match in _KINO_YES.finditer(heading):
            token = match.group(0)
            if token not in hits:
                hits.append(token)
    if hits:
        return STATUS_YES, "商品タイトルで検出: " + " / ".join(hits[:4])
    return STATUS_NO, "商品タイトルに特典表記はありません。"


def _kinokuniya_product_titles(
    html: str, title: str, isbn: str, author: str = ""
) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(("header", "footer", "nav", "aside")):
        tag.decompose()
    for tag in soup.find_all(class_=_KINO_CHROME):
        tag.decompose()
    for tag in soup.find_all(id=_KINO_CHROME):
        tag.decompose()

    headings: list[str] = []
    seen: set[str] = set()
    for el in soup.select("h1, h2, h3"):
        text = el.get_text(" ", strip=True)
        if not text or text in seen:
            continue
        if titles_match(title, text, isbn, author=author):
            seen.add(text)
            headings.append(text)
    return headings


def _melon_concrete_hits(text: str) -> list[str]:
    hits: list[str] = []
    for word in _MELON_CONCRETE:
        if word in text and word not in hits:
            hits.append(word)
    return hits


def _privilege_ended(text: str) -> bool:
    return bool(_ENDED_PRIVILEGE.search(text or ""))


def _looks_like_no_hit(html: str, title: str, isbn: str) -> bool:
    text = re.sub(r"\s+", " ", html or "")
    has_marker = any(marker in text for marker in _NO_HIT_PHRASES)
    has_work = (title and title in text) or (isbn and isbn in text)
    return has_marker and not has_work


def _is_negated(text: str) -> bool:
    return any(pattern.search(text) for pattern in _NEGATIONS)
