"""CSV とカード型HTML（発売日カレンダー）を出力する。"""

from __future__ import annotations

import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from manga_checker.dates import (
    format_release_date,
    parse_release_date,
    year_month_from_pubdate,
)
from manga_checker.links import amazon_url, mercari_url, rakuten_url
from manga_checker.models import Comic, ComicReport, StoreCheck
from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES, privilege_display_text
from manga_checker.publishers import (
    PUBLISHER_ORDER,
    OTHER_PUBLISHER_LABEL,
    publisher_group_label,
    publisher_sort_key,
)
from manga_checker.readings import search_index_text
from manga_checker.stores import STORES

SITE_NAME = "イッコミ特典＋"
SITE_TAGLINE = "コミック第1巻 書店特典チェック"
SITE_TITLE = SITE_NAME
PAGE_TITLE = f"{SITE_NAME}｜{SITE_TAGLINE}"
LOGO_ALT = f"{SITE_NAME} {SITE_TAGLINE}"
SITE_BASE = "https://comic539.github.io/manga-checker"
ASSET_VER = "brand32"
CONTACT_FORM_URL = "https://forms.gle/WF7cNtHZTpr4zGBu5"
CONTACT_EMAIL = "1comi.tokuten.plus@gmail.com"

# A8タグは配布HTMLのまま使う（属性・改行・計測用1pxを改変しない）。
INDEX_AD_TAGS = [
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCDBN+FFHG6Q+4ADS+609HT" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www21.a8.net/svt/bgt?aid=260917619933&wid=001&eno=01&mid=s00000020008001009000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4BCDBN+FFHG6Q+4ADS+609HT" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCL42+1U34XE+4Y6G+5Z6WX" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www27.a8.net/svt/bgt?aid=260927714111&wid=001&eno=01&mid=s00000023092001004000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4BCL42+1U34XE+4Y6G+5Z6WX" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCDBN+FG2VSI+4AHY+5Z6WX" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www23.a8.net/svt/bgt?aid=260917619934&wid=001&eno=01&mid=s00000020023001004000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www14.a8.net/0.gif?a8mat=4BCDBN+FG2VSI+4AHY+5Z6WX" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCL42+6XGN8Y+5FAA+609HT" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www28.a8.net/svt/bgt?aid=260927714419&wid=001&eno=01&mid=s00000025309001009000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4BCL42+6XGN8Y+5FAA+609HT" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCDBO+3KMEQ+1892+6XHHD" rel="nofollow">\n<img border="0" width="728" height="90" alt="" src="https://www29.a8.net/svt/bgt?aid=260917620006&wid=001&eno=01&mid=s00000005735001164000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4BCDBO+3KMEQ+1892+6XHHD" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCDBO+5DHWDU+4RNG+61RI9" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www27.a8.net/svt/bgt?aid=260917620325&wid=001&eno=01&mid=s00000022246001016000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=4BCDBO+5DHWDU+4RNG+61RI9" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCDBO+UD4MQ+37DC+60WN5" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www29.a8.net/svt/bgt?aid=260917620051&wid=001&eno=01&mid=s00000014952001012000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www12.a8.net/0.gif?a8mat=4BCDBO+UD4MQ+37DC+60WN5" alt="">',
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BCL42+5CB16A+41ZK+661TT" rel="nofollow">\n<img border="0" width="468" height="60" alt="" src="https://www27.a8.net/svt/bgt?aid=260927714323&wid=001&eno=01&mid=s00000018920001036000&mc=1"></a>\n<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4BCL42+5CB16A+41ZK+661TT" alt="">',
]
INTRO_NOTES = [
    "第1巻の各書店の特典情報をまとめたチェッカーサイトです。",
    "特典があるのに『特典なし』となる場合がございます。",
    "特典の配布状況の最終確認は各書店の公式商品ページにてご確認ください。",
    "過去に掲載した月は残し、現在月から前後３カ月も合わせて掲載しております",
    "当サイトはアフィリエイト広告(PR)を利用しています。",
]

