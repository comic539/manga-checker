"""今月のコミック書誌を取得する。

優先順位:
1. 楽天ブックス書籍検索API（発売中・予約を含む。各月は初日〜末日、ページ送りは次ページがなくなるまで）
2. 国立国会図書館サーチ OpenSearch（漫画分類 NDC 726。月初日〜末日。楽天未設定時）
3. openBD（ISBNから書誌・書影を補完）
4. 任意の CSV（手動追加）
"""

from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import requests

from manga_checker.covers import amazon_cover_url, openbd_cover_fallback
from manga_checker.dates import month_query_range, year_month_from_pubdate
from manga_checker.http import make_session
from manga_checker.models import Comic
from manga_checker.openbd import enrich_with_openbd
from manga_checker.publishers import canonical_publisher, publisher_sort_key
from manga_checker.rakuten_books import (
    fetch_rakuten_volume_ones,
    rakuten_configured,
    sales_year_month,
)
from manga_checker.retail_dates import fill_missing_pubdates
from manga_checker.volume import is_volume_one, normalize_text

NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcndl": "http://ndl.go.jp/dcndl/terms/",
    "dcterms": "http://purl.org/dc/terms/",
    "openSearch": "http://a9.com/-/spec/opensearchrss/1.0/",
}
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

NDL_OPENSEARCH = "https://ndlsearch.ndl.go.jp/api/opensearch"
ISBN_RE = re.compile(r"97[89][0-9\-]{10,}")
VOLUME_ONE_TITLE_QUERIES = ("第1巻", "(1)", "（1）", "1巻", "Vol.1")
COMIC_PUBLISHERS = (
    "講談社",
    "集英社",
    "小学館",
    "ＫＡＤＯＫＡＷＡ",
    "KADOKAWA",
    "秋田書店",
    "白泉社",
    "芳文社",
    "スクウェア・エニックス",
    "一迅社",
    "少年画報社",
    "コアミックス",
    "新潮社",
    "双葉社",
    "竹書房",
    "徳間書店",
    "幻冬舎コミックス",
    "リブレ",
    "大洋図書",
)


def month_range(year: int, month: int) -> tuple[str, str]:
    """対象月の検索範囲（初日〜末日）。YYYY-MM-DD。"""
    return month_query_range(year, month)


def fetch_month_volume_ones(
    year: int | None = None,
    month: int | None = None,
    extra_csv: Path | None = None,
    session: requests.Session | None = None,
    limit: int = 0,
) -> list[Comic]:
    today = date.today()
    year = year or today.year
    month = month or today.month
    session = session or make_session()

    comics: list[Comic] = []
    used_rakuten = False
    if rakuten_configured():
        try:
            comics.extend(
                fetch_rakuten_volume_ones(year, month, session=session)
            )
            used_rakuten = True
            print(f"楽天ブックスAPIから第1巻を {len(comics)} 件取得しました（発売中・予約を含む）。")
        except Exception as exc:
            print(f"楽天ブックスAPIを利用できません（{exc}）。NDL/openBDにフォールバックします。")
            comics = []
    else:
        print("楽天アプリIDまたはaccessKeyが未設定のため、NDL/openBDにフォールバックします。")

    if not used_rakuten:
        try:
            ndl = fetch_ndl_comics(year, month, session=session)
            print(f"NDLから漫画書誌を {len(ndl)} 件取得しました（月内全件）。")
            comics.extend(c for c in ndl if is_volume_one(c.title, c.volume))
        except Exception as exc:
            print(f"NDLの取得に失敗しました（{exc}）。")
    if extra_csv and extra_csv.exists():
        comics.extend(load_csv(extra_csv))
    comics = _dedupe(comics)
    comics = enrich_with_openbd(comics, session=session)
    comics = fill_missing_pubdates(comics, session=session)
    comics.sort(key=lambda c: publisher_sort_key(c.publisher, c.pubdate, c.display_title))
    by_pub = Counter(canonical_publisher(c.publisher) for c in comics)
    if by_pub:
        print(
            "出版社別累計: "
            + " / ".join(f"{name} {count}件" for name, count in by_pub.items())
        )
    return comics


def fetch_months_volume_ones(
    months: list[tuple[int, int]],
    extra_csv: Path | None = None,
    session: requests.Session | None = None,
) -> dict[tuple[int, int], list[Comic]]:
    """対象の複数月を、楽天なら1ヶ月ずつ完全取得する。
    各月は暦の初日〜末日を範囲とする。楽天が使えないときは NDL も同じ範囲で取得する。
    """
    if not months:
        return {}
    session = session or make_session()
    result: dict[tuple[int, int], list[Comic]] = {key: [] for key in months}
    used_rakuten = False
    if rakuten_configured():
        for year, month in months:
            try:
                got = fetch_rakuten_volume_ones(year, month, session=session)
                result[(year, month)].extend(got)
                used_rakuten = True
                print(
                    f"楽天ブックスAPIから{year}年{month}月の第1巻を "
                    f"{len(got)} 件取得しました（発売中・予約を含む）。"
                )
            except Exception as exc:
                print(
                    f"楽天ブックスAPIを利用できません（{year}年{month}月: {exc}）。"
                    "取得済みの月は残します。"
                )
        total = sum(len(comics) for comics in result.values())
        if used_rakuten:
            print(f"楽天ブックスAPIから第1巻を合計 {total} 件取得しました。")
    else:
        print("楽天アプリIDまたはaccessKeyが未設定のため、NDL/openBDにフォールバックします。")

    if used_rakuten:
        for year, month in months:
            if result[(year, month)]:
                continue
            print(f"楽天ブックス: {year}年{month}月が空のため、単月で再走査します。")
            try:
                result[(year, month)].extend(
                    fetch_rakuten_volume_ones(year, month, session=session)
                )
            except Exception as exc:
                print(f"楽天ブックス: {year}年{month}月の単月走査に失敗しました（{exc}）。")
    else:
        for year, month in months:
            try:
                ndl = fetch_ndl_comics(year, month, session=session)
            except Exception as exc:
                print(f"NDLの取得に失敗しました（{year}年{month}月: {exc}）。")
                continue
            print(f"NDLから{year}年{month}月の漫画書誌を {len(ndl)} 件取得しました。")
            result[(year, month)].extend(
                c
                for c in ndl
                if is_volume_one(c.title, c.volume) and _comic_matches_month(c, year, month)
            )

    if extra_csv and extra_csv.exists():
        month_set = set(months)
        for comic in load_csv(extra_csv):
            ym = sales_year_month(comic.pubdate)
            key = ym if ym in month_set else months[0]
            result[key].append(comic)

    all_comics: list[Comic] = []
    for key in months:
        result[key] = _dedupe(result[key])
        all_comics.extend(result[key])
    enrich_with_openbd(all_comics, session=session)
    fill_missing_pubdates(all_comics, session=session)
    result = redistribute_by_pubdate(result, months)
    for year, month in months:
        comics = _dedupe(result[(year, month)])
        result[(year, month)] = comics
        comics.sort(key=lambda c: publisher_sort_key(c.publisher, c.pubdate, c.display_title))
        by_pub = Counter(canonical_publisher(c.publisher) for c in comics)
        if by_pub:
            print(
                f"出版社別累計（{year}年{month}月）: "
                + " / ".join(f"{name} {count}件" for name, count in by_pub.items())
            )
    return result


def redistribute_by_pubdate(
    by_month: dict[tuple[int, int], list[Comic]],
    months: list[tuple[int, int]],
) -> dict[tuple[int, int], list[Comic]]:
    """発売日の年月がタブ月と一致する作品だけを、その月へ付け替える。"""
    month_set = set(months)
    moved: dict[tuple[int, int], list[Comic]] = {key: [] for key in months}
    for comics in by_month.values():
        for comic in comics:
            ym = year_month_from_pubdate(comic.pubdate)
            if ym in month_set:
                moved[ym].append(comic)
    for year, month in months:
        print(
            f"発売日フィルタ: {year}年{month}月 "
            f"{len(moved[(year, month)])} 件（タブ月と発売月が一致するもののみ）"
        )
    return moved


def write_catalog_json(path: Path, by_month: dict[tuple[int, int], list[Comic]]) -> None:
    payload = {
        f"{year:04d}-{month:02d}": [
            {
                "title": comic.display_title,
                "volume": comic.volume,
                "author": comic.author,
                "publisher": comic.publisher,
                "pubdate": comic.pubdate,
                "isbn": comic.isbn,
                "source": comic.source,
                "ndl_url": comic.ndl_url,
                "series": comic.series,
                "cover_url": comic.cover_url,
                "cover_source": comic.cover_source,
                "rakuten_item_url": comic.rakuten_item_url,
                "title_kana": comic.title_kana,
                "author_kana": comic.author_kana,
            }
            for comic in comics
        ]
        for (year, month), comics in by_month.items()
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"月別JSONを書き出しました: {path.resolve()}")


def load_catalog_json(
    path: Path,
    months: list[tuple[int, int]] | None = None,
) -> dict[tuple[int, int], list[Comic]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    month_set = set(months) if months else None
    result: dict[tuple[int, int], list[Comic]] = {}
    for key, rows in payload.items():
        year_s, month_s = key.split("-", 1)
        year, month = int(year_s), int(month_s)
        if month_set is not None and (year, month) not in month_set:
            continue
        result[(year, month)] = [
            Comic(
                title=str(row.get("title") or ""),
                volume=str(row.get("volume") or ""),
                author=str(row.get("author") or ""),
                publisher=str(row.get("publisher") or ""),
                pubdate=str(row.get("pubdate") or ""),
                isbn=str(row.get("isbn") or ""),
                source=str(row.get("source") or "json"),
                ndl_url=str(row.get("ndl_url") or ""),
                series=str(row.get("series") or ""),
                cover_url=str(row.get("cover_url") or ""),
                cover_source=str(row.get("cover_source") or ""),
                rakuten_item_url=str(row.get("rakuten_item_url") or ""),
                title_kana=str(row.get("title_kana") or ""),
                author_kana=str(row.get("author_kana") or ""),
            )
            for row in rows
            if row.get("title")
        ]
    if months:
        for key in months:
            result.setdefault(key, [])
    for comics in result.values():
        for comic in comics:
            if comic.cover_url or not comic.isbn:
                continue
            comic.cover_url = amazon_cover_url(comic.isbn) or openbd_cover_fallback(comic.isbn)
            if comic.cover_url:
                comic.cover_source = comic.cover_source or "openbd"
    return result


def _comic_matches_month(comic: Comic, year: int, month: int) -> bool:
    ym = year_month_from_pubdate(comic.pubdate)
    if ym is None:
        return True
    return ym == (year, month)


def fetch_ndl_comics(
    year: int,
    month: int,
    session: requests.Session | None = None,
    page_size: int = 200,
) -> list[Comic]:
    """その月の漫画を、APIの許す範囲で上限なく取得する。

    NDL OpenSearch は1クエリあたり500件が上限。月次がそれを超える場合は
    出版社分割と『第1巻』系タイトル検索を足して取りこぼしを減らす。
    """
    session = session or make_session()
    date_from, date_until = month_range(year, month)
    comics, total = _fetch_ndl_range(session, date_from, date_until, page_size=page_size)
    print(
        f"NDL月次クエリ（{date_from}〜{date_until}）: {len(comics)} 件取得 / 報告 {total} 件"
    )

    if total > 500 or len(comics) >= 500:
        print("500件上限のため、出版社別に追加取得します。")
        for publisher in COMIC_PUBLISHERS:
            extra, _ = _fetch_ndl_range(
                session,
                date_from,
                date_until,
                page_size=page_size,
                extra_params={"publisher": publisher},
            )
            comics.extend(extra)
            time.sleep(0.3)

    for title_q in VOLUME_ONE_TITLE_QUERIES:
        extra, _ = _fetch_ndl_range(
            session,
            date_from,
            date_until,
            page_size=page_size,
            extra_params={"title": title_q},
        )
        comics.extend(extra)
        time.sleep(0.3)

    return _dedupe(comics)


def _fetch_ndl_range(
    session: requests.Session,
    date_from: str,
    date_until: str,
    page_size: int = 200,
    hard_cap: int = 500,
    extra_params: dict[str, str] | None = None,
) -> tuple[list[Comic], int]:
    comics: list[Comic] = []
    start = 1
    total = 0
    page_size = min(page_size, 500)

    while start <= hard_cap:
        params = {
            "ndc": "726",
            "from": date_from,
            "until": date_until,
            "mediatype": "books",
            "cnt": str(min(page_size, hard_cap - start + 1)),
            "idx": str(start),
        }
        if extra_params:
            params.update(extra_params)
        url = f"{NDL_OPENSEARCH}?{urlencode(params)}"
        response = None
        for attempt in range(5):
            response = session.get(url, timeout=30)
            if response.status_code == 429:
                wait = 4 + attempt * 4
                print(f"NDL 429 Too Many Requests。{wait}秒待って再試行します（{attempt + 1}/5）")
                time.sleep(wait)
                continue
            break
        assert response is not None
        response.raise_for_status()
        root = ET.fromstring(response.content)
        total_el = root.find("channel/openSearch:totalResults", NS)
        if total_el is not None and total_el.text:
            total = int(total_el.text)

        items = root.findall("channel/item")
        if not items:
            break
        for item in items:
            comic = _parse_ndl_item(item)
            if comic:
                comics.append(comic)

        start += len(items)
        if start > total:
            break
        time.sleep(0.4)

    return comics, total


def load_csv(path: Path) -> list[Comic]:
    comics: list[Comic] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = normalize_text(row.get("title") or row.get("タイトル") or "")
            if not title:
                continue
            volume = normalize_text(row.get("volume") or row.get("巻") or "")
            if not is_volume_one(title, volume):
                continue
            comics.append(
                Comic(
                    title=title,
                    volume=volume,
                    author=normalize_text(row.get("author") or row.get("著者") or ""),
                    publisher=normalize_text(row.get("publisher") or row.get("出版社") or ""),
                    pubdate=normalize_text(row.get("pubdate") or row.get("発売日") or ""),
                    isbn=re.sub(r"[^0-9X]", "", (row.get("isbn") or row.get("ISBN") or "").upper()),
                    source="csv",
                )
            )
    return comics


def _parse_ndl_item(item: ET.Element) -> Comic | None:
    title = _text(item, "dc:title") or _text(item, "title")
    if not title:
        return None
    volume = _text(item, "dcndl:volume")
    creators = [el.text.strip() for el in item.findall("dc:creator", NS) if el.text]
    publishers = [el.text.strip() for el in item.findall("dc:publisher", NS) if el.text]
    isbn = _isbn_from_item(item)
    return Comic(
        title=normalize_text(title),
        volume=normalize_text(volume),
        author=" / ".join(creators),
        publisher=" / ".join(dict.fromkeys(publishers)),
        pubdate=normalize_text(_text(item, "dcterms:issued")),
        isbn=isbn,
        source="ndl",
        ndl_url=normalize_text(_text(item, "link")),
        series=normalize_text(_text(item, "dcndl:seriesTitle")),
    )


def _isbn_from_item(item: ET.Element) -> str:
    for el in item.findall("dc:identifier", NS):
        xsi_type = el.attrib.get(XSI_TYPE, "")
        text = (el.text or "").strip()
        if "ISBN" in xsi_type and text:
            return re.sub(r"[^0-9X]", "", text.upper())
        match = ISBN_RE.search(text)
        if match:
            return re.sub(r"[^0-9X]", "", match.group(0).upper())
    return ""


def _text(item: ET.Element, path: str) -> str:
    el = item.find(path, NS)
    return (el.text or "").strip() if el is not None else ""


def _dedupe(comics: list[Comic]) -> list[Comic]:
    seen: set[str] = set()
    unique: list[Comic] = []
    for comic in comics:
        key = comic.isbn or comic.display_title
        if key in seen:
            continue
        seen.add(key)
        unique.append(comic)
    return unique
