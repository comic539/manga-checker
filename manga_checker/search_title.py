"""書店検索用に、巻数や装飾を除いた作品名を作る。"""

from __future__ import annotations

import re

from manga_checker.volume import normalize_text

_DECORATION_PATTERNS = [
    re.compile(r"@COMIC", re.IGNORECASE),
    re.compile(r"【\s*コミック\s*】"),
    re.compile(r"【\s*小説\s*】"),
    re.compile(r"【\s*新装版\s*】"),
]

_VOLUME_PATTERNS = [
    re.compile(r"第\s*\d+\s*巻"),
    re.compile(r"第\s*一\s*巻"),
    re.compile(r"全\s*\d+\s*巻"),
    re.compile(r"全\s*一\s*巻"),
    re.compile(r"(?<!\d)一\s*巻"),
    re.compile(r"volume\s*\d+", re.IGNORECASE),
    re.compile(r"vol\.?\s*\d+", re.IGNORECASE),
    re.compile(r"[\(（]\s*\d+\s*[\)）]"),
    re.compile(r"\[\s*\d+\s*\]"),
    re.compile(r"[①]"),
    re.compile(r"(?<!\d)\d+\s*巻"),
]

_WAVES = re.compile(r"[~\u301c\uff5e\u223c\u2053\u02dc]+")
# 末尾の単独巻数（『進撃の巨人 1』）。年号や『1日〜』は残す
_TRAILING_VOLUME = re.compile(r"(?<!\d)\s+\d{1,2}$")
_BRACKET_DECO = re.compile(r"[【\[].*?[】\]]")
_SUBTITLE_MARK = re.compile(r"[:：/／]")


def bare_search_title(title: str, volume: str = "") -> str:
    """『第1巻』『(1)』『@COMIC』などを除いた検索用タイトル。"""
    text = normalize_text(title)
    volume_n = normalize_text(volume)
    if volume_n and volume_n in text:
        text = text.replace(volume_n, " ")

    text = _WAVES.sub(" ", text)

    for pattern in _DECORATION_PATTERNS:
        text = pattern.sub(" ", text)
    for pattern in _VOLUME_PATTERNS:
        text = pattern.sub(" ", text)

    text = _TRAILING_VOLUME.sub("", text)
    text = re.sub(r"[\s　]+", " ", text)
    # 末尾の区切りだけ落とす。長音「ー」は作品名の一部なので残す。
    text = re.sub(r"[\s/／:：\-–—]+$", "", text)
    text = text.strip(" 　・,，.")
    return text or normalize_text(title)


def toranoana_search_word(title: str, volume: str = "") -> str:
    """とらのあな用。ISBNは使わず、サブタイトルや装飾を除いた作品名。"""
    text = normalize_text(title)
    text = _WAVES.split(text, maxsplit=1)[0]
    text = _SUBTITLE_MARK.split(text, maxsplit=1)[0]
    text = _BRACKET_DECO.sub(" ", text)
    return bare_search_title(text, volume)
