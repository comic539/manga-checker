"""CSV とカード型HTML（発売日カレンダー）を出力する。"""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from pathlib import Path

from manga_checker.dates import format_release_date, format_year_month, year_month_from_pubdate
from manga_checker.links import amazon_url, mercari_url, rakuten_url
from manga_checker.models import Comic, ComicReport, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES
from manga_checker.publishers import (
    PUBLISHER_ORDER,
    OTHER_PUBLISHER_LABEL,
    publisher_group_label,
    publisher_sort_key,
)
from manga_checker.readings import search_index_text
from manga_checker.stores import STORES

SITE_TITLE = "新刊コミック第１巻　書店特典チェック"
ASSET_VER = "mercari4"

_STATUS_CLASS = {
    STATUS_YES: "yes",
    STATUS_NO: "no",
    STATUS_UNKNOWN: "todo",
}
_INDEX_TAB_CLASS = {
    "animate": "index-tab-animate",
    "melonbooks": "index-tab-melon",
    "gamers": "index-tab-gamers",
    "kinokuniya": "index-tab-kinokuniya",
    "kikuya": "index-tab-kikuya",
    "kumazawa": "index-tab-kumazawa",
}


def write_csv(reports: list[ComicReport], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = _sorted_reports(reports)
    fieldnames = [
        "タイトル",
        "検索タイトル",
        "巻",
        "著者",
        "出版社",
        "発売日",
        "対象月",
        "ISBN",
        "書影URL",
        "Amazon",
        "楽天ブックス",
        "出典",
    ]
    for store in STORES:
        fieldnames.append(f"{store.name}_特典")
        fieldnames.append(f"{store.name}_検索URL")

    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for report in reports:
            row = {
                "タイトル": report.comic.display_title,
                "検索タイトル": report.comic.search_query,
                "巻": report.comic.volume,
                "著者": report.comic.author,
                "出版社": report.comic.publisher,
                "発売日": report.comic.pubdate,
                "対象月": (
                    f"{report.period_year:04d}-{report.period_month:02d}"
                    if report.period_year and report.period_month
                    else ""
                ),
                "ISBN": report.comic.isbn,
                "書影URL": report.comic.cover_url,
                "Amazon": amazon_url(report.comic.isbn, report.comic.search_query),
                "楽天ブックス": rakuten_url(report.comic.isbn, report.comic.search_query),
                "出典": report.comic.source,
            }
            for check in report.checks:
                row[f"{check.store_name}_特典"] = check.status
                row[f"{check.store_name}_検索URL"] = check.url
            writer.writerow(row)


def write_html(
    reports: list[ComicReport],
    path: Path,
    heading: str,
    *,
    month_panels: list[tuple[int, int, list[ComicReport]]] | None = None,
    active_period: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not month_panels:
        month_panels = [(0, 0, reports)]
    tabs: list[str] = []
    panels: list[str] = []
    card_id = 0
    named_indexes = [
        index
        for index, (year, month, _) in enumerate(month_panels)
        if year and month
    ]
    active_index = 0
    if active_period and named_indexes:
        for index, (year, month, _) in enumerate(month_panels):
            if (year, month) == active_period:
                active_index = index
                break
        else:
            active_index = named_indexes[0]
    active_counts: Counter = Counter()
    active_total = 0
    all_reports: list[ComicReport] = []
    for index, (year, month, items) in enumerate(month_panels):
        month_items = _reports_matching_month(items, year, month)
        all_reports.extend(month_items)
        counts = Counter(check.status for report in month_items for check in report.checks)
        if index == active_index:
            active_counts = counts
            active_total = len(month_items)
        month_id = f"{year:04d}-{month:02d}" if year and month else f"panel-{index}"
        if year and month:
            label = format_year_month(year, month)
        else:
            label = "一覧"
        grouped = _group_by_publisher(month_items)
        sections: list[str] = []
        for pub_label, pub_items in grouped:
            cards = []
            for report in pub_items:
                cards.append(_card_html(report, card_id))
                card_id += 1
            sections.append(
                f'<section class="day-block" data-publisher="{html.escape(pub_label, quote=True)}">'
                f'<h2 class="day-label">{html.escape(pub_label)}'
                f'<span class="count">{len(pub_items)}作品</span></h2>'
                f'<div class="card-grid">{"".join(cards)}</div>'
                "</section>"
            )
        inner = "\n".join(sections) or '<p class="empty">該当する第1巻はありませんでした。</p>'
        is_active = index == active_index
        active = " is-active" if is_active else ""
        hidden = "" if is_active else " hidden"
        selected = "true" if is_active else "false"
        panels.append(
            f'<div class="month-panel{active}" id="month-{html.escape(month_id, quote=True)}" '
            f'data-month="{html.escape(month_id, quote=True)}" data-total="{len(month_items)}" '
            f'data-yes="{counts.get(STATUS_YES, 0)}" data-no="{counts.get(STATUS_NO, 0)}" '
            f'data-todo="{counts.get(STATUS_UNKNOWN, 0)}" role="tabpanel"{hidden}>'
            f"{inner}"
            "</div>"
        )
        tabs.append(
            f'<button type="button" class="month-tab{active}" role="tab" '
            f'data-month="{html.escape(month_id, quote=True)}" '
            f'aria-selected="{selected}" aria-controls="month-{html.escape(month_id, quote=True)}">'
            f"{html.escape(label)}</button>"
        )
    tabs_html = (
        f'<nav class="month-tabs" role="tablist" aria-label="発売月">{"".join(tabs)}</nav>'
        if tabs
        else ""
    )
    body = "\n".join(panels)
    index_links = "".join(
        f"<a class='index-tab {_INDEX_TAB_CLASS.get(store.store_id, '')}' "
        f"data-store='{html.escape(store.store_id)}' "
        f"href='{html.escape(store.privilege_index_url)}' target='_blank' "
        f"rel='noopener noreferrer'>{html.escape(store.name)}</a>"
        for store in STORES
        if store.privilege_index_url
    )
    summary = (
        "新タイトルの【第1巻】の発売日のみにスポットを当て、"
        "各書店の限定特典情報をまとめたチェッカーサイトです。"
        "各月は出版社優先順 → 発売日順です。"
    )
    disclaimer = (
        "各書店の表記ゆれや仕様変更により、自動検知に不安定な部分"
        "（特典があるのに『未確認』となる等）が生じる場合がございます。"
        "ご不便をおかけしますが、特典の有無や配布状況の最終確認は"
        "各書店の公式商品ページにてご確認ください。"
    )
    path.write_text(
        _html_document(
            heading,
            body,
            index_links,
            active_total,
            active_counts,
            rakuten_credit=_uses_rakuten(all_reports),
            tabs_html=tabs_html,
            summary=summary,
            disclaimer=disclaimer,
        ),
        encoding="utf-8",
    )


def _sorted_reports(reports: list[ComicReport]) -> list[ComicReport]:
    return sorted(
        reports,
        key=lambda r: publisher_sort_key(
            r.comic.publisher, r.comic.pubdate, r.comic.display_title
        ),
    )


def _reports_matching_month(
    reports: list[ComicReport], year: int, month: int
) -> list[ComicReport]:
    if not year or not month:
        return reports
    matched: list[ComicReport] = []
    for report in reports:
        ym = year_month_from_pubdate(report.comic.pubdate)
        if ym == (year, month):
            matched.append(report)
    return matched


def _group_by_publisher(reports: list[ComicReport]) -> list[tuple[str, list[ComicReport]]]:
    buckets: dict[str, list[ComicReport]] = defaultdict(list)
    for report in reports:
        buckets[publisher_group_label(report.comic.publisher)].append(report)

    def sort_items(items: list[ComicReport]) -> list[ComicReport]:
        return sorted(
            items,
            key=lambda r: publisher_sort_key(
                r.comic.publisher, r.comic.pubdate, r.comic.display_title
            ),
        )

    ordered: list[tuple[str, list[ComicReport]]] = []
    for name in PUBLISHER_ORDER:
        if name in buckets:
            ordered.append((name, sort_items(buckets[name])))
    if OTHER_PUBLISHER_LABEL in buckets:
        ordered.append((OTHER_PUBLISHER_LABEL, sort_items(buckets[OTHER_PUBLISHER_LABEL])))
    return ordered


def _card_html(report: ComicReport, card_id: int = 0) -> str:
    comic = report.comic
    badges = "".join(_badge_html(check) for check in report.checks)
    cover = _cover_html(comic)
    author = html.escape(comic.author or "著者未登録")
    publisher = html.escape(comic.publisher or "出版社未登録")
    isbn = html.escape(comic.isbn) if comic.isbn else ""
    amazon = amazon_url(comic.isbn, comic.search_query)
    rakuten = rakuten_url(comic.isbn, comic.search_query)
    mercari = mercari_url(comic.search_query)
    release = html.escape(format_release_date(comic.pubdate))
    release_ym = year_month_from_pubdate(comic.pubdate)
    release_month_attr = (
        f"{release_ym[0]:04d}-{release_ym[1]:02d}" if release_ym else ""
    )
    credit = _credit_html(comic)
    ext = (
        '<div class="ext-links">'
        f'<a class="ext amazon" href="{html.escape(amazon)}" target="_blank" '
        'rel="noopener noreferrer"><span class="mark" aria-hidden="true">a</span>Amazon</a>'
        '<div class="ext-stack">'
        f'<a class="ext rakuten" href="{html.escape(rakuten)}" target="_blank" '
        'rel="noopener noreferrer"><span class="mark" aria-hidden="true">R</span>楽天ブックス</a>'
        f'<a class="ext mercari" href="{html.escape(mercari)}" target="_blank" '
        'rel="noopener noreferrer"><span class="mark" aria-hidden="true">m</span>mercari</a>'
        "</div>"
        "</div>"
    )
    search_blob = html.escape(
        search_index_text(
            comic.display_title,
            comic.author,
            comic.publisher,
            comic.title_kana,
            comic.author_kana,
        ),
        quote=True,
    )
    cover_attr = html.escape(_rakuten_cover_url(comic), quote=True)
    return (
        f'<article class="card" id="comic-card-{card_id}" data-card-id="{card_id}" '
        f'data-search="{search_blob}" '
        f'data-cover="{cover_attr}" '
        f'data-title="{html.escape(comic.display_title, quote=True)}" '
        f'data-publisher="{html.escape(comic.publisher or "出版社未登録", quote=True)}" '
        f'data-date="{release}" data-release-month="{release_month_attr}">'
        '<div class="cover-col">'
        f"{cover}"
        f"{credit}"
        "</div>"
        '<div class="card-body">'
        f'<p class="date-chip">{release}</p>'
        '<div class="title-row">'
        f"<h3>{html.escape(comic.display_title)}</h3>"
        f'<button type="button" class="copy-title" data-title="{html.escape(comic.display_title, quote=True)}">📋 コピー</button>'
        "</div>"
        f"{ext}"
        f'<p class="meta">{author}</p>'
        f'<p class="meta">{publisher}</p>'
        f'<p class="isbn">{isbn}</p>'
        f'<div class="badges">{badges}</div>'
        "</div></article>"
    )


def _uses_rakuten(reports: list[ComicReport]) -> bool:
    return any(
        report.comic.cover_source == "rakuten"
        or "rakuten" in (report.comic.source or "")
        or "rakuten" in (report.comic.cover_url or "")
        for report in reports
    )


def _credit_html(comic: Comic) -> str:
    if not _rakuten_cover_url(comic):
        return ""
    return (
        '<p class="credit">出典: 楽天ブックス</p>'
        '<p class="credit">Supported by Rakuten Developers</p>'
    )


def _rakuten_cover_url(comic: Comic) -> str:
    from manga_checker.rakuten_books import is_placeholder_cover

    url = comic.cover_url or ""
    if is_placeholder_cover(url):
        return ""
    if comic.cover_source == "rakuten" or "rakuten" in url:
        return url
    return ""


def _cover_html(comic: Comic) -> str:
    placeholder = '<div class="cover ph" aria-hidden="true"><span>書影なし</span></div>'
    src_url = _rakuten_cover_url(comic)
    if not src_url:
        return placeholder
    src = html.escape(src_url, quote=True)
    alt = html.escape(comic.display_title)
    return (
        '<div class="cover">'
        f'<img src="{src}" alt="{alt}" loading="lazy" referrerpolicy="no-referrer" '
        "onerror=\"const p=this.parentElement; p.classList.add('ph'); p.innerHTML='<span>書影なし</span>';\">"
        "</div>"
    )


def _badge_html(check: StoreCheck) -> str:
    css = _STATUS_CLASS.get(check.status, "todo")
    title = html.escape(check.detail)
    return (
        f'<a class="badge {css}" href="{html.escape(check.url)}" '
        f'target="_blank" rel="noopener noreferrer" title="{title}">'
        f"<span class='store'>{html.escape(check.store_name)}</span>"
        f"<span class='status'>{html.escape(check.status)}</span>"
        "</a>"
    )


def _html_document(
    heading: str,
    body: str,
    index_links: str,
    total: int,
    counts: Counter,
    rakuten_credit: bool = False,
    tabs_html: str = "",
    summary: str = "",
    disclaimer: str = "",
) -> str:
    page_size = 50
    if total <= 0:
        initial_hit = "0件中 0件表示"
    elif total <= page_size:
        initial_hit = f"{total}件中 {total}件表示"
    else:
        initial_hit = f"{total}件中 1〜{page_size}件表示"
    if not summary:
        summary = (
            "新タイトルの【第1巻】の発売日のみにスポットを当て、"
            "各書店の限定特典情報をまとめたチェッカーサイトです。"
            "各月は出版社優先順 → 発売日順です。"
        )
    if not disclaimer:
        disclaimer = (
            "各書店の表記ゆれや仕様変更により、自動検知に不安定な部分"
            "（特典があるのに『未確認』となる等）が生じる場合がございます。"
            "ご不便をおかけしますが、特典の有無や配布状況の最終確認は"
            "各書店の公式商品ページにてご確認ください。"
        )
    return f"""<!DOCTYPE html>
<html lang="ja" data-build="{ASSET_VER}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta http-equiv="Cache-Control" content="no-store">
  <title>{html.escape(heading)}</title>
  <link rel="icon" type="image/png" href="icon-3.png?v={ASSET_VER}">
  <link rel="shortcut icon" href="favicon.ico?v={ASSET_VER}">
  <style>
    :root {{
      --bg: #efe7dc;
      --paper: #fffaf3;
      --ink: #2a211c;
      --muted: #7a6f66;
      --accent: #c45c26;
      --yes: #1f7a3a;
      --yes-bg: #e5f6ea;
      --no: #5c5854;
      --no-bg: #eeeae4;
      --todo: #8a6400;
      --todo-bg: #fff3cc;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      width: 100%;
      max-width: 100%;
      overflow-x: hidden;
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Hiragino Sans", "Yu Gothic", Meiryo, sans-serif;
      background:
        radial-gradient(circle at top left, #f7efe3, transparent 28%),
        var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 32px 24px 12px;
      width: 100%;
      max-width: 1360px;
      margin: 0 auto;
      overflow-x: hidden;
      box-sizing: border-box;
      position: relative;
      z-index: 5;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 1.6rem;
      letter-spacing: 0.04em;
    }}
    .kicker {{
      color: var(--accent);
      font-weight: 700;
      font-size: 0.8rem;
      letter-spacing: 0.18em;
      margin: 0 0 6px;
    }}
    .summary, .legend, .indexes, .search-hit {{
      color: var(--muted);
      font-size: 0.9rem;
      margin: 6px 0;
    }}
    .disclaimer {{
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
      max-width: 46rem;
      margin: 8px 0 10px;
    }}
    .month-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0 4px;
    }}
    .month-tab {{
      min-width: 7.5em;
      padding: 8px 12px;
      border: 0;
      border-radius: 999px;
      background: #fffaf3;
      color: var(--ink);
      font: inherit;
      font-size: 0.84rem;
      font-weight: 800;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      cursor: pointer;
      white-space: nowrap;
    }}
    .month-tab:hover {{
      background: #f3e6d6;
    }}
    .month-tab.is-active {{
      background: var(--accent);
      color: #fff;
    }}
    .index-tabs {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin: 12px 0 4px;
    }}
    .index-label {{
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 700;
      margin-right: 4px;
    }}
    .index-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 6.5em;
      padding: 8px 14px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 800;
      text-decoration: none;
      box-shadow: 0 1px 3px rgba(0,0,0,0.12);
      white-space: nowrap;
      transition: transform 0.15s ease, filter 0.15s ease, box-shadow 0.15s ease;
    }}
    .index-tab:hover {{
      transform: translateY(-2px);
      filter: brightness(1.06);
      box-shadow: 0 4px 10px rgba(0,0,0,0.16);
    }}
    .index-tab-animate {{
      background: #f5d000;
      color: #0b3cc8;
    }}
    .index-tab-melon {{
      background: #8bc34a;
      color: #143308;
    }}
    .index-tab-gamers {{
      background: #ff8a1a;
      color: #3d1a00;
    }}
    /* 紀伊國屋書店: 藍色・白文字 */
    .index-tab-kinokuniya,
    .index-tab[data-store="kinokuniya"] {{
      background: #123a6e;
      color: #fff;
    }}
    /* 喜久屋書店: 薄い紫 */
    .index-tab-kikuya,
    .index-tab[data-store="kikuya"] {{
      background: #e4c7f5;
      color: #3a1a55;
    }}
    .index-tab-kumazawa {{
      background: #cbb089;
      color: #3d2c16;
    }}
    .month-panel[hidden] {{
      display: none !important;
    }}
    .search-bar {{
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 10px 16px;
      margin: 14px 0 8px;
    }}
    .search-cluster {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      flex: 1 1 320px;
      max-width: 560px;
    }}
    .search-wrap {{
      position: relative;
      flex: 1 1 auto;
      min-width: 0;
    }}
    .search-wrap input {{
      width: 100%;
      padding: 10px 36px 10px 12px;
      border: 1px solid #e2d5c4;
      border-radius: 10px;
      background: #fffaf3;
      color: var(--ink);
      font-size: 0.95rem;
      font-family: inherit;
    }}
    .search-wrap input:focus {{
      outline: 2px solid #e8b48a;
      outline-offset: 1px;
    }}
    .search-clear {{
      position: absolute;
      right: 6px;
      top: 10px;
      width: 28px;
      height: 28px;
      border: 0;
      border-radius: 50%;
      background: #efe7dc;
      color: var(--muted);
      font-size: 1.05rem;
      line-height: 1;
      cursor: pointer;
    }}
    .search-clear:hover {{
      background: #f3e6d6;
      color: var(--ink);
    }}
    .search-go {{
      flex: 0 0 auto;
      width: 44px;
      height: 44px;
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: #fff;
      font-size: 1.15rem;
      cursor: pointer;
      box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }}
    .search-go:hover {{
      filter: brightness(1.05);
    }}
    .search-suggest {{
      position: absolute;
      left: 0;
      right: 0;
      top: calc(100% + 4px);
      margin: 0;
      padding: 6px 0;
      list-style: none;
      background: #fffaf3;
      border: 1px solid #e2d5c4;
      border-radius: 12px;
      box-shadow: 0 12px 28px rgba(80, 50, 20, 0.16);
      z-index: 20;
      max-height: 420px;
      overflow: auto;
    }}
    .search-suggest[hidden] {{
      display: none !important;
    }}
    .suggest-item {{
      display: grid;
      grid-template-columns: 40px 1fr;
      gap: 10px;
      width: 100%;
      padding: 8px 12px;
      border: 0;
      background: transparent;
      text-align: left;
      cursor: pointer;
      color: inherit;
      font-family: inherit;
    }}
    .suggest-item:hover,
    .suggest-item.active {{
      background: #f3e6d6;
    }}
    .suggest-thumb {{
      width: 40px;
      height: 56px;
      border-radius: 4px;
      object-fit: cover;
      background: #d9cfc3;
    }}
    .suggest-thumb.ph {{
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.55rem;
      color: #8a7f75;
    }}
    .suggest-title {{
      font-size: 0.86rem;
      font-weight: 700;
      line-height: 1.3;
    }}
    .suggest-meta {{
      margin-top: 2px;
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .search-hit {{
      font-weight: 700;
      margin: 8px 0 0;
    }}
    .card.focus-flash {{
      outline: 3px solid var(--accent);
      box-shadow: 0 0 0 6px rgba(196, 92, 38, 0.28);
      animation: cardGlow 2.8s ease;
    }}
    @keyframes cardGlow {{
      0% {{ box-shadow: 0 0 0 8px rgba(196, 92, 38, 0.45); }}
      100% {{ box-shadow: 0 8px 24px rgba(80, 50, 20, 0.08); }}
    }}
    .legend b.yes {{ color: var(--yes); }}
    .legend b.no {{ color: var(--no); }}
    .legend b.todo {{ color: var(--todo); }}
    main {{
      width: 100%;
      max-width: 1360px;
      margin: 0 auto 48px;
      padding: 0 16px;
      overflow-x: hidden;
      box-sizing: border-box;
    }}
    .day-block {{ margin-top: 28px; }}
    .day-label {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin: 0 0 14px;
      padding-bottom: 8px;
      border-bottom: 2px solid #e2d5c4;
      font-size: 1.15rem;
    }}
    .day-label .count {{
      color: var(--muted);
      font-size: 0.8rem;
      font-weight: 600;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(440px, 1fr));
      gap: 14px;
    }}
    .card {{
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 12px;
      min-width: 340px;
      background: var(--paper);
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 8px 24px rgba(80, 50, 20, 0.08);
    }}
    .cover-col {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }}
    .cover {{
      width: 110px;
      height: 156px;
      border-radius: 8px;
      overflow: hidden;
      background: #d9cfc3;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .cover img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .cover.ph {{
      color: #8a7f75;
      font-size: 0.75rem;
      text-align: center;
      padding: 8px;
    }}
    .card-body h3 {{
      margin: 0;
      font-size: 1rem;
      line-height: 1.35;
    }}
    .title-row {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin: 0 0 6px;
    }}
    .copy-title {{
      flex: 0 0 auto;
      margin-top: 2px;
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 0.68rem;
      font-weight: 700;
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 6px;
      white-space: nowrap;
      line-height: 1.3;
    }}
    .copy-title:hover {{
      background: #f3e6d6;
      color: var(--ink);
    }}
    .copy-title.done {{
      color: var(--yes);
    }}
    .date-chip {{
      display: inline-block;
      margin: 0 0 6px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #f3e6d6;
      color: var(--accent);
      font-size: 0.72rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    .credit {{
      margin: 0;
      font-size: 0.58rem;
      line-height: 1.35;
      color: #9a9088;
    }}
    footer.api-credit {{
      max-width: 1360px;
      margin: 0 auto 8px;
      padding: 0 16px 8px;
      color: #9a9088;
      font-size: 0.72rem;
    }}
    footer.affiliate-note {{
      max-width: 1360px;
      margin: 0 auto 48px;
      padding: 4px 16px 28px;
      color: #b5aea6;
      font-size: 0.68rem;
      line-height: 1.5;
      text-align: center;
    }}
    .meta, .isbn {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.4;
    }}
    .ext-links {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin: 0 0 8px;
      align-items: start;
    }}
    .ext-stack {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 0;
    }}
    .ext-stack .ext {{
      width: 100%;
      box-sizing: border-box;
    }}
    .ext {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 6px 8px;
      border-radius: 8px;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.01em;
      text-decoration: none;
      white-space: nowrap;
      overflow: hidden;
      line-height: 1;
      box-shadow: 0 1px 2px rgba(0,0,0,0.12);
    }}
    .ext .mark {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.15em;
      height: 1.15em;
      border-radius: 50%;
      font-size: 0.68rem;
      font-weight: 900;
      flex: 0 0 auto;
    }}
    .ext.amazon {{
      background: #232f3e;
      color: #ff9900;
    }}
    .ext.amazon .mark {{
      background: #ff9900;
      color: #232f3e;
    }}
    .ext.rakuten {{
      background: #bf0000;
      color: #fff;
    }}
    .ext.rakuten .mark {{
      background: #fff;
      color: #bf0000;
      border-radius: 3px;
    }}
    .ext.mercari {{
      background: #4ba7ee;
      color: #ffffff;
      font-weight: 800;
      justify-content: center;
      align-items: center;
      border-radius: 10px;
      letter-spacing: 0.02em;
    }}
    .ext.mercari .mark {{
      background: #ff0211;
      color: #ffffff;
      border-radius: 4px;
      font-family: "Nunito", "Varela Round", "Segoe UI", "Trebuchet MS", sans-serif;
      font-weight: 800;
    }}
    .badges {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 6px;
      margin-top: 10px;
    }}
    .badge {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-width: 0;
      padding: 7px 4px;
      border-radius: 8px;
      text-decoration: none;
      text-align: center;
      box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    }}
    .badge .store {{
      font-size: 0.66rem;
      font-weight: 800;
      line-height: 1.25;
      white-space: normal;
      overflow: visible;
      text-overflow: unset;
      word-break: keep-all;
    }}
    .badge .status {{
      font-size: 0.7rem;
      font-weight: 800;
      white-space: nowrap;
      margin-top: 2px;
    }}
    .badge.yes {{
      background: #16a34a;
      color: #fff;
    }}
    .badge.yes .store,
    .badge.yes .status {{ color: #fff; }}
    .badge.no {{
      background: #eceae6;
      color: #3f3c39;
    }}
    .badge.no .store,
    .badge.no .status {{ color: #4b5563; }}
    .badge.todo {{
      background: #fff3cc;
      color: #8a6400;
    }}
    .badge.todo .store,
    .badge.todo .status {{ color: #8a6400; }}
    .empty {{ color: var(--muted); padding: 24px; }}
    .ad-container {{
      margin: 20px auto;
      text-align: center;
      max-width: 1360px;
      width: 100%;
      padding: 0 16px;
      overflow: hidden;
    }}
    .ad-pr {{
      margin: 0 0 6px;
      color: #9a9088;
      font-size: 0.65rem;
      letter-spacing: 0.16em;
      font-weight: 700;
    }}
    .ad-slot {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      max-width: 728px;
      min-height: 90px;
      margin: 0 auto;
      background: #e8e2d8;
      color: #9a9088;
      font-size: 0.75rem;
      letter-spacing: 0.14em;
      border: 1px dashed #cfc4b6;
      overflow: hidden;
    }}
    .ad-container img,
    .ad-container iframe,
    .ad-container ins {{
      max-width: 100%;
      height: auto;
    }}
    .ad-footer {{
      margin-bottom: 8px;
    }}
    .pager {{
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px auto 24px;
      padding: 4px 16px 8px;
    }}
    .pager-top {{
      margin: 8px auto 16px;
      padding-bottom: 4px;
    }}
    .pager-bottom {{
      margin-bottom: 40px;
      padding-bottom: 24px;
    }}
    .pager-pages {{
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .pager-btn {{
      min-width: 40px;
      height: 40px;
      padding: 0 12px;
      border: 0;
      border-radius: 999px;
      background: #fffaf3;
      color: var(--ink);
      font: inherit;
      font-size: 0.88rem;
      font-weight: 700;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      cursor: pointer;
    }}
    .pager-btn:hover:not(:disabled) {{
      background: #f3e6d6;
    }}
    .pager-btn.is-current {{
      background: var(--accent);
      color: #fff;
    }}
    .pager-btn:disabled {{
      opacity: 0.4;
      cursor: default;
    }}
    .back-to-top {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 1000;
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      min-width: 88px;
      height: auto;
      padding: 8px 14px;
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      line-height: 1.15;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(196, 92, 38, 0.35);
      opacity: 0;
      pointer-events: none;
      transform: translateY(8px);
      transition: opacity 0.25s ease, transform 0.25s ease, box-shadow 0.2s ease;
    }}
    .back-to-top-icon {{
      font-size: 13px;
      line-height: 1;
    }}
    .back-to-top-label {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }}
    .back-to-top.is-visible {{
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
    }}
    .back-to-top:hover {{
      transform: translateY(-4px);
      box-shadow: 0 8px 16px rgba(196, 92, 38, 0.4);
    }}
    .card[hidden],
    .day-block[hidden],
    .month-panel[hidden],
    #search-empty[hidden],
    .search-suggest[hidden],
    .pager[hidden] {{
      display: none !important;
    }}
    @media (max-width: 768px) {{
      header {{ padding: 20px 12px 8px; }}
      main {{ padding: 0 10px 32px; }}
      h1 {{ font-size: 1.28rem; }}
      .card-grid {{
        grid-template-columns: 1fr;
        gap: 10px;
      }}
      .card {{
        width: 100%;
        max-width: 100%;
        min-width: 0;
        margin-left: 0;
        margin-right: 0;
        padding: 10px;
        box-sizing: border-box;
        grid-template-columns: 84px 1fr;
      }}
      .cover {{ width: 84px; height: 120px; }}
      .badges {{
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        grid-template-columns: none;
      }}
      .badge {{
        flex: 1 1 calc(50% - 4px);
        min-width: 0;
      }}
      .ext {{ font-size: 0.66rem; padding: 6px 4px; }}
      .ad-slot {{ min-height: 60px; }}
    }}
  </style>
</head>
<body>
  <header>
    <p class="kicker">COMIC RELEASE CALENDAR</p>
    <h1>{html.escape(heading)}</h1>
    <p class="summary">{html.escape(summary)}</p>
    <p class="disclaimer">{html.escape(disclaimer)}</p>
    <p class="legend" id="status-legend">
      凡例:
      <b class="yes" id="legend-yes">特典あり {counts.get(STATUS_YES, 0)}</b>
      <b class="no" id="legend-no">通常/なし {counts.get(STATUS_NO, 0)}</b>
      <b class="todo" id="legend-todo">未確認 {counts.get(STATUS_UNKNOWN, 0)}</b>
    </p>
    <nav class="index-tabs" aria-label="特典一覧">
      <span class="index-label">特典一覧</span>
      {index_links or "—"}
    </nav>
    {tabs_html}
    <div class="search-bar">
      <div class="search-cluster">
        <div class="search-wrap">
          <input id="comic-search" type="search" placeholder="タイトル・著者・出版社で検索"
                 autocomplete="off" spellcheck="false" aria-label="作品を検索"
                 aria-autocomplete="list" aria-controls="search-suggest">
          <button type="button" class="search-clear" id="search-clear" aria-label="検索をクリア">×</button>
          <ul class="search-suggest" id="search-suggest" hidden role="listbox"></ul>
        </div>
        <button type="button" class="search-go" id="search-go" aria-label="検索する">🔍</button>
      </div>
      <p class="search-hit" id="search-hit">{initial_hit}</p>
    </div>
  </header>
  <div class="ad-container ad-header">
    <p class="ad-pr">PR</p>
    <div class="ad-slot"><!-- 上部広告スペース（728x90等） -->広告スペース</div>
  </div>
  <nav class="pager pager-top" id="pager-top" aria-label="ページ送り（上部）" hidden>
    <button type="button" class="pager-btn pager-prev">前へ</button>
    <div class="pager-pages"></div>
    <button type="button" class="pager-btn pager-next">次へ</button>
  </nav>
  <main>
    {body}
    <p class="empty" id="search-empty" hidden>一致する作品がありません。</p>
  </main>
  <div class="ad-container ad-footer">
    <p class="ad-pr">PR</p>
    <div class="ad-slot"><!-- 下部広告スペース -->広告スペース</div>
  </div>
  <nav class="pager pager-bottom" id="pager" aria-label="ページ送り" hidden>
    <button type="button" class="pager-btn pager-prev">前へ</button>
    <div class="pager-pages"></div>
    <button type="button" class="pager-btn pager-next">次へ</button>
  </nav>
  {"<footer class='api-credit'>Supported by Rakuten Developers</footer>" if rakuten_credit else ""}
  <footer class="affiliate-note">このサイトはアフィリエイト広告（Amazonアソシエイト、楽天アフィリエイト、メルカリアンバサダー含む）を掲載しています。</footer>
  <button type="button" class="back-to-top" id="back-to-top" aria-label="TOPに戻る">
    <span class="back-to-top-icon" aria-hidden="true">↑</span>
    <span class="back-to-top-label">TOPに戻る</span>
  </button>
  <script>
    document.querySelectorAll(".copy-title").forEach(function (btn) {{
      var label = "📋 コピー";
      btn.addEventListener("click", function () {{
        var text = btn.getAttribute("data-title") || "";
        var done = function () {{
          btn.textContent = "コピー完了！";
          btn.classList.add("done");
          setTimeout(function () {{
            btn.textContent = label;
            btn.classList.remove("done");
          }}, 1200);
        }};
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(text).then(done).catch(function () {{
            fallbackCopy(text); done();
          }});
        }} else {{
          fallbackCopy(text); done();
        }}
      }});
    }});
    function fallbackCopy(text) {{
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {{ document.execCommand("copy"); }} catch (e) {{}}
      document.body.removeChild(ta);
    }}
    (function () {{
      var input = document.getElementById("comic-search");
      var clearBtn = document.getElementById("search-clear");
      var goBtn = document.getElementById("search-go");
      var suggest = document.getElementById("search-suggest");
      var hit = document.getElementById("search-hit");
      var empty = document.getElementById("search-empty");
      var pagers = document.querySelectorAll(".pager");
      var cluster = input ? input.closest(".search-cluster") : null;
      var PAGE_SIZE = 50;
      var currentPage = 1;
      var monthState = {{}};
      var MAX_SUGGEST = 8;
      function fold(s) {{
        s = String(s || "").normalize("NFKC").toLowerCase();
        var out = "";
        for (var i = 0; i < s.length; i++) {{
          var c = s.charCodeAt(i);
          out += (c >= 0x30A1 && c <= 0x30F6) ? String.fromCharCode(c - 0x60) : s.charAt(i);
        }}
        return out.replace(/[\\s・\\/／\\-−_.,.'\"「」『』()（）\\[\\]]+/g, "");
      }}
      function activePanel() {{
        return document.querySelector(".month-panel.is-active") || document.querySelector(".month-panel");
      }}
      function panelTotal() {{
        var panel = activePanel();
        return panel ? parseInt(panel.getAttribute("data-total") || "0", 10) : 0;
      }}
      function cards() {{
        var panel = activePanel();
        if (!panel) return [];
        var want = panel.getAttribute("data-month") || "";
        return Array.prototype.slice.call(panel.querySelectorAll(".card")).filter(function (card) {{
          var got = card.getAttribute("data-release-month") || "";
          return !want || !got || got === want;
        }});
      }}
      function monthKey() {{
        var panel = activePanel();
        return panel ? (panel.getAttribute("data-month") || "default") : "default";
      }}
      function saveMonthState() {{
        monthState[monthKey()] = {{
          page: currentPage,
          query: input ? input.value : ""
        }};
      }}
      function updateLegend() {{
        var panel = activePanel();
        if (!panel) return;
        var yes = document.getElementById("legend-yes");
        var no = document.getElementById("legend-no");
        var todo = document.getElementById("legend-todo");
        if (yes) yes.textContent = "特典あり " + (panel.getAttribute("data-yes") || "0");
        if (no) no.textContent = "通常/なし " + (panel.getAttribute("data-no") || "0");
        if (todo) todo.textContent = "未確認 " + (panel.getAttribute("data-todo") || "0");
      }}
      function switchMonth(id) {{
        saveMonthState();
        document.querySelectorAll(".month-panel").forEach(function (panel) {{
          var on = panel.getAttribute("data-month") === id;
          panel.classList.toggle("is-active", on);
          panel.hidden = !on;
        }});
        document.querySelectorAll(".month-tab").forEach(function (tab) {{
          var on = tab.getAttribute("data-month") === id;
          tab.classList.toggle("is-active", on);
          tab.setAttribute("aria-selected", on ? "true" : "false");
        }});
        var st = monthState[id] || {{ page: 1, query: "" }};
        currentPage = st.page || 1;
        if (input) input.value = st.query || "";
        updateLegend();
        renderList();
        closeSuggest();
      }}
      function closeSuggest() {{
        if (!suggest) return;
        suggest.hidden = true;
        suggest.innerHTML = "";
      }}
      function matchingCards() {{
        var q = fold(input && input.value);
        return cards().filter(function (card) {{
          return !q || fold(card.getAttribute("data-search") || "").indexOf(q) !== -1;
        }});
      }}
      function applyFilter() {{
        currentPage = 1;
        renderList();
        saveMonthState();
        closeSuggest();
      }}
      function renderList() {{
        var matched = matchingCards();
        var pages = Math.max(1, Math.ceil(matched.length / PAGE_SIZE) || 1);
        if (matched.length === 0) pages = 1;
        if (currentPage > pages) currentPage = pages;
        if (currentPage < 1) currentPage = 1;
        var start = (currentPage - 1) * PAGE_SIZE;
        var visible = matched.slice(start, start + PAGE_SIZE);
        var visibleSet = {{}};
        visible.forEach(function (card) {{ visibleSet[card.id] = true; }});
        var matchSet = {{}};
        matched.forEach(function (card) {{ matchSet[card.id] = true; }});
        var panel = activePanel();
        if (panel) {{
          panel.querySelectorAll(".day-block").forEach(function (sec) {{
          var nMatch = 0;
          var nVis = 0;
          sec.querySelectorAll(".card").forEach(function (card) {{
            if (matchSet[card.id]) nMatch++;
            var onPage = !!visibleSet[card.id];
            card.hidden = !onPage;
            if (onPage) nVis++;
          }});
          sec.hidden = nVis === 0;
          var countEl = sec.querySelector(".count");
          if (countEl) countEl.textContent = nMatch + "作品";
          }});
        }}
        var total = panelTotal();
        var shownFrom = matched.length ? start + 1 : 0;
        var shownTo = start + visible.length;
        if (hit) {{
          if (!matched.length) hit.textContent = total + "件中 0件表示";
          else if (matched.length <= PAGE_SIZE) hit.textContent = total + "件中 " + matched.length + "件表示";
          else hit.textContent = matched.length + "件中 " + shownFrom + "〜" + shownTo + "件表示";
        }}
        if (empty) empty.hidden = matched.length !== 0;
        renderPager(pages, matched.length);
      }}
      function renderPager(pages, matchedCount) {{
        pagers.forEach(function (nav) {{
          if (matchedCount === 0) {{
            nav.hidden = true;
            return;
          }}
          nav.hidden = false;
          var pagesEl = nav.querySelector(".pager-pages");
          var prevBtn = nav.querySelector(".pager-prev");
          var nextBtn = nav.querySelector(".pager-next");
          if (pagesEl) {{
            pagesEl.innerHTML = "";
            for (var p = 1; p <= pages; p++) {{
              var btn = document.createElement("button");
              btn.type = "button";
              btn.className = "pager-btn" + (p === currentPage ? " is-current" : "");
              btn.textContent = String(p);
              if (p === currentPage) btn.setAttribute("aria-current", "page");
              btn.setAttribute("data-page", String(p));
              pagesEl.appendChild(btn);
            }}
          }}
          if (prevBtn) prevBtn.disabled = currentPage <= 1;
          if (nextBtn) nextBtn.disabled = currentPage >= pages;
        }});
      }}
      function goToPage(page) {{
        currentPage = page;
        renderList();
        saveMonthState();
        var topPager = document.getElementById("pager-top") || document.querySelector("main");
        if (topPager && topPager.scrollIntoView) topPager.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }}
      function updateSuggest() {{
        if (!suggest) return;
        var q = fold(input.value);
        if (!q) {{
          closeSuggest();
          return;
        }}
        var matches = matchingCards().slice(0, MAX_SUGGEST);
        if (!matches.length) {{
          closeSuggest();
          return;
        }}
        suggest.innerHTML = matches.map(function (card) {{
          var id = card.id || "";
          var cover = card.getAttribute("data-cover") || "";
          var thumb = cover
            ? '<img class="suggest-thumb" src="' + cover.replace(/"/g, "") + '" alt="" loading="lazy" referrerpolicy="no-referrer">'
            : '<div class="suggest-thumb ph">書影</div>';
          return '<li role="option"><button type="button" class="suggest-item" data-target="' + id + '">' +
            thumb + '<span><span class="suggest-title"></span><span class="suggest-meta"></span></span></button></li>';
        }}).join("");
        Array.prototype.forEach.call(suggest.querySelectorAll(".suggest-item"), function (btn, i) {{
          var card = matches[i];
          btn.querySelector(".suggest-title").textContent = card.getAttribute("data-title") || "";
          btn.querySelector(".suggest-meta").textContent =
            (card.getAttribute("data-publisher") || "") + " · " + (card.getAttribute("data-date") || "");
        }});
        suggest.hidden = false;
      }}
      function focusCard(id) {{
        var card = document.getElementById(id);
        if (!card) return;
        var matched = matchingCards();
        var idx = matched.indexOf(card);
        if (idx < 0) idx = 0;
        currentPage = Math.floor(idx / PAGE_SIZE) + 1;
        renderList();
        closeSuggest();
        card.classList.remove("focus-flash");
        card.scrollIntoView({{ behavior: "smooth", block: "center" }});
        window.setTimeout(function () {{
          card.classList.add("focus-flash");
        }}, 80);
        window.setTimeout(function () {{
          card.classList.remove("focus-flash");
        }}, 3200);
      }}
      pagers.forEach(function (nav) {{
        var prevBtn = nav.querySelector(".pager-prev");
        var nextBtn = nav.querySelector(".pager-next");
        var pagesEl = nav.querySelector(".pager-pages");
        if (prevBtn) prevBtn.addEventListener("click", function () {{
          if (currentPage > 1) goToPage(currentPage - 1);
        }});
        if (nextBtn) nextBtn.addEventListener("click", function () {{
          var pages = Math.max(1, Math.ceil(matchingCards().length / PAGE_SIZE));
          if (currentPage < pages) goToPage(currentPage + 1);
        }});
        if (pagesEl) pagesEl.addEventListener("click", function (ev) {{
          var btn = ev.target.closest("[data-page]");
          if (!btn) return;
          goToPage(parseInt(btn.getAttribute("data-page"), 10) || 1);
        }});
      }});
      document.querySelectorAll(".month-tab").forEach(function (tab) {{
        tab.addEventListener("click", function () {{
          var id = tab.getAttribute("data-month") || "";
          if (!id || id === monthKey()) return;
          switchMonth(id);
        }});
      }});
      var topBtn = document.getElementById("back-to-top");
      if (topBtn) {{
        var onScroll = function () {{
          if (window.scrollY > 300) topBtn.classList.add("is-visible");
          else topBtn.classList.remove("is-visible");
        }};
        window.addEventListener("scroll", onScroll, {{ passive: true }});
        onScroll();
        topBtn.addEventListener("click", function () {{
          window.scrollTo({{ top: 0, behavior: "smooth" }});
        }});
      }}
      if (!input) {{
        renderList();
        return;
      }}
      input.addEventListener("input", updateSuggest);
      input.addEventListener("keydown", function (ev) {{
        if (ev.key === "Enter") {{
          ev.preventDefault();
          applyFilter();
        }} else if (ev.key === "Escape") {{
          closeSuggest();
        }}
      }});
      if (goBtn) goBtn.addEventListener("click", applyFilter);
      if (suggest) {{
        suggest.addEventListener("click", function (ev) {{
          var btn = ev.target.closest(".suggest-item");
          if (!btn) return;
          ev.preventDefault();
          focusCard(btn.getAttribute("data-target") || "");
        }});
      }}
      if (clearBtn) {{
        clearBtn.addEventListener("click", function () {{
          input.value = "";
          input.focus();
          applyFilter();
        }});
      }}
      document.addEventListener("click", function (ev) {{
        if (cluster && cluster.contains(ev.target)) return;
        closeSuggest();
      }});
      renderList();
    }})();
  </script>
</body>
</html>
"""
