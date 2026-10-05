"""タイトル・巻次から『第1巻』相当かを判定する。"""

from __future__ import annotations

import re
import unicodedata

# 全角数字・括弧などを半角へ揃える
_VOLUME_FIELD_ONE = re.compile(r"^(第)?0*1(巻|冊)?$")
_OTHER_VOLUME_FIELD = re.compile(r"^(第)?\d+(巻|冊)?$")

# 1 / 01 / １ / ０１。11巻・10巻は前後の数字で除外する
_PADDED_ONE = r"[0０]*[1１]"
_VOLUME_ONE_PATTERN = re.compile(
    rf"(?<![0-9０-９])(?:第\s*{_PADDED_ONE}\s*巻|{_PADDED_ONE}\s*巻|"
    rf"[(（]\s*{_PADDED_ONE}\s*[)）]|"
    rf"[ \u3000]{_PADDED_ONE}(?=[ \u3000:：\(\)（）~〜-]|$))(?![0-9０-９])"
)
_VOLUME_ONE_EXTRA = [
    re.compile(r"(?<!\d)vol\.?\s*0*1(?!\d)", re.IGNORECASE),
    re.compile(r"(?<!\d)volume\s*0*1(?!\d)", re.IGNORECASE),
]

_EXCLUDE_WORDS = ("下巻", "後編", "中巻")

_VOLUME_NUMBERS = re.compile(
    r"(?:第\s*([0-9０-９]+)\s*巻|"
    r"vol\.?\s*([0-9０-９]+)|"
    r"volume\s*([0-9０-９]+)|"
    r"[(（]\s*([0-9０-９]+)\s*[)）]|"
    r"[ \u3000]([0-9０-９]+)(?=[ \u3000:：\(\)（）~〜-]|$)|"
    r"(?<![0-9０-９])([0-9０-９]+)\s*巻)",
    re.IGNORECASE,
)


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", text).strip()


def is_volume_one(title: str, volume: str = "") -> bool:
    """タイトルまたは巻次に第1巻相当の表記があるものだけを対象にする。

    単なる数字の『1』（例: 『1日10分で〜』）は巻数とは見ない。
    巻数のない単巻、短編集・上巻などは入れない。
    『下巻』『後編』や2巻以降の巻数がある作品は除外する。
    """
    volume_n = normalize_text(volume)
    combined = normalize_text(f"{title} {volume}")

    if any(word in combined for word in _EXCLUDE_WORDS):
        return False

    if volume_n:
        if _VOLUME_FIELD_ONE.fullmatch(volume_n):
            return True
        if _OTHER_VOLUME_FIELD.fullmatch(volume_n):
            return False

    numbers = _volume_numbers(title, volume)
    if any(n >= 2 for n in numbers):
        return False

    for haystack in _search_texts(title, volume):
        if _VOLUME_ONE_PATTERN.search(haystack):
            return True
        if any(pattern.search(haystack) for pattern in _VOLUME_ONE_EXTRA):
            return True

    return 1 in numbers


def _volume_numbers(title: str, volume: str) -> list[int]:
    found: list[int] = []
    for haystack in _search_texts(title, volume):
        nfkc = unicodedata.normalize("NFKC", haystack)
        for match in _VOLUME_NUMBERS.finditer(nfkc):
            raw = next((g for g in match.groups() if g), "")
            digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", raw))
            if not digits:
                continue
            value = int(digits)
            if 1 <= value <= 99:
                found.append(value)
    return found


def _search_texts(title: str, volume: str) -> list[str]:
    """スペース種別を潰す前の原文と、正規化後の両方を見る。"""
    raw_title = title or ""
    raw_volume = volume or ""
    texts = [
        raw_title,
        f"{raw_title} {raw_volume}".strip(),
        unicodedata.normalize("NFKC", raw_title),
        normalize_text(f"{raw_title} {raw_volume}"),
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique
