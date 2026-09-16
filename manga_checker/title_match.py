"""作品名の照合。短いタイトルの誤ヒットを避ける。"""

from __future__ import annotations

import re
import unicodedata

from manga_checker.search_title import bare_search_title
from manga_checker.volume import normalize_text

_AUTHOR_SPLIT = re.compile(r"[,、/／・\s]+")
_AFTER_OK = set(" 　0123456789第巻()（）[]【】「」『』~～〜・:：/／-|!！?？☆★'のと")
# 文中照合の直前。『の』は『裏切り者のラブソング』誤ヒットを避けるため入れない
_BEFORE_OK = set(" 　0123456789第巻()（）[]【】「」『』~～〜・:：/／-|!！?？☆★'")


def titles_match(
    work_title: str,
    haystack: str,
    isbn: str = "",
    author: str = "",
) -> bool:
    hay = normalize_text(haystack)
    digits = "".join(ch for ch in isbn if ch.isdigit())
    if len(digits) >= 10 and digits in hay.replace("-", ""):
        return True
    bare = bare_search_title(work_title)
    if len(bare) < 2:
        return False
    hay_bare = bare_search_title(haystack)
    candidates = (
        hay_bare,
        hay,
        hay.lstrip("「」『』【】\"'・ "),
        hay_bare.lstrip("「」『』【】\"'・ "),
    )
    if any(_exact_or_prefix(bare, cand) for cand in candidates):
        return True
    if any(_contained_title(bare, cand) for cand in candidates):
        return True
    if author and _author_in(hay, author) and bare in hay:
        return True
    return False


def _exact_or_prefix(bare: str, hay: str) -> bool:
    if hay == bare:
        return True
    if hay.startswith(bare) and _prefix_boundary(hay, len(bare)):
        return True
    return False


def _contained_title(bare: str, hay: str) -> bool:
    if len(bare) < 3:
        return False
    start = 0
    while True:
        idx = hay.find(bare, start)
        if idx < 0:
            return False
        before_ok = idx == 0 or hay[idx - 1] in _BEFORE_OK
        after_ok = _prefix_boundary(hay, idx + len(bare))
        if before_ok and after_ok:
            return True
        start = idx + 1


def _prefix_boundary(hay: str, end: int) -> bool:
    if end >= len(hay):
        return True
    nxt = hay[end]
    return nxt in _AFTER_OK or not _is_name_char(nxt)


def _is_name_char(ch: str) -> bool:
    if not ch:
        return False
    cat = unicodedata.category(ch)
    return cat.startswith("L") or cat.startswith("M")


def _author_in(hay: str, author: str) -> bool:
    for token in _author_tokens(author):
        if token in hay:
            return True
    return False


def _author_tokens(author: str) -> list[str]:
    tokens: list[str] = []
    for part in _AUTHOR_SPLIT.split(normalize_text(author or "")):
        part = part.strip()
        if len(part) >= 2 and part not in {"著", "作画", "原作", "漫画", "作"}:
            tokens.append(part)
    return tokens


def listing_matches_work(
    work_title: str,
    haystack: str,
    isbn: str = "",
    author: str = "",
) -> bool:
    """商品カード／リンク文言が探している作品か。短い部分一致の誤爆はしない。"""
    if not titles_match(work_title, haystack, isbn, author=author):
        return False
    digits = "".join(ch for ch in isbn if ch.isdigit())
    hay = normalize_text(haystack)
    if len(digits) >= 10 and digits in hay.replace("-", ""):
        return True
    bare = bare_search_title(work_title)
    return len(bare) < 2 or bare in hay