_STATUS_CLASS = {
    STATUS_YES: "yes",
    STATUS_NO: "no",
    STATUS_UNKNOWN: "todo",
}
_INDEX_TAB_CLASS = {
    "animate": "index-tab-animate",
    "melonbooks": "index-tab-melon",
    "gamers": "index-tab-gamers",
    "comiczin": "index-tab-comiczin",
    "comirano": "index-tab-comirano",
    "kikuya": "index-tab-kikuya",
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
        "レーベル",
        "価格",
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
                "レーベル": report.comic.series,
                "価格": report.comic.item_price or "",
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
    book_dir: Path | None = None,
    sitemap_path: Path | None = None,
    site_base: str | None = None,
    preview_cache_path: Path | None = None,
    fetch_preview: bool = False,
    preview_limit: int = 0,
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
            label = f"{year}/{month}"
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
            f'data-yes="{counts.get(STATUS_YES, 0)}" '
            f'data-no="{counts.get(STATUS_NO, 0) + counts.get(STATUS_UNKNOWN, 0)}" '
            f'data-todo="0" role="tabpanel"{hidden}>'
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
        '<nav class="month-nav" aria-label="発売月">'
        '<button type="button" class="month-shift" id="month-prev" aria-label="前の月">‹</button>'
        '<div class="month-tabs-scroll" id="month-tabs-scroll">'
        f'<div class="month-tabs" role="tablist">{"".join(tabs)}</div>'
        "</div>"
        '<button type="button" class="month-shift" id="month-next" aria-label="次の月">›</button>'
        "</nav>"
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
    summary = INTRO_NOTES[0]
    path.write_text(
        _html_document(
            heading,
            body,
            index_links,
            active_total,
            active_counts,
            tabs_html=tabs_html,
            summary=summary,
            publishers=_publisher_catalog(all_reports),
        ),
        encoding="utf-8",
    )
    if book_dir is not None or sitemap_path is not None:
        from manga_checker.book_pages import write_book_pages, write_sitemap

        base = site_base or SITE_BASE
        if book_dir is not None:
            write_book_pages(
                all_reports,
                book_dir,
                preview_cache_path=preview_cache_path,
                fetch_preview=fetch_preview,
                preview_limit=preview_limit,
            )
        if sitemap_path is not None:
            write_sitemap(all_reports, sitemap_path, site_base=base)


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


def _publisher_catalog(reports: list[ComicReport]) -> list[dict[str, object]]:
    counts: Counter[str] = Counter()
    for report in reports:
        counts[publisher_group_label(report.comic.publisher)] += 1
    items: list[dict[str, object]] = []
    for name in PUBLISHER_ORDER:
        if counts.get(name):
            items.append({"name": name, "count": counts[name]})
    if counts.get(OTHER_PUBLISHER_LABEL):
        items.append({"name": OTHER_PUBLISHER_LABEL, "count": counts[OTHER_PUBLISHER_LABEL]})
    return items


def _card_html(report: ComicReport, card_id: int = 0) -> str:
    comic = report.comic
    badges = "".join(_badge_html(check) for check in report.checks)
    cover = _cover_html(comic)
    author = html.escape(comic.author or "著者未登録")
    publisher = html.escape(comic.publisher_label_line())
    isbn = html.escape(comic.isbn) if comic.isbn else ""
    price = html.escape(comic.price_line())
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
        f'<a class="ext rakuten" href="{html.escape(rakuten)}" target="_blank" '
        'rel="noopener noreferrer"><span class="mark" aria-hidden="true">R</span>楽天ブックス</a>'
        f'<a class="ext mercari" href="{html.escape(mercari)}" target="_blank" '
        'rel="noopener noreferrer"><span class="mark" aria-hidden="true">m</span>mercari</a>'
        "</div>"
    )
    search_blob = html.escape(
        search_index_text(
            comic.display_title,
            comic.author,
            comic.publisher,
            comic.title_kana,
            comic.author_kana,
            comic.series,
        ),
        quote=True,
    )
    from manga_checker.book_pages import book_href, isbn_slug

    href = book_href(comic.isbn)
    isbn_digits = isbn_slug(comic.isbn)
    fav_btn = _fav_button_html(isbn_digits)
    title_html = html.escape(comic.display_title)
    if href:
        title_html = (
            f'<a class="title-link" href="{html.escape(href, quote=True)}">{title_html}</a>'
        )
        cover = (
            f'<a class="cover-link" href="{html.escape(href, quote=True)}">{cover}</a>'
        )
    parsed = parse_release_date(comic.pubdate)
    pub_iso = parsed.isoformat() if parsed else ""
    cover_attr = html.escape(_rakuten_cover_url(comic), quote=True)
    return (
        f'<article class="card" id="comic-card-{card_id}" data-card-id="{card_id}" '
        f'data-isbn="{html.escape(isbn_digits, quote=True)}" '
        f'data-search="{search_blob}" '
        f'data-cover="{cover_attr}" '
        f'data-title="{html.escape(comic.display_title, quote=True)}" '
        f'data-author="{html.escape(comic.author or "", quote=True)}" '
        f'data-kana="{html.escape(" ".join(p for p in (comic.title_kana, comic.author_kana) if p), quote=True)}" '
        f'data-publisher="{html.escape(comic.publisher or "出版社未登録", quote=True)}" '
        f'data-pub-group="{html.escape(publisher_group_label(comic.publisher), quote=True)}" '
        f'data-date="{release}" data-release-month="{release_month_attr}" '
        f'data-pubdate="{html.escape(pub_iso, quote=True)}">'
        '<div class="cover-col">'
        f"{cover}"
        f"{credit}"
        "</div>"
        '<div class="card-body">'
        '<div class="date-row">'
        f'<p class="date-chip">{release}</p>'
        "</div>"
        '<div class="title-row">'
        f"<h3>{title_html}"
        f'<button type="button" class="copy-title" data-title="{html.escape(comic.display_title, quote=True)}">📋 コピー</button>'
        "</h3>"
        "</div>"
        f"{ext}"
        f'<p class="meta">{publisher}</p>'
        f'<p class="meta">{author}</p>'
        f'<p class="isbn">{isbn}</p>'
        f'<p class="meta">{price}</p>'
        f'<div class="badges">{badges}</div>'
        "</div>"
        f"{fav_btn}"
        "</article>"
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


_HEART_SVG = (
    '<svg class="fav-heart" viewBox="0 0 32 32" aria-hidden="true">'
    '<path d="M16 27.2S4.8 19.6 4.8 12.7C4.8 8.6 8 5.8 11.8 5.8c2.2 0 3.8 1.1 4.2 2.6'
    "C16.4 6.9 18 5.8 20.2 5.8 24 5.8 27.2 8.6 27.2 12.7 27.2 19.6 16 27.2 16 27.2z\"/>"
    "</svg>"
)


def _fav_button_html(isbn_digits: str) -> str:
    slug = "".join(ch for ch in (isbn_digits or "") if ch.isdigit())
    if not slug:
        return ""
    return (
        f'<button type="button" class="fav-btn" data-isbn="{html.escape(slug, quote=True)}" '
        'aria-pressed="false" aria-label="お気に入りに追加">'
        f"{_HEART_SVG}</button>"
    )


def _site_legal_html(*, logo_src: str = "logo.png") -> str:
    form = html.escape(CONTACT_FORM_URL, quote=True)
    logo = html.escape(f"{logo_src}?v={ASSET_VER}", quote=True)
    logo_alt = html.escape(LOGO_ALT, quote=True)
    return f"""
  <footer class="site-legal">
    <nav class="site-legal-nav" aria-label="サイト情報">
      <button type="button" data-legal-open="legal-about">サイトについて</button>
      <button type="button" data-legal-open="legal-ad">広告</button>
      <button type="button" data-legal-open="legal-contact">お問い合わせ</button>
    </nav>
    <p class="site-legal-copy">© イッコミ特典＋</p>
  </footer>
  <div class="legal-modal" id="legal-about" hidden>
    <div class="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-about-title">
      <button type="button" class="legal-close" data-legal-close aria-label="閉じる">×</button>
      <h2 id="legal-about-title">サイトについて</h2>
      <img class="legal-about-logo" src="{logo}" alt="{logo_alt}">
      <h3>イッコミ特典＋について</h3>
      <p>当サイト「イッコミ特典＋」は、コミック第1巻の各書店の特典情報をまとめたチェッカーサイトです。</p>
      <p>過去に掲載した月は残し、現在月から3カ月先まで掲載しております。</p>
      <h3>免責事項・掲載情報について</h3>
      <p>各書店の公開情報をもとに自動収集および確認を行っておりますが、システムの仕様上、実際には特典がある場合でも『特典なし』と表示される場合がございます。</p>
      <p>特典の終了、配布条件、仕様変更等が発生する場合もありますので、特典の配布状況の最終確認は各書店の公式商品ページにてご確認ください。</p>
      <p>当サイトの情報を利用したことで生じた損害等について、当サイトは一切の責任を負いかねます。</p>
      <p>なお、当サイトは各出版社様、およびアニメイト様、メロンブックス様、ゲーマーズ様、とらのあな様、COMIC ZIN様、こみらの！様、喜久屋書店様とは一切関係ありません。</p>
      <h3>著作権・商標権について</h3>
      <p>掲載されている書影、特典名、作品名等の権利は、各出版社、著者、書店等の各権利所有者に帰属します。権利を侵害することを目的としたものではありません。</p>
      <p>掲載内容や画像等に問題がある場合は、確認のうえ速やかに修正・削除等の対応をいたします。お問い合わせよりご連絡ください。</p>
    </div>
  </div>
  <div class="legal-modal" id="legal-ad" hidden>
    <div class="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-ad-title">
      <button type="button" class="legal-close" data-legal-close aria-label="閉じる">×</button>
      <h2 id="legal-ad-title">広告掲載について</h2>
      <h3>アフィリエイト広告(PR)の利用</h3>
      <p>当サイトはアフィリエイト広告(PR)を利用しています。</p>
      <p>第三者配信の広告サービスおよびアフィリエイトプログラム（楽天アフィリエイト、A8.net等の各種ASP）に参加しています。</p>
      <p>リンク先の商品は各販売店が販売・管理しているものであり、商品のご購入やお問い合わせにつきましては各ショップ・店舗へ直接ご確認いただきますようお願いいたします。</p>
      <h3>Cookie（クッキー）の利用について</h3>
      <p>当サイトでは、アクセス状況の把握や広告配信のためにCookieを使用することがあります。Cookieはお客様のブラウザを識別するものであり、個人を特定する情報は一切含まれません。ブラウザの設定によりCookieを無効化することも可能です。</p>
    </div>
  </div>
  <div class="legal-modal" id="legal-contact" hidden>
    <div class="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-contact-title">
      <button type="button" class="legal-close" data-legal-close aria-label="閉じる">×</button>
      <h2 id="legal-contact-title">お問い合わせ</h2>
      <p>当サイトに関するご質問、ご要望、または掲載情報の訂正（発売日や特典情報の修正依頼）、権利関係のご連絡は以下のお問い合わせフォームよりお願いいたします。</p>
      <p class="legal-actions">
        <a class="legal-form-btn" href="{form}" target="_blank" rel="noopener noreferrer">お問い合わせフォームを開く（Googleフォーム）</a>
      </p>
      <h3>個人情報の取り扱いについて</h3>
      <p>お問い合わせの際にご入力いただいたお名前（ニックネーム）やメールアドレス等の個人情報は、お問い合わせに対する回答や必要な情報を電子メールなどでご連絡する場合にのみ利用いたします。法令に基づく場合を除き、ご本人の同意なく第三者へ開示・提供することは一切ありません。</p>
    </div>
  </div>
"""


def _site_legal_css() -> str:
    return """
    .site-legal {
      width: 100%;
      max-width: 720px;
      margin: 8px auto 32px;
      padding: 0 16px;
    }
    .site-legal-nav {
      display: flex;
      width: 100%;
      border: 1px solid #d8d0c8;
      background: #fff;
    }
    .site-legal-nav button {
      flex: 1 1 0;
      margin: 0;
      padding: 14px 8px;
      border: 0;
      border-right: 1px solid #d8d0c8;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 0.86rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-align: center;
      cursor: pointer;
      line-height: 1.3;
    }
    .site-legal-nav button:last-child {
      border-right: 0;
    }
    .site-legal-nav button:hover {
      background: #f7f4f0;
      color: var(--accent);
    }
    .site-legal-copy {
      margin: 14px 0 0;
      text-align: center;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.06em;
    }
    .legal-modal {
      position: fixed;
      inset: 0;
      z-index: 5100;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
      background: rgba(42, 33, 28, 0.42);
    }
    .legal-modal[hidden] { display: none !important; }
    .legal-dialog {
      position: relative;
      width: min(640px, 100%);
      max-height: min(82vh, 720px);
      overflow: auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 18px 48px rgba(42, 33, 28, 0.22);
      padding: 28px 28px 24px;
      color: var(--ink);
    }
    .legal-dialog h2 {
      margin: 0 36px 16px 0;
      font-size: 1.12rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding-bottom: 12px;
      border-bottom: 1px solid #ece6df;
    }
    .legal-dialog h3 {
      margin: 18px 0 8px;
      font-size: 0.92rem;
      font-weight: 800;
      color: var(--accent);
    }
    .legal-about-logo {
      display: block;
      width: min(440px, 100%);
      max-width: 100%;
      height: auto;
      margin: 8px auto 20px;
      object-fit: contain;
    }
    .legal-dialog p {
      margin: 0 0 10px;
      font-size: 0.84rem;
      line-height: 1.75;
      color: #4a433e;
    }
    .legal-close {
      position: absolute;
      top: 12px;
      right: 12px;
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 8px;
      background: #f3eee8;
      color: var(--ink);
      font-size: 1.2rem;
      line-height: 1;
      cursor: pointer;
    }
    .legal-close:hover {
      background: #eadfd4;
    }
    .legal-actions {
      margin: 16px 0 14px !important;
      text-align: center;
    }
    .legal-form-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 10px 18px;
      border-radius: 8px;
      background: var(--accent);
      color: #fff !important;
      font-weight: 800;
      font-size: 0.86rem;
      text-decoration: none;
      letter-spacing: 0.02em;
    }
    .legal-form-btn:hover {
      background: #a84c1e;
    }
    .legal-dialog a {
      color: var(--accent);
      word-break: break-all;
    }
    @media (max-width: 768px) {
      .site-legal {
        padding: 0 10px;
        margin-bottom: 24px;
      }
      .site-legal-nav button {
        padding: 12px 4px;
        font-size: 0.72rem;
        letter-spacing: 0.01em;
      }
      .legal-dialog {
        padding: 22px 16px 18px;
        max-height: 86vh;
      }
      .legal-dialog h2 { font-size: 1rem; }
      .legal-dialog p { font-size: 0.8rem; }
      .legal-form-btn {
        width: 100%;
        font-size: 0.8rem;
        padding: 10px 12px;
      }
    }
"""


def _site_legal_script() -> str:
    return """
      function closeLegalModals() {
        document.querySelectorAll(".legal-modal").forEach(function (el) {
          el.hidden = true;
        });
      }
      document.querySelectorAll("[data-legal-open]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-legal-open") || "";
          var modal = document.getElementById(id);
          if (!modal) return;
          closeLegalModals();
          modal.hidden = false;
        });
      });
      document.querySelectorAll("[data-legal-close]").forEach(function (btn) {
        btn.addEventListener("click", closeLegalModals);
      });
      document.querySelectorAll(".legal-modal").forEach(function (modal) {
        modal.addEventListener("click", function (ev) {
          if (ev.target === modal) closeLegalModals();
        });
      });
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") closeLegalModals();
      });
"""


def _badge_html(check: StoreCheck) -> str:
    css, label = _badge_view(check.status)
    title = html.escape(privilege_display_text(check.status, check.detail))
    return (
        f'<a class="badge {css}" href="{html.escape(check.url)}" '
        f'target="_blank" rel="noopener noreferrer" title="{title}">'
        f"<span class='store'>{html.escape(check.store_name)}</span>"
        f"<span class='status'>{html.escape(label)}</span>"
        "</a>"
    )


def _badge_view(status: str) -> tuple[str, str]:
    if status == STATUS_YES:
        return "yes", STATUS_YES
    return "no", STATUS_NO


def _html_document(
    heading: str,
    body: str,
    index_links: str,
    total: int,
    counts: Counter,
    tabs_html: str = "",
    summary: str = "",
    publishers: list[dict[str, object]] | None = None,
) -> str:
    page_size = 50
    if total <= 0:
        initial_hit = "0件中 0件表示"
    elif total <= page_size:
        initial_hit = f"{total}件中 {total}件表示"
    else:
        initial_hit = f"{total}件中 1〜{page_size}件表示"
    if not summary:
        summary = INTRO_NOTES[0]
    publishers = publishers or []
    publishers_json = json.dumps(publishers, ensure_ascii=False)
    legal_html = _site_legal_html()
    return f"""<!DOCTYPE html>
<html lang="ja" data-build="{ASSET_VER}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta http-equiv="Cache-Control" content="no-store">
  <title>{html.escape(PAGE_TITLE)}</title>
  <meta name="description" content="{html.escape(SITE_NAME + '｜' + SITE_TAGLINE)}">
  <meta property="og:site_name" content="{html.escape(SITE_NAME)}">
  <meta property="og:title" content="{html.escape(PAGE_TITLE)}">
  <meta property="og:description" content="{html.escape(summary or SITE_TAGLINE)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{html.escape(SITE_BASE)}/">
  <meta property="og:image" content="{html.escape(SITE_BASE)}/logo.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{html.escape(PAGE_TITLE)}">
  <meta name="twitter:image" content="{html.escape(SITE_BASE)}/logo.png">
  <link rel="icon" type="image/png" href="icon-3.png?v={ASSET_VER}">
  <link rel="shortcut icon" href="favicon.ico?v={ASSET_VER}">
  <style>
    :root {{
      --bg: #ffffff;
      --paper: #f2f2f2;
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
      overflow-x: clip;
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Hiragino Sans", "Yu Gothic", Meiryo, sans-serif;
      background: #fff;
      color: var(--ink);
    }}
    header {{
      padding: 0;
      width: 100%;
      max-width: none;
      margin: 0;
      overflow: visible;
      box-sizing: border-box;
      position: relative;
      z-index: 40;
    }}
    .site-top {{
      position: sticky;
      top: 0;
      z-index: 300;
      background: #fff;
      border-bottom: 1px solid #ececec;
      box-shadow: 0 1px 0 rgba(0,0,0,0.04);
    }}
    .site-top-inner {{
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      max-width: 1360px;
      margin: 0 auto;
      padding: 2px 16px;
      box-sizing: border-box;
    }}
    .header-actions {{
      align-self: center;
      margin-top: 0;
    }}
    .site-intro {{
      width: 100%;
      max-width: 1360px;
      margin: 0 auto;
      padding: 12px 24px 12px;
      box-sizing: border-box;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 1.6rem;
      letter-spacing: 0.04em;
    }}
    .logo-link {{
      display: block;
      flex: 0 0 280px;
      width: 280px;
      max-width: 100%;
      margin: 0;
      line-height: 0;
    }}
    .site-logo {{
      display: block;
      width: 280px;
      max-width: 100%;
      height: 72px;
      object-fit: contain;
      object-position: left center;
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
      margin: 8px 0 6px;
    }}
    .affiliate-notice {{
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
      max-width: 46rem;
      margin: 0 0 10px;
    }}
    .month-nav {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: fit-content;
      max-width: 100%;
      margin: 16px auto 4px;
      min-width: 0;
    }}
    .month-shift {{
      flex: 0 0 auto;
      width: 36px;
      min-width: 36px;
      height: 36px;
      padding: 0;
      border: 0;
      border-radius: 999px;
      background: #fffaf3;
      color: var(--ink);
      font: inherit;
      font-size: 1.35rem;
      font-weight: 800;
      line-height: 1;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      cursor: pointer;
      white-space: nowrap;
    }}
    .month-shift:hover:not(:disabled) {{
      background: #f3e6d6;
    }}
    .month-shift:disabled {{
      opacity: 0.35;
      cursor: default;
    }}
    .month-tabs-scroll {{
      flex: 0 1 auto;
      width: max-content;
      max-width: min(22.8em, calc(100vw - 6.2em));
      min-width: 0;
      overflow-x: auto;
      overscroll-behavior-x: contain;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
      scroll-snap-type: x proximity;
      touch-action: pan-x;
    }}
    .month-tabs {{
      display: flex;
      flex-wrap: nowrap;
      gap: 8px;
      width: max-content;
      margin: 0;
    }}
    .month-tab {{
      flex: 0 0 auto;
      min-width: 6.4em;
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
      scroll-snap-align: start;
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
    .index-tab-comiczin,
    .index-tab[data-store="comiczin"] {{
      background: #c4122f;
      color: #fff;
    }}
    .index-tab-comirano,
    .index-tab[data-store="comirano"] {{
      background: #4ba7ee;
      color: #07324d;
    }}
    /* 喜久屋書店: 薄い紫 */
    .index-tab-kikuya,
    .index-tab[data-store="kikuya"] {{
      background: #e4c7f5;
      color: #3a1a55;
    }}
    .month-panel[hidden] {{
      display: none !important;
    }}
    .search-bar {{
      display: flex;
      flex: 0 0 260px;
      flex-wrap: nowrap;
      align-items: center;
      gap: 8px;
      margin: 0;
      min-width: 0;
      max-width: 260px;
      width: 260px;
    }}
    .search-wrap {{
      position: relative;
      display: flex;
      align-items: center;
      width: 100%;
      min-width: 0;
      z-index: 50;
      height: 40px;
      padding: 0 6px 0 14px;
      border: 1px solid #e5e5e5;
      border-radius: 999px;
      background: #f6f6f6;
    }}
    .search-wrap:focus-within {{
      background: #fff;
      border-color: #d0d0d0;
      box-shadow: 0 0 0 3px rgba(196, 92, 38, 0.12);
    }}
    .search-wrap input {{
      flex: 1 1 auto;
      width: 100%;
      min-width: 0;
      height: 38px;
      padding: 0 4px;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: var(--ink);
      font-size: 0.86rem;
      font-family: inherit;
    }}
    .search-wrap input:focus {{
      outline: none;
    }}
    .search-wrap input::-webkit-search-cancel-button {{
      -webkit-appearance: none;
    }}
    .search-clear {{
      flex: 0 0 auto;
      width: 22px;
      height: 22px;
      margin-right: 2px;
      border: 0;
      border-radius: 50%;
      background: #d8d8d8;
      color: #fff;
      font-size: 0.85rem;
      line-height: 1;
      cursor: pointer;
    }}
    .search-clear[hidden] {{
      display: none !important;
    }}
    .search-clear:hover {{
      background: #bfbfbf;
    }}
    .search-go {{
      flex: 0 0 auto;
      width: 32px;
      height: 32px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: #8a8a8a;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .search-go svg {{
      display: block;
      width: 18px;
      height: 18px;
    }}
    .search-go:hover {{
      color: var(--ink);
    }}
    .search-suggest {{
      position: fixed;
      margin: 0;
      padding: 6px 0;
      list-style: none;
      background: #fffaf3;
      border: 1px solid #e2d5c4;
      border-radius: 12px;
      box-shadow: 0 12px 28px rgba(80, 50, 20, 0.16);
      z-index: 4000;
      max-height: min(360px, 50vh);
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
      margin: 0 auto 12px;
      padding: 0 16px;
      text-align: center;
      white-space: nowrap;
    }}
    .search-hit[hidden] {{ display: none !important; }}
    .pub-btn {{
      flex: 0 0 auto;
      padding: 8px 12px;
      border: 0;
      border-radius: 999px;
      background: #e9f7ef;
      color: #1b6b40;
      font: inherit;
      font-size: 0.78rem;
      font-weight: 800;
      cursor: pointer;
      white-space: nowrap;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    .pub-btn:hover {{
      background: #d4eedf;
    }}
    .pub-btn.is-on {{
      background: #c5e8d3;
      color: #14532d;
    }}
    .fav-list-btn {{
      flex: 0 0 auto;
      padding: 8px 12px;
      border: 0;
      border-radius: 999px;
      background: #fff0f6;
      color: #c2185b;
      font: inherit;
      font-size: 0.78rem;
      font-weight: 800;
      cursor: pointer;
      white-space: nowrap;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    .fav-list-btn:hover {{
      background: #ffd6ea;
    }}
    .fav-list-btn.is-on {{
      background: #ff2eb8;
      color: #fff;
    }}
    .header-actions {{
      display: flex;
      flex: 0 0 auto;
      align-items: center;
      gap: 8px;
      margin-left: auto;
    }}
    .cal-btn {{
      flex: 0 0 auto;
      padding: 8px 12px;
      border: 0;
      border-radius: 999px;
      background: #eef6ff;
      color: #1565c0;
      font: inherit;
      font-size: 0.78rem;
      font-weight: 800;
      cursor: pointer;
      white-space: nowrap;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    .cal-btn:hover {{
      background: #d6ebff;
    }}
    .cal-modal {{
      position: fixed;
      inset: 0;
      z-index: 5000;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 72px 16px 24px;
      background: rgba(42, 33, 28, 0.35);
    }}
    .cal-modal[hidden] {{ display: none !important; }}
    .cal-dialog {{
      width: min(560px, 100%);
      max-height: calc(100vh - 96px);
      overflow: auto;
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 16px 40px rgba(80, 50, 20, 0.22);
      padding: 16px 16px 20px;
    }}
    .pub-list {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .pub-item {{
      display: flex;
      align-items: center;
      width: 100%;
      min-height: 52px;
      padding: 12px 14px;
      border: 1px solid transparent;
      border-radius: 14px;
      text-align: left;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .pub-item:hover,
    .pub-item.is-on {{
      box-shadow: 0 2px 8px rgba(80, 50, 20, 0.12);
      filter: saturate(1.08);
    }}
    .pub-item strong {{
      display: block;
      font-size: 0.88rem;
      line-height: 1.4;
      font-weight: 800;
    }}
    .pub-clear {{
      margin: 0 0 12px;
      padding: 6px 12px;
      border: 0;
      border-radius: 999px;
      background: #f3e6d6;
      font: inherit;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
    }}
    .cal-head {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 12px;
    }}
    .cal-head h2 {{
      margin: 0;
      text-align: center;
      font-size: 1.05rem;
      line-height: 1.2;
    }}
    .cal-title-block {{
      flex: 1 1 auto;
      min-width: 0;
      text-align: center;
    }}
    .cal-month-total {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .cal-nav,
    .cal-close {{
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 8px;
      background: #f3e6d6;
      color: var(--ink);
      font-size: 1.1rem;
      cursor: pointer;
    }}
    .cal-week,
    .cal-grid {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 4px;
    }}
    .cal-week span {{
      text-align: center;
      font-size: 0.72rem;
      font-weight: 800;
      color: var(--muted);
      padding: 4px 0;
    }}
    .cal-cell {{
      min-height: 54px;
      border: 0;
      border-radius: 10px;
      background: #f7f4f0;
      color: var(--ink);
      font: inherit;
      cursor: pointer;
      padding: 4px 2px 6px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
    }}
    .cal-cell[disabled] {{
      background: transparent;
      cursor: default;
    }}
    .cal-cell.is-empty {{ visibility: hidden; }}
    .cal-cell.is-on {{
      outline: 2px solid var(--accent);
      background: #fff4ea;
    }}
    .cal-num {{ font-size: 0.82rem; font-weight: 700; }}
    .cal-count {{
      min-width: 1.6em;
      padding: 1px 6px;
      border-radius: 999px;
      background: #c45c26;
      color: #fff;
      font-size: 0.68rem;
      font-weight: 800;
    }}
    .cal-cell.is-zero .cal-count {{
      display: none;
    }}
    .cal-day-list {{
      margin: 14px 0 0;
      padding: 12px 0 0;
      border-top: 1px solid #ececec;
    }}
    .cal-day-list h3 {{
      margin: 0 0 8px;
      font-size: 0.95rem;
    }}
    .cal-day-list ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .cal-day-item {{
      display: grid;
      grid-template-columns: 40px 1fr;
      gap: 10px;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }}
    .cal-day-item img,
    .cal-day-item .ph {{
      width: 40px;
      height: 56px;
      object-fit: cover;
      border-radius: 4px;
      background: #d9cfc3;
    }}
    .cal-day-item .ph {{
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.55rem;
      color: #8a7f75;
    }}
    .cal-day-item strong {{
      display: block;
      font-size: 0.86rem;
      line-height: 1.35;
    }}
    .cal-day-item span {{
      color: var(--muted);
      font-size: 0.72rem;
    }}
    .day-filter-bar {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 8px 0 0;
      font-size: 0.86rem;
    }}
    .day-filter-bar[hidden] {{ display: none !important; }}
    .day-filter-bar button {{
      border: 0;
      border-radius: 999px;
      background: #f3e6d6;
      color: var(--ink);
      font: inherit;
      font-size: 0.78rem;
      font-weight: 700;
      padding: 4px 10px;
      cursor: pointer;
    }}
    .fav-btn {{
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 2;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
      cursor: pointer;
    }}
    .fav-heart {{
      width: 30px;
      height: 30px;
      fill: #fff;
      stroke: none;
      filter: drop-shadow(0 1px 2px rgba(0,0,0,0.12)) drop-shadow(0 3px 8px rgba(0,0,0,0.18));
    }}
    .fav-btn.is-on .fav-heart {{
      fill: #ff2eb8;
      filter: drop-shadow(0 1px 2px rgba(255,46,184,0.25));
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
      position: relative;
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
      margin: 0 0 6px;
      padding-right: 36px;
    }}
    .title-row h3 .copy-title {{
      display: inline;
      vertical-align: middle;
      margin-left: 4px;
    }}
    .title-link {{
      color: inherit;
      text-decoration: none;
    }}
    .title-link:hover {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .cover-link {{
      display: block;
      color: inherit;
      text-decoration: none;
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
    .date-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 6px;
      padding-right: 36px;
    }}
    .date-chip {{
      display: inline-block;
      margin: 0;
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
    .site-legal {{
      width: 100%;
      max-width: 720px;
      margin: 8px auto 32px;
      padding: 0 16px;
    }}
    .site-legal-nav {{
      display: flex;
      width: 100%;
      border: 1px solid #d8d0c8;
      background: #fff;
    }}
    .site-legal-nav button {{
      flex: 1 1 0;
      margin: 0;
      padding: 14px 8px;
      border: 0;
      border-right: 1px solid #d8d0c8;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 0.86rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-align: center;
      cursor: pointer;
      line-height: 1.3;
    }}
    .site-legal-nav button:last-child {{
      border-right: 0;
    }}
    .site-legal-nav button:hover {{
      background: #f7f4f0;
      color: var(--accent);
    }}
    .site-legal-copy {{
      margin: 14px 0 0;
      text-align: center;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.06em;
    }}
    .legal-modal {{
      position: fixed;
      inset: 0;
      z-index: 5100;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
      background: rgba(42, 33, 28, 0.42);
    }}
    .legal-modal[hidden] {{ display: none !important; }}
    .legal-dialog {{
      position: relative;
      width: min(640px, 100%);
      max-height: min(82vh, 720px);
      overflow: auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 18px 48px rgba(42, 33, 28, 0.22);
      padding: 28px 28px 24px;
      color: var(--ink);
    }}
    .legal-dialog h2 {{
      margin: 0 36px 16px 0;
      font-size: 1.12rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      padding-bottom: 12px;
      border-bottom: 1px solid #ece6df;
    }}
    .legal-dialog h3 {{
      margin: 18px 0 8px;
      font-size: 0.92rem;
      font-weight: 800;
      color: var(--accent);
    }}
    .legal-about-logo {{
      display: block;
      width: min(440px, 100%);
      max-width: 100%;
      height: auto;
      margin: 8px auto 20px;
      object-fit: contain;
    }}
    .legal-dialog p {{
      margin: 0 0 10px;
      font-size: 0.84rem;
      line-height: 1.75;
      color: #4a433e;
    }}
    .legal-close {{
      position: absolute;
      top: 12px;
      right: 12px;
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 8px;
      background: #f3eee8;
      color: var(--ink);
      font-size: 1.2rem;
      line-height: 1;
      cursor: pointer;
    }}
    .legal-close:hover {{
      background: #eadfd4;
    }}
    .legal-actions {{
      margin: 16px 0 14px !important;
      text-align: center;
    }}
    .legal-form-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 10px 18px;
      border-radius: 8px;
      background: var(--accent);
      color: #fff !important;
      font-weight: 800;
      font-size: 0.86rem;
      text-decoration: none;
      letter-spacing: 0.02em;
    }}
    .legal-form-btn:hover {{
      background: #a84c1e;
    }}
    .legal-dialog a {{
      color: var(--accent);
      word-break: break-all;
    }}
    .meta, .isbn {{
      margin: 0;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.4;
    }}
    .ext-links {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 6px;
      margin: 0 0 8px;
      align-items: stretch;
    }}
    .ext {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      min-height: 22px;
      padding: 4px 6px;
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
      width: 1em;
      height: 1em;
      border-radius: 50%;
      font-size: 0.62rem;
      font-weight: 900;
      flex: 0 0 auto;
    }}
    .ext.amazon {{
      background: #1877f2;
      color: #ff9900;
    }}
    .ext.amazon .mark {{ background: #ff9900; color: #1877f2; }}
    .ext.rakuten {{
      background: #c41e3a;
      color: #fff;
    }}
    .ext.rakuten .mark {{ background: #fff; color: #c41e3a; }}
    .ext.mercari {{
      background: #4ba7ee;
      color: #ff0211;
    }}
    .ext.mercari .mark {{ background: #ff0211; color: #fff; }}
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
    .ad-slot {{
      position: relative;
      display: flex;
      flex-wrap: wrap;
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
      box-sizing: border-box;
    }}
    .ad-slot:has(a) {{
      background: transparent;
      border: none;
      color: inherit;
    }}
    .ad-slot > a {{
      display: block;
      max-width: 100%;
      margin: 0 auto;
    }}
    .ad-container iframe,
    .ad-container ins,
    .ad-slot > a img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    .ad-slot > img {{
      position: absolute;
      width: 1px;
      height: 1px;
      max-width: 1px;
      border: 0;
    }}
    .ad-header {{
      margin-top: 8px;
      margin-bottom: 12px;
    }}
    .ad-header .ad-row {{
      max-width: 728px;
      align-items: center;
    }}
    .ad-header .ad-slot {{
      width: 100%;
      max-width: 728px;
      min-height: 60px;
    }}
    .ad-footer {{
      margin-bottom: 8px;
    }}
    .ad-row {{
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
      gap: 16px;
      width: 100%;
      max-width: 728px;
      margin: 0 auto;
    }}
    .ad-row .ad-slot {{
      width: auto;
      max-width: 100%;
      min-height: 60px;
      flex: 0 1 auto;
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
      margin-bottom: 16px;
      padding-bottom: 8px;
    }}
    .month-count {{
      max-width: 1360px;
      margin: 0 auto 8px;
      padding: 0 16px 4px;
      color: var(--muted);
      font-size: 0.92rem;
      font-weight: 700;
      text-align: center;
    }}
    .month-count[hidden] {{ display: none !important; }}
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
      header {{ padding: 0; }}
      .site-top-inner {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        grid-template-areas:
          "logo actions"
          "search search";
        align-items: center;
        padding: 6px 8px 8px;
        gap: 6px 8px;
      }}
      .logo-link {{
        grid-area: logo;
      }}
      .header-actions {{
        grid-area: actions;
        flex-direction: row;
        flex-wrap: wrap;
        justify-content: flex-end;
        align-items: center;
        gap: 4px;
        margin: 0;
      }}
      .search-bar {{
        grid-area: search;
        width: 100%;
        max-width: none;
        flex: 1 1 auto;
        margin: 0;
      }}
      .site-intro {{ padding: 10px 12px 8px; }}
      main {{ padding: 0 10px 32px; }}
      h1 {{ font-size: 1.28rem; }}
      .logo-link,
      .site-logo {{
        flex: none;
        width: 132px;
        max-width: 132px;
      }}
      .site-logo {{
        height: 42px;
      }}
      .search-wrap {{
        height: 34px;
        padding: 0 4px 0 10px;
      }}
      .search-wrap input {{
        height: 32px;
        padding: 0 2px;
        font-size: 0.72rem;
      }}
      .search-clear {{
        width: 18px;
        height: 18px;
        font-size: 0.75rem;
      }}
      .search-go {{ width: 26px; height: 26px; }}
      .search-go svg {{ width: 15px; height: 15px; }}
      .fav-list-btn,
      .cal-btn,
      .pub-btn {{
        font-size: 0.58rem;
        padding: 4px 6px;
        line-height: 1.2;
      }}
      .month-shift {{
        width: 32px;
        min-width: 32px;
        height: 32px;
        font-size: 1.2rem;
      }}
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
      .ext-links {{
        grid-template-columns: 1fr;
        gap: 5px;
        margin: 0 0 8px;
      }}
      .ext {{
        width: 100%;
        min-height: 22px;
        padding: 4px 10px;
        font-size: 0.72rem;
        box-sizing: border-box;
      }}
      .ad-slot {{ min-height: 60px; }}
      .ad-row {{ flex-direction: column; }}
      .site-legal {{
        padding: 0 10px;
        margin-bottom: 24px;
      }}
      .site-legal-nav button {{
        padding: 12px 4px;
        font-size: 0.72rem;
        letter-spacing: 0.01em;
      }}
      .legal-dialog {{
        padding: 22px 16px 18px;
        max-height: 86vh;
      }}
      .legal-dialog h2 {{ font-size: 1rem; }}
      .legal-dialog p {{ font-size: 0.8rem; }}
      .legal-form-btn {{
        width: 100%;
        font-size: 0.8rem;
        padding: 10px 12px;
      }}
      .logo-link,
      .site-logo {{
        flex: none;
        width: 132px;
        max-width: 132px;
      }}
      .site-logo {{
        height: 42px;
      }}
    }}
  </style>
</head>
<body>
  <div class="site-top">
    <div class="site-top-inner">
      <a class="logo-link" href="./index.html">
        <img class="site-logo" src="logo.png?v={ASSET_VER}" alt="{html.escape(LOGO_ALT, quote=True)}">
      </a>
      <div class="search-bar">
        <div class="search-wrap" id="search-wrap">
          <input id="comic-search" type="search" placeholder="タイトル・著者で検索"
                 autocomplete="off" spellcheck="false" aria-label="作品を検索"
                 aria-autocomplete="list" aria-controls="search-suggest">
          <button type="button" class="search-clear" id="search-clear" hidden aria-label="検索をクリア">×</button>
          <button type="button" class="search-go" id="search-go" aria-label="検索する">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="2"></circle>
              <path d="M16.2 16.2L21 21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
            </svg>
          </button>
          <ul class="search-suggest" id="search-suggest" hidden role="listbox"></ul>
        </div>
      </div>
      <div class="header-actions">
        <button type="button" class="cal-btn" id="cal-btn" aria-haspopup="dialog" aria-controls="cal-modal">📅 カレンダー</button>
        <button type="button" class="pub-btn" id="pub-btn" aria-haspopup="dialog" aria-controls="pub-modal">出版社一覧</button>
        <button type="button" class="fav-list-btn" id="fav-list-btn">お気に入り一覧</button>
      </div>
    </div>
  </div>
  <header>
    <div class="site-intro">
    {tabs_html}
    <p class="day-filter-bar" id="day-filter-bar" hidden>
      <span id="day-filter-label"></span>
      <button type="button" id="day-filter-clear">この日の絞り込みを解除</button>
    </p>
    <p class="day-filter-bar" id="pub-filter-bar" hidden>
      <span id="pub-filter-label"></span>
      <button type="button" id="pub-filter-clear">出版社の絞り込みを解除</button>
    </p>
    </div>
  </header>
  <nav class="pager pager-top" id="pager-top" aria-label="ページ送り（上部）" hidden>
    <button type="button" class="pager-btn pager-prev">前へ</button>
    <div class="pager-pages"></div>
    <button type="button" class="pager-btn pager-next">次へ</button>
  </nav>
  <div class="ad-container ad-header" id="ad-header">
    <div class="ad-row">
      <div class="ad-slot" id="ad-slot-top"></div>
    </div>
  </div>
  <p class="search-hit" id="search-hit">{initial_hit}</p>
  <main>
    {body}
    <p class="empty" id="search-empty" hidden>一致する作品がありません。</p>
  </main>
  <div class="ad-container ad-footer" id="ad-footer">
    <div class="ad-row">
      <div class="ad-slot" id="ad-slot-bottom"></div>
    </div>
  </div>
  <nav class="pager pager-bottom" id="pager" aria-label="ページ送り" hidden>
    <button type="button" class="pager-btn pager-prev">前へ</button>
    <div class="pager-pages"></div>
    <button type="button" class="pager-btn pager-next">次へ</button>
  </nav>
  {legal_html}
  <button type="button" class="back-to-top" id="back-to-top" aria-label="TOPに戻る">
    <span class="back-to-top-icon" aria-hidden="true">↑</span>
    <span class="back-to-top-label">TOPに戻る</span>
  </button>
  <div class="cal-modal" id="cal-modal" hidden>
    <div class="cal-dialog" role="dialog" aria-modal="true" aria-labelledby="cal-title">
      <div class="cal-head">
        <button type="button" class="cal-nav" id="cal-prev" aria-label="前の月">‹</button>
        <div class="cal-title-block">
          <h2 id="cal-title">カレンダー</h2>
          <p class="cal-month-total" id="cal-month-total"></p>
        </div>
        <button type="button" class="cal-nav" id="cal-next" aria-label="次の月">›</button>
        <button type="button" class="cal-close" id="cal-close" aria-label="閉じる">×</button>
      </div>
      <div class="cal-week" aria-hidden="true"><span>月</span><span>火</span><span>水</span><span>木</span><span>金</span><span>土</span><span>日</span></div>
      <div class="cal-grid" id="cal-grid"></div>
      <div class="cal-day-list" id="cal-day-list" hidden></div>
    </div>
  </div>
  <div class="cal-modal" id="pub-modal" hidden>
    <div class="cal-dialog" role="dialog" aria-modal="true" aria-labelledby="pub-title">
      <div class="cal-head">
        <h2 id="pub-title">出版社一覧</h2>
        <button type="button" class="cal-close" id="pub-close" aria-label="閉じる">×</button>
      </div>
      <button type="button" class="pub-clear" id="pub-clear">絞り込みを解除</button>
      <div class="pub-list" id="pub-list"></div>
    </div>
  </div>
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
      var cluster = input ? input.closest(".search-wrap") : null;
      var PAGE_SIZE = 50;
      var currentPage = 1;
      var dayFilter = "";
      var publisherFilter = "";
      var monthState = {{}};
      var MAX_SUGGEST = 8;
      var FAV_KEY = "ichikomi-favorites-v1";
      var favMode = false;
      var favs = {{}};
      var PUBLISHERS = {publishers_json};
      var INDEX_ADS = {json.dumps(INDEX_AD_TAGS, ensure_ascii=False)};
      function shuffleAds() {{
        var tags = INDEX_ADS.slice();
        var i, j, tmp;
        for (i = tags.length - 1; i > 0; i--) {{
          j = Math.floor(Math.random() * (i + 1));
          tmp = tags[i];
          tags[i] = tags[j];
          tags[j] = tmp;
        }}
        var top = document.getElementById("ad-slot-top");
        var bottom = document.getElementById("ad-slot-bottom");
        if (top) top.innerHTML = tags[0] || "";
        if (bottom) bottom.innerHTML = tags.length > 1 ? tags[1] : (tags[0] || "");
      }}
      shuffleAds();
      function stickyHeaderOffset() {{
        var header = document.querySelector(".site-top");
        return header ? Math.ceil(header.getBoundingClientRect().height) + 8 : 8;
      }}
      function scrollToPagerAndAds() {{
        var pager = document.getElementById("pager-top");
        var target = document.querySelector(".month-nav") || ((pager && !pager.hidden) ? pager : document.getElementById("ad-header"));
        if (!target) {{
          window.scrollTo({{ top: 0, behavior: "smooth" }});
          return;
        }}
        var y = target.getBoundingClientRect().top + window.scrollY - stickyHeaderOffset();
        window.scrollTo({{ top: Math.max(0, y), behavior: "smooth" }});
      }}
      function loadFavs() {{
        try {{
          var raw = JSON.parse(localStorage.getItem(FAV_KEY) || "[]");
          var map = {{}};
          (Array.isArray(raw) ? raw : []).forEach(function (id) {{
            if (id) map[String(id)] = true;
          }});
          return map;
        }} catch (e) {{
          return {{}};
        }}
      }}
      function saveFavs() {{
        try {{
          localStorage.setItem(FAV_KEY, JSON.stringify(Object.keys(favs)));
        }} catch (e) {{}}
      }}
      function isFav(isbn) {{
        return !!(isbn && favs[isbn]);
      }}
      function paintFavs() {{
        document.querySelectorAll(".fav-btn").forEach(function (btn) {{
          var on = isFav(btn.getAttribute("data-isbn") || "");
          btn.classList.toggle("is-on", on);
          btn.setAttribute("aria-pressed", on ? "true" : "false");
          btn.setAttribute("aria-label", on ? "お気に入りから外す" : "お気に入りに追加");
        }});
      }}
      function setFavMode(on) {{
        favMode = !!on;
        document.body.classList.toggle("fav-mode", favMode);
        var favListBtn = document.getElementById("fav-list-btn");
        if (favListBtn) {{
          favListBtn.classList.toggle("is-on", favMode);
          favListBtn.textContent = favMode ? "一覧に戻る" : "お気に入り一覧";
        }}
        if (empty) empty.textContent = favMode ? "お気に入りはまだありません。" : "一致する作品がありません。";
        if (!favMode) {{
          var id = monthKey();
          document.querySelectorAll(".month-panel").forEach(function (panel) {{
            var onp = panel.getAttribute("data-month") === id;
            panel.classList.toggle("is-active", onp);
            panel.hidden = !onp;
          }});
        }}
        if (on) {{
          publisherFilter = "";
          updatePubBar();
        }}
        currentPage = 1;
        renderList();
      }}
      favs = loadFavs();
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
        if (favMode) return allCards();
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
      var LIST_POS_KEY = "ichikomi-list-pos-v1";
      function saveListPos(extra) {{
        extra = extra || {{}};
        try {{
          sessionStorage.setItem(LIST_POS_KEY, JSON.stringify({{
            month: monthKey(),
            page: currentPage,
            query: input ? input.value : "",
            fav: favMode,
            pub: publisherFilter,
            day: dayFilter,
            card: extra.card || "",
            scroll: (typeof extra.scroll === "number") ? extra.scroll : window.scrollY
          }}));
        }} catch (e) {{}}
      }}
      function loadListPos() {{
        try {{
          var raw = sessionStorage.getItem(LIST_POS_KEY);
          return raw ? JSON.parse(raw) : null;
        }} catch (e) {{
          return null;
        }}
      }}
      function applyListPos(st) {{
        if (!st) return false;
        if (st.fav) {{
          favMode = true;
          document.body.classList.toggle("fav-mode", true);
          var favListBtn = document.getElementById("fav-list-btn");
          if (favListBtn) {{
            favListBtn.classList.toggle("is-on", true);
            favListBtn.textContent = "一覧に戻る";
          }}
          if (empty) empty.textContent = "お気に入りはまだありません。";
        }} else if (st.month) {{
          document.querySelectorAll(".month-panel").forEach(function (panel) {{
            var on = panel.getAttribute("data-month") === st.month;
            panel.classList.toggle("is-active", on);
            panel.hidden = !on;
          }});
          document.querySelectorAll(".month-tab").forEach(function (tab) {{
            var on = tab.getAttribute("data-month") === st.month;
            tab.classList.toggle("is-active", on);
            tab.setAttribute("aria-selected", on ? "true" : "false");
          }});
        }}
        if (input && typeof st.query === "string") input.value = st.query;
        if (typeof st.day === "string") dayFilter = st.day;
        if (typeof st.pub === "string") publisherFilter = st.pub;
        currentPage = st.page || 1;
        updateLegend();
        updateDayBar();
        updatePubBar();
        syncSearchClear();
        renderList();
        window.setTimeout(function () {{
          var card = st.card ? document.getElementById(st.card) : null;
          if (card && !card.hidden && card.scrollIntoView) {{
            card.scrollIntoView({{ behavior: "auto", block: "center" }});
          }} else if (typeof st.scroll === "number") {{
            window.scrollTo(0, st.scroll);
          }}
        }}, 0);
        return true;
      }}
      function updateLegend() {{
        var panel = activePanel();
        if (!panel) return;
        var yes = document.getElementById("legend-yes");
        var no = document.getElementById("legend-no");
        var todo = document.getElementById("legend-todo");
        if (yes) yes.textContent = "特典あり " + (panel.getAttribute("data-yes") || "0");
        if (no) no.textContent = "特典なし " + (panel.getAttribute("data-no") || "0");
        if (todo) todo.textContent = "";
      }}
      function allCards() {{
        return Array.prototype.slice.call(document.querySelectorAll(".month-panel .card"));
      }}
      function cardMatches(card, q) {{
        if (publisherFilter) {{
          var g = card.getAttribute("data-pub-group") || "";
          if (g !== publisherFilter) return false;
        }}
        if (favMode && !isFav(card.getAttribute("data-isbn") || "")) return false;
        if (!q) return true;
        var title = fold(card.getAttribute("data-title") || "");
        if (title.indexOf(q) !== -1) return true;
        if (q.length < 3) return false;
        var author = fold(card.getAttribute("data-author") || "");
        var kana = fold(card.getAttribute("data-kana") || "");
        if (author.indexOf(q) !== -1 || kana.indexOf(q) !== -1) return true;
        return fold(card.getAttribute("data-search") || "").indexOf(q) !== -1;
      }}
      function matchingAllCards() {{
        var q = fold(input && input.value);
        if (!q && !favMode) return [];
        return allCards().filter(function (card) {{
          return cardMatches(card, q);
        }});
      }}
      function cardMonth(card) {{
        if (!card) return "";
        var panel = card.closest(".month-panel");
        return (panel && panel.getAttribute("data-month")) || card.getAttribute("data-release-month") || "";
      }}
      function switchMonth(id, keepQuery, keepDay) {{
        var q = input ? input.value : "";
        saveMonthState();
        if (!keepDay) dayFilter = "";
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
        currentPage = keepQuery ? 1 : (st.page || 1);
        if (input) input.value = keepQuery ? q : (st.query || "");
        updateLegend();
        updateDayBar();
        updatePubBar();
        renderList();
        if (!keepQuery) closeSuggest();
        shuffleAds();
        scrollToPagerAndAds();
        syncMonthWindow();
      }}
      function closeSuggest() {{
        if (!suggest) return;
        suggest.hidden = true;
        suggest.innerHTML = "";
      }}
      function placeSuggest() {{
        if (!suggest || suggest.hidden || !input) return;
        var r = input.getBoundingClientRect();
        var width = Math.max(r.width, 280);
        var left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
        var top = r.bottom + 4;
        var maxH = Math.min(360, Math.max(120, window.innerHeight - top - 12));
        suggest.style.left = left + "px";
        suggest.style.width = width + "px";
        suggest.style.top = top + "px";
        suggest.style.maxHeight = maxH + "px";
      }}
      function matchingCards() {{
        var q = fold(input && input.value);
        var seen = {{}};
        return cards().filter(function (card) {{
          if (dayFilter && (card.getAttribute("data-pubdate") || "") !== dayFilter) return false;
          if (!cardMatches(card, q)) return false;
          if (favMode) {{
            var isbn = card.getAttribute("data-isbn") || "";
            if (isbn && seen[isbn]) return false;
            if (isbn) seen[isbn] = true;
          }}
          return true;
        }});
      }}
      function applyFilter() {{
        dayFilter = "";
        updateDayBar();
        var globalMatches = matchingAllCards();
        if (!favMode && globalMatches.length) {{
          var month = cardMonth(globalMatches[0]);
          if (month && month !== monthKey()) switchMonth(month, true);
        }}
        currentPage = 1;
        renderList();
        saveMonthState();
        closeSuggest();
        if (globalMatches.length === 1) focusCard(globalMatches[0].id);
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
        var panelList = favMode
          ? Array.prototype.slice.call(document.querySelectorAll(".month-panel"))
          : [activePanel()].filter(Boolean);
        if (favMode) {{
          panelList.forEach(function (panel) {{ panel.hidden = false; }});
        }}
        panelList.forEach(function (panel) {{
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
        }});
        var total = favMode ? matched.length : panelTotal();
        var shownFrom = matched.length ? start + 1 : 0;
        var shownTo = start + visible.length;
        if (hit) {{
          if (favMode) {{
            if (!matched.length) hit.textContent = "お気に入り 0件";
            else if (matched.length <= PAGE_SIZE) hit.textContent = "お気に入り " + matched.length + "件";
            else hit.textContent = "お気に入り " + shownFrom + "〜" + shownTo + " / " + matched.length + "件";
          }} else if (!matched.length) hit.textContent = total + "件中 0件表示";
          else if (matched.length <= PAGE_SIZE) hit.textContent = total + "件中 " + matched.length + "件表示";
          else hit.textContent = matched.length + "件中 " + shownFrom + "〜" + shownTo + "件表示";
        }}
        if (empty) empty.hidden = matched.length !== 0;
        renderPager(pages, matched.length);
        syncSearchClear();
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
        var changed = page !== currentPage;
        currentPage = page;
        renderList();
        saveMonthState();
        saveListPos();
        if (changed) shuffleAds();
        scrollToPagerAndAds();
      }}
      function updateSuggest() {{
        if (!suggest) return;
        var q = fold(input.value);
        if (!q) {{
          closeSuggest();
          return;
        }}
        var matches = matchingAllCards().slice(0, MAX_SUGGEST);
        if (!matches.length) {{
          closeSuggest();
          return;
        }}
        if (!favMode) {{
          var firstMonth = cardMonth(matches[0]);
          if (firstMonth && firstMonth !== monthKey()) switchMonth(firstMonth, true);
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
            (card.getAttribute("data-date") || "") + " · " + (card.getAttribute("data-publisher") || "");
        }});
        suggest.hidden = false;
        placeSuggest();
      }}
      function focusCard(id) {{
        var card = document.getElementById(id);
        if (!card) return;
        var month = cardMonth(card);
        if (month && month !== monthKey()) switchMonth(month, true);
        var matched = matchingCards();
        var idx = matched.indexOf(card);
        if (idx < 0) idx = 0;
        currentPage = Math.floor(idx / PAGE_SIZE) + 1;
        renderList();
        closeSuggest();
        card.classList.remove("focus-flash");
        window.setTimeout(function () {{
          card.scrollIntoView({{ behavior: "smooth", block: "center" }});
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
          if (!id) return;
          if (favMode) setFavMode(false);
          if (id === monthKey()) return;
          switchMonth(id);
        }});
      }});
      function monthTabs() {{
        return Array.prototype.slice.call(document.querySelectorAll(".month-tab[data-month]"));
      }}
      function monthScrollEl() {{
        return document.getElementById("month-tabs-scroll");
      }}
      function updateMonthShift() {{
        var sc = monthScrollEl();
        var prev = document.getElementById("month-prev");
        var next = document.getElementById("month-next");
        if (!sc) return;
        if (prev) prev.disabled = sc.scrollLeft <= 2;
        if (next) next.disabled = sc.scrollLeft + sc.clientWidth >= sc.scrollWidth - 2;
      }}
      function syncMonthWindow() {{
        var sc = monthScrollEl();
        var tabs = monthTabs();
        if (!sc || !tabs.length) return;
        var active = null;
        tabs.forEach(function (tab) {{
          tab.hidden = false;
          if (tab.classList.contains("is-active")) active = tab;
        }});
        if (active) {{
          var left = active.offsetLeft - (sc.clientWidth - active.offsetWidth) / 2;
          sc.scrollLeft = Math.max(0, left);
        }}
        updateMonthShift();
      }}
      function shiftMonthWindow(delta) {{
        var sc = monthScrollEl();
        if (!sc) return;
        var tab = document.querySelector(".month-tab");
        var step = (tab ? tab.getBoundingClientRect().width : 100) + 8;
        sc.scrollBy({{ left: delta * step, behavior: "smooth" }});
      }}
      var monthPrev = document.getElementById("month-prev");
      var monthNext = document.getElementById("month-next");
      if (monthPrev) monthPrev.addEventListener("click", function () {{ shiftMonthWindow(-1); }});
      if (monthNext) monthNext.addEventListener("click", function () {{ shiftMonthWindow(1); }});
      var monthScroll = monthScrollEl();
      if (monthScroll) {{
        monthScroll.addEventListener("scroll", updateMonthShift, {{ passive: true }});
        monthScroll.addEventListener("wheel", function (ev) {{
          if (monthScroll.scrollWidth <= monthScroll.clientWidth) return;
          monthScroll.scrollLeft += ev.deltaX || ev.deltaY;
          ev.preventDefault();
          updateMonthShift();
        }}, {{ passive: false }});
      }}
      var PUB_TONES = [
        {{bg:"#fdecea", fg:"#b71c1c"}},
        {{bg:"#e8f1fb", fg:"#0d47a1"}},
        {{bg:"#f3e5f5", fg:"#6a1b9a"}},
        {{bg:"#e8f5e9", fg:"#1b5e20"}},
        {{bg:"#fff3e0", fg:"#e65100"}},
        {{bg:"#efebe9", fg:"#4e342e"}},
        {{bg:"#e0f2f1", fg:"#00695c"}},
        {{bg:"#e8eaf6", fg:"#283593"}},
        {{bg:"#fce4ec", fg:"#ad1457"}},
        {{bg:"#eceff1", fg:"#37474f"}},
        {{bg:"#fff8e1", fg:"#f57f17"}},
        {{bg:"#e0f7fa", fg:"#00838f"}},
        {{bg:"#f1f8e9", fg:"#33691e"}},
        {{bg:"#fbe9e7", fg:"#d84315"}},
        {{bg:"#ede7f6", fg:"#4527a0"}},
        {{bg:"#e3f2fd", fg:"#0277bd"}},
        {{bg:"#f9fbe7", fg:"#827717"}},
        {{bg:"#f3e5de", fg:"#6d4c41"}},
        {{bg:"#e8f5e8", fg:"#2e7d32"}},
        {{bg:"#fff0f0", fg:"#c62828"}}
      ];
      function updatePubBar() {{
        var bar = document.getElementById("pub-filter-bar");
        var lab = document.getElementById("pub-filter-label");
        var btn = document.getElementById("pub-btn");
        if (btn) btn.classList.toggle("is-on", !!publisherFilter);
        if (!bar) return;
        if (!publisherFilter) {{
          bar.hidden = true;
          return;
        }}
        bar.hidden = false;
        if (lab) lab.textContent = publisherFilter + "の作品";
      }}
      function setPublisherFilter(name) {{
        publisherFilter = name || "";
        if (publisherFilter && favMode) {{
          favMode = false;
          document.body.classList.remove("fav-mode");
          var favListBtn = document.getElementById("fav-list-btn");
          if (favListBtn) {{
            favListBtn.classList.remove("is-on");
            favListBtn.textContent = "お気に入り一覧";
          }}
        }}
        if (publisherFilter) {{
          var months = availableMonths();
          var latest = "";
          months.forEach(function (m) {{
            var panel = document.getElementById("month-" + m);
            if (!panel) return;
            var hit = panel.querySelector('.card[data-pub-group="' + publisherFilter.replace(/"/g, "") + '"]');
            if (hit) latest = m;
          }});
          if (latest && latest !== monthKey()) switchMonth(latest, true);
          else {{
            currentPage = 1;
            renderList();
          }}
        }} else {{
          currentPage = 1;
          renderList();
        }}
        updatePubBar();
        renderPubList();
        closePubModal();
      }}
      function renderPubList() {{
        var box = document.getElementById("pub-list");
        if (!box) return;
        box.innerHTML = PUBLISHERS.map(function (item, i) {{
          var on = item.name === publisherFilter ? " is-on" : "";
          var tone = PUB_TONES[i % PUB_TONES.length];
          return '<button type="button" class="pub-item' + on + '" data-pub="' +
            String(item.name).replace(/"/g, "") + '" style="background:' + tone.bg +
            ";color:" + tone.fg + '"><strong></strong></button>';
        }}).join("");
        Array.prototype.forEach.call(box.querySelectorAll(".pub-item"), function (btn, i) {{
          var item = PUBLISHERS[i];
          if (!item) return;
          btn.querySelector("strong").textContent = item.name + " " + item.count + "作品";
        }});
      }}
      function openPubModal() {{
        var modal = document.getElementById("pub-modal");
        if (!modal) return;
        renderPubList();
        modal.hidden = false;
      }}
      function closePubModal() {{
        var modal = document.getElementById("pub-modal");
        if (modal) modal.hidden = true;
      }}
      var topBtn = document.getElementById("back-to-top");
      if (topBtn) {{
        var onScroll = function () {{
          if (window.scrollY > 300) topBtn.classList.add("is-visible");
          else topBtn.classList.remove("is-visible");
        }};
        window.addEventListener("scroll", onScroll, {{ passive: true }});
        onScroll();
        topBtn.addEventListener("click", function () {{
          scrollToPagerAndAds();
        }});
      }}
      if (!input) {{
        paintFavs();
        renderList();
        syncMonthWindow();
        return;
      }}
      input.addEventListener("input", function () {{
        syncSearchClear();
        updateSuggest();
      }});
      window.addEventListener("resize", placeSuggest);
      window.addEventListener("scroll", placeSuggest, true);
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
          syncSearchClear();
          input.focus();
          applyFilter();
        }});
      }}
      function syncSearchClear() {{
        if (!clearBtn || !input) return;
        clearBtn.hidden = !input.value;
      }}
      function updateDayBar() {{
        var bar = document.getElementById("day-filter-bar");
        var lab = document.getElementById("day-filter-label");
        if (!bar) return;
        if (!dayFilter) {{
          bar.hidden = true;
          return;
        }}
        var parts = dayFilter.split("-");
        var n = allCards().filter(function (c) {{
          return (c.getAttribute("data-pubdate") || "") === dayFilter;
        }}).length;
        if (lab) {{
          lab.textContent = Number(parts[1]) + "月" + Number(parts[2]) + "日 発売 " + n + "冊";
        }}
        bar.hidden = false;
      }}
      function bookHref(card) {{
        var a = card.querySelector("a.title-link, a.cover-link");
        return a ? a.getAttribute("href") || "" : "";
      }}
      function cardsByDate() {{
        var map = {{}};
        allCards().forEach(function (card) {{
          var d = card.getAttribute("data-pubdate") || "";
          if (!d) return;
          if (!map[d]) map[d] = [];
          map[d].push(card);
        }});
        return map;
      }}
      function availableMonths() {{
        return Array.prototype.slice.call(document.querySelectorAll(".month-tab[data-month]")).map(function (tab) {{
          return tab.getAttribute("data-month") || "";
        }}).filter(Boolean);
      }}
      var calYear = 0;
      var calMonth = 0;
      function openCalendar() {{
        var modal = document.getElementById("cal-modal");
        if (!modal) return;
        var key = (dayFilter && dayFilter.slice(0, 7)) || monthKey();
        var parts = (key || "").split("-");
        calYear = parseInt(parts[0], 10) || new Date().getFullYear();
        calMonth = parseInt(parts[1], 10) || (new Date().getMonth() + 1);
        renderCalendar();
        if (dayFilter) renderCalDayList(dayFilter);
        else {{
          var list = document.getElementById("cal-day-list");
          if (list) {{ list.hidden = true; list.innerHTML = ""; }}
        }}
        modal.hidden = false;
      }}
      function closeCalendar() {{
        var modal = document.getElementById("cal-modal");
        if (modal) modal.hidden = true;
      }}
      function pad2(n) {{
        return (n < 10 ? "0" : "") + n;
      }}
      function shiftCalMonth(delta) {{
        calMonth += delta;
        if (calMonth < 1) {{ calMonth = 12; calYear -= 1; }}
        if (calMonth > 12) {{ calMonth = 1; calYear += 1; }}
        var months = availableMonths();
        var key = calYear + "-" + pad2(calMonth);
        if (months.length) {{
          if (delta > 0 && key > months[months.length - 1]) {{
            calYear = parseInt(months[months.length - 1].slice(0, 4), 10);
            calMonth = parseInt(months[months.length - 1].slice(5), 10);
          }}
          if (delta < 0 && key < months[0]) {{
            calYear = parseInt(months[0].slice(0, 4), 10);
            calMonth = parseInt(months[0].slice(5), 10);
          }}
        }}
        var list = document.getElementById("cal-day-list");
        if (list) {{ list.hidden = true; list.innerHTML = ""; }}
        renderCalendar();
      }}
      function renderCalendar() {{
        var title = document.getElementById("cal-title");
        var grid = document.getElementById("cal-grid");
        if (title) title.textContent = calYear + "年" + calMonth + "月";
        if (!grid) return;
        var map = cardsByDate();
        var first = new Date(calYear, calMonth - 1, 1);
        var start = (first.getDay() + 6) % 7;
        var days = new Date(calYear, calMonth, 0).getDate();
        var html = "";
        var i;
        var monthTotal = 0;
        for (i = 0; i < start; i++) html += '<button type="button" class="cal-cell is-empty" disabled></button>';
        for (var d = 1; d <= days; d++) {{
          var iso = calYear + "-" + pad2(calMonth) + "-" + pad2(d);
          var n = (map[iso] || []).length;
          monthTotal += n;
          var on = dayFilter === iso ? " is-on" : "";
          var zero = n ? "" : " is-zero";
          html += '<button type="button" class="cal-cell' + on + zero + '" data-date="' + iso + '"' +
            (n ? "" : " disabled") + '><span class="cal-num">' + d +
            '</span><span class="cal-count">' + n + "</span></button>";
        }}
        grid.innerHTML = html;
        var totalEl = document.getElementById("cal-month-total");
        if (totalEl) totalEl.textContent = monthTotal + "作品";
      }}
      function renderCalDayList(iso) {{
        var box = document.getElementById("cal-day-list");
        if (!box) return;
        var items = cardsByDate()[iso] || [];
        var parts = iso.split("-");
        var seen = {{}};
        var rows = [];
        items.forEach(function (card) {{
          var isbn = card.getAttribute("data-isbn") || card.id;
          if (seen[isbn]) return;
          seen[isbn] = true;
          rows.push({{
            href: bookHref(card),
            cover: card.getAttribute("data-cover") || "",
            title: card.getAttribute("data-title") || "",
            pub: card.getAttribute("data-publisher") || "",
            id: card.id
          }});
        }});
        box.hidden = false;
        box.innerHTML = "<h3>" + Number(parts[1]) + "月" + Number(parts[2]) + "日　" + rows.length + "冊</h3><ul></ul>";
        var ul = box.querySelector("ul");
        rows.forEach(function (row) {{
          var li = document.createElement("li");
          var node = document.createElement(row.href ? "a" : "div");
          node.className = "cal-day-item";
          if (row.href) node.href = row.href;
          var thumb = row.cover
            ? '<img src="' + row.cover.replace(/"/g, "") + '" alt="">'
            : '<div class="ph">書影</div>';
          node.innerHTML = thumb + "<div><strong></strong><span></span></div>";
          node.querySelector("strong").textContent = row.title;
          node.querySelector("span").textContent = row.pub;
          if (row.href) {{
            node.addEventListener("click", function () {{
              saveListPos({{ card: row.id }});
            }});
          }}
          li.appendChild(node);
          ul.appendChild(li);
        }});
      }}
      function selectCalDate(iso) {{
        if (!iso) return;
        dayFilter = iso;
        var ym = iso.slice(0, 7);
        if (ym && ym !== monthKey()) switchMonth(ym, true, true);
        else {{
          currentPage = 1;
          renderList();
        }}
        updateDayBar();
        renderCalendar();
        renderCalDayList(iso);
        saveListPos();
      }}
      var calBtn = document.getElementById("cal-btn");
      if (calBtn) calBtn.addEventListener("click", openCalendar);
      var pubBtn = document.getElementById("pub-btn");
      if (pubBtn) pubBtn.addEventListener("click", openPubModal);
      var pubClose = document.getElementById("pub-close");
      if (pubClose) pubClose.addEventListener("click", closePubModal);
      var pubClear = document.getElementById("pub-clear");
      if (pubClear) pubClear.addEventListener("click", function () {{ setPublisherFilter(""); }});
      var pubFilterClear = document.getElementById("pub-filter-clear");
      if (pubFilterClear) pubFilterClear.addEventListener("click", function () {{ setPublisherFilter(""); }});
      var pubList = document.getElementById("pub-list");
      if (pubList) pubList.addEventListener("click", function (ev) {{
        var item = ev.target.closest(".pub-item[data-pub]");
        if (!item) return;
        setPublisherFilter(item.getAttribute("data-pub") || "");
      }});
      var pubModal = document.getElementById("pub-modal");
      if (pubModal) pubModal.addEventListener("click", function (ev) {{
        if (ev.target === pubModal) closePubModal();
      }});
      var calClose = document.getElementById("cal-close");
      if (calClose) calClose.addEventListener("click", closeCalendar);
      var calPrev = document.getElementById("cal-prev");
      if (calPrev) calPrev.addEventListener("click", function () {{ shiftCalMonth(-1); }});
      var calNext = document.getElementById("cal-next");
      if (calNext) calNext.addEventListener("click", function () {{ shiftCalMonth(1); }});
      var calGrid = document.getElementById("cal-grid");
      if (calGrid) calGrid.addEventListener("click", function (ev) {{
        var cell = ev.target.closest(".cal-cell[data-date]");
        if (!cell || cell.disabled) return;
        selectCalDate(cell.getAttribute("data-date") || "");
      }});
      var calModal = document.getElementById("cal-modal");
      if (calModal) calModal.addEventListener("click", function (ev) {{
        if (ev.target === calModal) closeCalendar();
      }});
      function closeLegalModals() {{
        document.querySelectorAll(".legal-modal").forEach(function (el) {{
          el.hidden = true;
        }});
      }}
      document.querySelectorAll("[data-legal-open]").forEach(function (btn) {{
        btn.addEventListener("click", function () {{
          var id = btn.getAttribute("data-legal-open") || "";
          var modal = document.getElementById(id);
          if (!modal) return;
          closeCalendar();
          closePubModal();
          closeLegalModals();
          modal.hidden = false;
        }});
      }});
      document.querySelectorAll("[data-legal-close]").forEach(function (btn) {{
        btn.addEventListener("click", closeLegalModals);
      }});
      document.querySelectorAll(".legal-modal").forEach(function (modal) {{
        modal.addEventListener("click", function (ev) {{
          if (ev.target === modal) closeLegalModals();
        }});
      }});
      var dayClear = document.getElementById("day-filter-clear");
      if (dayClear) dayClear.addEventListener("click", function () {{
        dayFilter = "";
        updateDayBar();
        currentPage = 1;
        renderList();
        saveListPos();
      }});
      document.addEventListener("keydown", function (ev) {{
        if (ev.key === "Escape") {{
          closeCalendar();
          closePubModal();
          closeLegalModals();
        }}
      }});
      var favListBtn = document.getElementById("fav-list-btn");
      if (favListBtn) {{
        favListBtn.addEventListener("click", function () {{
          setFavMode(!favMode);
        }});
      }}
      document.addEventListener("click", function (ev) {{
        var bookLink = ev.target.closest("a.title-link, a.cover-link");
        if (bookLink) {{
          var card = ev.target.closest(".card");
          saveListPos({{ card: card ? card.id : "" }});
        }}
        var favBtn = ev.target.closest(".fav-btn");
        if (favBtn) {{
          ev.preventDefault();
          ev.stopPropagation();
          var isbn = favBtn.getAttribute("data-isbn") || "";
          if (!isbn) return;
          if (favs[isbn]) delete favs[isbn];
          else favs[isbn] = true;
          saveFavs();
          paintFavs();
          if (favMode) renderList();
          return;
        }}
        if (cluster && cluster.contains(ev.target)) return;
        closeSuggest();
      }});
      paintFavs();
      try {{
        var params = new URLSearchParams(location.search);
        if (params.get("fav") === "1") {{
          setFavMode(true);
        }} else if (!applyListPos(loadListPos())) {{
          renderList();
        }}
        var q = params.get("q");
        if (q && input) {{
          input.value = q;
          applyFilter();
        }}
        if (params.get("cal") === "1") openCalendar();
        var pubParam = params.get("pub");
        if (pubParam === "1") openPubModal();
        else if (pubParam) setPublisherFilter(pubParam);
        syncMonthWindow();
        syncSearchClear();
      }} catch (e) {{
        renderList();
      }}
    }})();
  </script>
</body>
</html>
"""
