"""発売日の正規化と表示用フォーマット。"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone

_WEEKDAYS = "月火水木金土日"
JST = timezone(timedelta(hours=9))


def today_jst(*, now: datetime | None = None) -> date:
    """サイトの『今日』は日本時間。Actions の UTC 日付だと月初に1日遅れる。"""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(JST).date()


def prefer_pubdate(*candidates: str) -> str:
    """年月日まで分かる値を優先する。"""
    best = ""
    best_score = -1
    for raw in candidates:
        value = (raw or "").strip()
        if not value:
            continue
        score = len(_digits(value))
        if score > best_score:
            best = value
            best_score = score
    return best


def format_release_date(raw: str) -> str:
    """「2026/09/27 (日)」形式。日が無い場合は年月のみ。"""
    value = (raw or "").strip()
    if not value:
        return "日付未登録"
    parsed = parse_release_date(value)
    if parsed:
        w = _WEEKDAYS[parsed.weekday()]
        return f"{parsed:%Y/%m/%d} ({w})"
    match = re.search(r"(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?", value)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if match.group(3):
            try:
                parsed = date(year, month, int(match.group(3)))
            except ValueError:
                parsed = None
            if parsed:
                w = _WEEKDAYS[parsed.weekday()]
                return f"{parsed:%Y/%m/%d} ({w})"
        if 1 <= month <= 12:
            return f"{year:04d}/{month:02d}"
    digits = _digits(value)
    if len(digits) >= 6:
        return f"{digits[:4]}/{digits[4:6]}"
    return value


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def has_full_day(raw: str) -> bool:
    return parse_release_date(raw) is not None


def parse_release_date(raw: str) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    digits = _digits(value)
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            pass
    match = re.search(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def format_year_month(year: int, month: int) -> str:
    """タブ・説明文用の「2026年10月」形式（月はゼロ埋めしない）。"""
    return f"{year}年{month}月"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """対象月の初日と末日（暦の月。日数引き算は使わない）。"""
    if not 1 <= month <= 12:
        raise ValueError("month は 1〜12 です。")
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def month_datetime_span(year: int, month: int) -> tuple[datetime, datetime]:
    """検索範囲: 月初 00:00:00 〜 月末 23:59:59。"""
    start, end = month_bounds(year, month)
    return datetime.combine(start, time.min), datetime.combine(end, time(23, 59, 59))


def month_query_range(year: int, month: int) -> tuple[str, str]:
    """API の from/until 用（YYYY-MM-DD）。その月の初日〜末日。"""
    start, end = month_bounds(year, month)
    return start.isoformat(), end.isoformat()


def year_month_from_pubdate(raw: str) -> tuple[int, int] | None:
    """発売日から (年, 月) を取る。日が無くても年月が分かれば返す。"""
    parsed = parse_release_date(raw)
    if parsed:
        return parsed.year, parsed.month
    value = (raw or "").strip()
    match = re.search(r"(\d{4})\D+(\d{1,2})", value)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return year, month
    digits = _digits(value)
    if len(digits) >= 6:
        year, month = int(digits[:4]), int(digits[4:6])
        if 1 <= month <= 12:
            return year, month
    return None


def is_unreleased(pubdate: str, today: date | None = None) -> bool:
    """発売日が今日以降（または年月だけ分かって当月以降）なら未発売。"""
    today = today or today_jst()
    parsed = parse_release_date(pubdate)
    if parsed:
        return parsed > today
    ym = year_month_from_pubdate(pubdate)
    if ym is None:
        return True
    return date(ym[0], ym[1], 1) > date(today.year, today.month, 1)


def date_in_month(raw: str, year: int, month: int) -> bool | None:
    """年月日まで分かる値はその月の初日〜末日に入るか。判定不能なら None。"""
    parsed = parse_release_date(raw)
    if parsed is None:
        return None
    start, end = month_bounds(year, month)
    return start <= parsed <= end


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """年月に delta ヶ月を加算する（負数可、年またぎ可）。"""
    if not 1 <= month <= 12:
        raise ValueError("month は 1〜12 です。")
    index = year * 12 + (month - 1) + delta
    y, m0 = divmod(index, 12)
    return y, m0 + 1


def iter_months(year: int, month: int, count: int = 4) -> list[tuple[int, int]]:
    """year/month から連続する count ヶ月（年またぎ可）。"""
    if count < 1:
        raise ValueError("count は 1 以上にしてください。")
    if not 1 <= month <= 12:
        raise ValueError("month は 1〜12 です。")
    return [add_months(year, month, i) for i in range(count)]


def iter_month_offsets(
    year: int | None = None,
    month: int | None = None,
    *,
    before: int = 3,
    after: int = 3,
    today: date | None = None,
) -> list[tuple[int, int]]:
    """基準月の before ヶ月前から after ヶ月後まで（既定は -3〜+3 の7ヶ月）。"""
    if before < 0 or after < 0:
        raise ValueError("before / after は 0 以上にしてください。")
    today = today or today_jst()
    y = today.year if year is None else year
    m = today.month if month is None else month
    if not 1 <= m <= 12:
        raise ValueError("month は 1〜12 です。")
    return [add_months(y, m, offset) for offset in range(-before, after + 1)]


def privilege_months(today: date | None = None) -> list[tuple[int, int]]:
    """特典一覧の走査窓: 前月・当月・翌月・翌々月。"""
    return iter_month_offsets(before=1, after=2, today=today)


def comiczin_months(
    catalog_months: list[tuple[int, int]] | None = None,
    today: date | None = None,
) -> list[tuple[int, int]]:
    """COMIC ZIN 入荷日検索: 掲載済みの過去月＋当月＋翌月まで。"""
    current = today or today_jst()
    limit = add_months(current.year, current.month, 1)
    source = catalog_months or privilege_months(today=current)
    return [ym for ym in source if ym <= limit]


def iter_month_days(months: list[tuple[int, int]]) -> list[date]:
    days: list[date] = []
    for year, month in months:
        start, end = month_bounds(year, month)
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
    return days
