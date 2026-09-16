"""ISBN から書影URLを組み立てる。"""

from __future__ import annotations


def amazon_cover_url(isbn: str) -> str:
    """書影は楽天ブックスAPIのみ。Amazon URL は生成しない。"""
    return ""


def openbd_cover_fallback(isbn: str) -> str:
    """書影は楽天ブックスAPIのみ。openBD URL は生成しない。"""
    return ""


def isbn13_to_isbn10(isbn13: str) -> str:
    core = isbn13[3:12]
    if len(core) != 9 or not core.isdigit():
        return ""
    total = sum(int(ch) * (10 - i) for i, ch in enumerate(core))
    remainder = total % 11
    check = 11 - remainder
    if check == 10:
        check_ch = "X"
    elif check == 11:
        check_ch = "0"
    else:
        check_ch = str(check)
    return core + check_ch
