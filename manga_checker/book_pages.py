"""作品ごとの静的詳細ページと sitemap.xml を出力する。"""

from __future__ import annotations

import html
import re
from pathlib import Path

from manga_checker.dates import format_release_date, today_jst
from manga_checker.links import amazon_url, mercari_url, rakuten_url
from manga_checker.models import ComicReport
from manga_checker.preview import (
    SearchFn,
    load_preview_cache,
    preview_cache_key,
    preview_links_for,
    resolve_preview_cache,
    save_preview_cache,
)
from manga_checker.privilege import STATUS_YES, privilege_display_text, privilege_summary
from manga_checker.report import (
    ASSET_VER,
    LOGO_ALT,
    SITE_BASE,
    SITE_NAME,
    _badge_html,
    _cover_html,
    _credit_html,
    _fav_button_html,
    _rakuten_cover_url,
    _site_legal_css,
    _site_legal_html,
    _site_legal_script,
)

_ISBN_CHARS = re.compile(r"[^0-9Xx]")
BOOK_PAGE_LEAD = "各店舗特典・試し読み・発売日情報まとめ【イッコミ特典＋】"


def isbn_slug(isbn: str) -> str:
    return _ISBN_CHARS.sub("", isbn or "")


def book_href(isbn: str) -> str:
    slug = isbn_slug(isbn)
    return f"books/{slug}.html" if slug else ""


def write_book_pages(
    reports: list[ComicReport],
    books_dir: Path,
    *,
    preview_cache_path: Path | None = None,
    fetch_preview: bool = False,
    preview_limit: int = 0,
    preview_delay_sec: float = 0.4,
    search_fn: SearchFn | None = None,
    prune_missing: bool = True,
) -> list[str]:
    books_dir.mkdir(parents=True, exist_ok=True)
    unique: dict[str, ComicReport] = {}
    for report in reports:
        slug = isbn_slug(report.comic.isbn)
        if slug and slug not in unique:
            unique[slug] = report
    cache: dict[str, dict[str, str]] = {}
    if preview_cache_path is not None:
        cache = load_preview_cache(preview_cache_path)
    comics = [report.comic for report in unique.values()]
    if fetch_preview:
        resolve_preview_cache(
            comics,
            cache,
            fetch=True,
            limit=preview_limit,
            delay_sec=preview_delay_sec,
            search_fn=search_fn,
            cache_path=preview_cache_path,
        )
    written = set()
    for slug, report in unique.items():
        links = preview_links_for(report.comic, cache.get(preview_cache_key(report.comic)))
        path = books_dir / f"{slug}.html"
        path.write_text(_book_document(report, preview=links), encoding="utf-8")
        written.add(path.name)
    for stale in books_dir.glob("*.html"):
        if prune_missing and stale.name not in written:
            stale.unlink()
    return sorted(written)


def write_sitemap(
    reports: list[ComicReport],
    path: Path,
    *,
    site_base: str = SITE_BASE,
) -> None:
    base = site_base.rstrip("/")
    slugs = []
    seen: set[str] = set()
    for report in reports:
        slug = isbn_slug(report.comic.isbn)
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    today = today_jst().isoformat()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{html.escape(base)}/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "  </url>",
    ]
    for slug in slugs:
        loc = f"{base}/books/{slug}.html"
        lines.extend(
            [
                "  <url>",
                f"    <loc>{html.escape(loc)}</loc>",
                f"    <lastmod>{today}</lastmod>",
                "    <changefreq>weekly</changefreq>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _trial_buttons_html(preview: dict[str, str] | None) -> str:
    preview = preview or {}
    buttons: list[str] = []
    official = preview.get("official_url") or ""
    if official:
        buttons.append(
            f'<a class="ext trial-official" href="{html.escape(official, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">公式で試し読み</a>'
        )
    else:
        fallback = preview.get("fallback_url") or ""
        label = preview.get("fallback_label") or "試し読みリンク不明"
        if fallback:
            buttons.append(
                f'<a class="ext trial-fallback" href="{html.escape(fallback, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{html.escape(label)}</a>'
            )
    cmoa = preview.get("cmoa_url") or ""
    if cmoa:
        buttons.append(
            f'<a class="ext trial-cmoa" href="{html.escape(cmoa, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">シーモアで試し読み</a>'
        )
    return "".join(buttons)


def _book_document(report: ComicReport, preview: dict[str, str] | None = None) -> str:
    comic = report.comic
    title = comic.display_title
    page_title = f"{title}\n{BOOK_PAGE_LEAD}"
    cover = _cover_html(comic)
    credit = _credit_html(comic)
    release = format_release_date(comic.pubdate) or "未登録"
    isbn = comic.isbn or "未登録"
    author = comic.author or "著者未登録"
    publisher = (comic.publisher or "").strip() or "出版社未登録"
    series = (comic.series or "").strip()
    if not series or series == publisher:
        series = "未登録"
    price = comic.price_line()
    amazon = amazon_url(comic.isbn, comic.search_query)
    rakuten = rakuten_url(comic.isbn, comic.search_query)
    mercari = mercari_url(comic.search_query)
    yes = sum(1 for c in report.checks if c.status == STATUS_YES)
    store_confirm = "".join(_store_confirm_row(check) for check in report.checks)
    trial_html = _trial_buttons_html(preview)
    ndl = ""
    if comic.ndl_url:
        ndl = (
            f'<p class="meta-line"><span>NDL</span>'
            f'<a href="{html.escape(comic.ndl_url)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(comic.ndl_url)}</a></p>'
        )
    slug = isbn_slug(comic.isbn)
    og_image = _rakuten_cover_url(comic) or f"{SITE_BASE}/logo.png"
    og_url = f"{SITE_BASE}/books/{slug}.html" if slug else f"{SITE_BASE}/"
    legal_html = _site_legal_html(logo_src="../logo.png")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(page_title)}</title>
  <meta property="og:site_name" content="{html.escape(SITE_NAME)}">
  <meta property="og:title" content="{html.escape(page_title)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{html.escape(og_url)}">
  <meta property="og:image" content="{html.escape(og_image)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{html.escape(page_title)}">
  <link rel="icon" type="image/png" href="../icon-3.png?v={ASSET_VER}">
  <style>
    :root {{
      --bg: #ffffff;
      --paper: #f2f2f2;
      --ink: #2a211c;
      --muted: #7a6f66;
      --accent: #c45c26;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      width: 100%;
      max-width: 100%;
      overflow-x: clip;
    }}
    body {{
      margin: 0;
      font-family: "Hiragino Sans", "Yu Gothic", Meiryo, sans-serif;
      background: #fff;
      color: var(--ink);
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
      flex-direction: row;
      align-items: center;
      gap: 16px;
      width: 100%;
      max-width: 1360px;
      margin: 0 auto;
      padding: 8px 20px;
      box-sizing: border-box;
    }}
    .site-top-row {{
      display: flex;
      flex: 1 1 auto;
      align-items: center;
      gap: 16px;
      min-width: 0;
    }}
    .smart-header {{
      display: flex;
      flex: 0 0 auto;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: nowrap;
      gap: 3px;
      height: 42px;
      margin-left: 0;
      padding: 3px;
      border: 1px solid #ece8e3;
      border-radius: 999px;
      background: #f5f4f2;
      box-sizing: border-box;
      overflow: hidden;
      transition: opacity 0.22s ease, transform 0.22s ease, max-height 0.22s ease, padding 0.22s ease, border-width 0.22s ease;
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
    .cal-btn,
    .pub-btn,
    .fav-list-btn {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 34px;
      padding: 0 14px;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: #1a1a1a;
      font: inherit;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      line-height: 1;
      text-decoration: none;
      cursor: pointer;
      white-space: nowrap;
      box-shadow: none;
    }}
    .cal-btn:hover,
    .pub-btn:hover,
    .fav-list-btn:hover,
    .cal-btn:active,
    .pub-btn:active,
    .fav-list-btn:active,
    .cal-btn.is-on,
    .pub-btn.is-on,
    .fav-list-btn.is-on {{
      background: var(--accent);
      color: #fff;
    }}
    .wrap {{
      max-width: 760px;
      margin: 0 auto;
      padding: 16px 16px 80px;
    }}
    .back {{
      display: inline-block;
      margin: 0 0 16px;
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    .back:hover {{ text-decoration: underline; }}
    h1 {{
      margin: 0 0 16px;
      font-size: 1.35rem;
      line-height: 1.4;
    }}
    .meta-line .copy-title {{
      display: inline;
      vertical-align: middle;
      margin-left: 6px;
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 700;
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 6px;
      white-space: nowrap;
    }}
    .meta-line .copy-title:hover {{
      background: #f3e6d6;
      color: var(--ink);
    }}
    .meta-line .copy-title.done {{
      color: #1f7a3a;
    }}
    .page-lead {{
      display: block;
      margin: 8px 0 0;
      font-size: 0.88rem;
      font-weight: 700;
      line-height: 1.45;
      color: var(--ink);
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1fr;
      grid-template-areas:
        "info"
        "ad";
      gap: 16px;
      align-items: start;
    }}
    .hero-info {{
      grid-area: info;
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr);
      grid-template-areas:
        "cover meta"
        "actions actions";
      gap: 16px;
      align-items: start;
      position: relative;
      width: 100%;
      max-width: 100%;
      margin-inline: auto;
      background: var(--paper);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(80, 50, 20, 0.08);
    }}
    .hero-ad {{
      grid-area: ad;
      margin: 0;
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      justify-content: center;
      gap: 16px;
      align-items: flex-start;
    }}
    .hero-cover {{ grid-area: cover; }}
    .hero-meta {{ grid-area: meta; min-width: 0; }}
    .hero-actions {{
      grid-area: actions;
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 16px 24px;
      padding-top: 0;
    }}
    .hero-actions .action-block {{
      flex: 1 1 160px;
      min-width: 148px;
    }}
    .hero-actions .buy {{
      flex-direction: column;
      align-items: stretch;
    }}
    .hero-actions .ext {{
      width: 100%;
    }}
    .buy-label {{
      margin: 0 0 8px;
      font-size: 0.78rem;
      font-weight: 800;
      color: var(--muted);
    }}
    .cover {{
      width: 140px;
      height: 198px;
      border-radius: 8px;
      overflow: hidden;
      background: #d9cfc3;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .cover img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .cover.ph {{ color: #8a7f75; font-size: 0.75rem; text-align: center; padding: 8px; }}
    .credit {{ margin: 6px 0 0; font-size: 0.58rem; color: #9a9088; }}
    .meta-line {{
      margin: 0 0 8px;
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .meta-line span {{
      display: inline-block;
      min-width: 5.5em;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .summary-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0 0;
    }}
    .chip {{
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 800;
      background: #f3e6d6;
    }}
    .chip.yes {{ background: #e5f6ea; color: #1f7a3a; }}
    .chip.no {{ background: #eceae6; color: #4b5563; }}
    .chip.todo {{ background: #fff3cc; color: #8a6400; }}
    h2 {{
      margin: 28px 0 12px;
      font-size: 1.05rem;
    }}
    .badges {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 8px;
    }}
    .badge {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 10px 6px;
      border-radius: 8px;
      text-decoration: none;
      text-align: center;
      box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    }}
    .badge .store {{ font-size: 0.72rem; font-weight: 800; }}
    .badge .status {{ font-size: 0.78rem; font-weight: 800; margin-top: 2px; }}
    @keyframes jelly-wobble {{
      0% {{ transform: scale(1, 1) rotate(0deg); }}
      18% {{ transform: scale(1.14, 0.84) rotate(-4deg); }}
      34% {{ transform: scale(0.9, 1.14) rotate(4deg); }}
      50% {{ transform: scale(1.1, 0.92) rotate(-2.4deg); }}
      66% {{ transform: scale(0.96, 1.08) rotate(1.6deg); }}
      82% {{ transform: scale(1.04, 0.97) rotate(-0.7deg); }}
      100% {{ transform: scale(1, 1) rotate(0deg); }}
    }}
    .badge.yes {{
      background: #16a34a;
      color: #fff;
      transform-origin: 50% 85%;
    }}
    .badge.yes:hover {{
      animation: jelly-wobble 0.7s cubic-bezier(0.22, 0.82, 0.32, 1);
      z-index: 2;
    }}
    @media (prefers-reduced-motion: reduce) {{
      .badge.yes:hover {{ animation: none; }}
    }}
    .badge.yes .store, .badge.yes .status {{ color: #fff; }}
    .badge.no {{ background: #eceae6; color: #3f3c39; }}
    .badge.todo {{ background: #fff3cc; color: #8a6400; }}
    .store-confirm {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .store-confirm-row {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 12px;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid #ececec;
    }}
    .store-confirm-row .badge {{
      min-width: 0;
      width: 100%;
      overflow: hidden;
    }}
    .badge .store,
    .badge .status {{
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .store-detail {{
      margin: 0;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.55;
    }}
    .ext {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-height: 44px;
      padding: 12px 16px;
      border-radius: 10px;
      font-size: 0.88rem;
      font-weight: 800;
      text-decoration: none;
      color: #fff;
    }}
    .buy .ext.amazon,
    .buy .ext.rakuten,
    .buy .ext.mercari {{
      min-height: 22px;
      padding: 4px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
    }}
    .ext .mark {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.2em;
      height: 1.2em;
      border-radius: 50%;
      font-size: 0.72rem;
      font-weight: 900;
      flex: 0 0 auto;
    }}
    .buy {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
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
    .ext.trial-official {{ background: #1f7a3a; color: #fff; }}
    .ext.trial-cmoa {{ background: #ff8a1a; color: #111; }}
    .ext.trial-fallback {{ background: #4b5563; color: #fff; }}
    .fav-btn {{
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 2;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 44px;
      height: 44px;
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
      cursor: pointer;
    }}
    .page-lead {{
      display: block;
      margin: 8px 0 0;
      font-size: 0.88rem;
      font-weight: 700;
      line-height: 1.45;
      color: var(--ink);
    }}
    .fav-heart {{
      width: 36px;
      height: 36px;
      fill: #fff;
      stroke: none;
      filter: drop-shadow(0 1px 2px rgba(0,0,0,0.12)) drop-shadow(0 3px 8px rgba(0,0,0,0.18));
    }}
    .fav-btn.is-on .fav-heart {{
      fill: #ff2eb8;
      filter: drop-shadow(0 1px 2px rgba(255,46,184,0.25));
    }}
    .ad-book {{
      position: relative;
      margin: 0;
      text-align: center;
    }}
    .ad-book a {{
      display: inline-block;
      max-width: 100%;
    }}
    .ad-book-rect a img {{
      display: block;
      width: 300px;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    .ad-book > img {{
      position: absolute;
      width: 1px;
      height: 1px;
      border: 0;
    }}
    {_site_legal_css()}
    @media (max-width: 768px) {{
      .site-top-inner {{
        flex-direction: column;
        align-items: stretch;
        padding: 8px 12px;
        gap: 0;
      }}
      .site-top-row {{
        flex-wrap: nowrap;
        gap: 8px;
        width: 100%;
      }}
      .smart-header {{
        width: 100%;
        justify-content: stretch;
        flex-wrap: nowrap;
        margin: 8px 0 0;
        height: 32px;
        max-height: 40px;
        padding: 2px;
        gap: 2px;
      }}
      .smart-header.is-away {{
        opacity: 0;
        transform: translateY(-10px);
        max-height: 0;
        height: 0;
        margin: 0;
        padding: 0;
        border-width: 0;
        pointer-events: none;
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
      .cal-btn,
      .pub-btn,
      .fav-list-btn {{
        flex: 1 1 0;
        height: 28px;
        font-size: 0.62rem;
        padding: 0 6px;
        letter-spacing: 0.02em;
      }}
    }}
    @media (max-width: 640px) {{
      .hero-ad {{
        flex-direction: column;
        align-items: center;
      }}
      .hero-info {{
        grid-template-columns: 1fr;
        grid-template-areas:
          "cover"
          "meta"
          "actions";
        width: 100%;
      }}
      .cover {{ width: 120px; height: 170px; }}
      .store-confirm-row {{
        grid-template-columns: 1fr;
        align-items: start;
      }}
      .hero-actions {{
        flex-direction: column;
        gap: 12px;
      }}
      .hero-actions .action-block {{
        flex: 1 1 auto;
        min-width: 0;
        width: 100%;
      }}
      .hero-actions .buy {{
        flex-direction: column;
        align-items: stretch;
        gap: 5px;
      }}
      .hero-actions .ext {{
        width: 100%;
        min-height: 32px;
        padding: 6px 12px;
        font-size: 0.78rem;
        box-sizing: border-box;
      }}
      .buy .ext.amazon,
      .buy .ext.rakuten,
      .buy .ext.mercari {{
        min-height: 22px;
        padding: 4px 10px;
        font-size: 0.72rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="site-top">
    <div class="site-top-inner">
      <div class="site-top-row">
        <a class="logo-link" href="../index.html?home=1">
          <img class="site-logo" src="../logo.png?v={ASSET_VER}" alt="{html.escape(LOGO_ALT, quote=True)}">
        </a>
      </div>
      <nav class="smart-header" id="smart-header" aria-label="主要メニュー">
        <a class="cal-btn" id="cal-btn" href="../index.html?cal=1">カレンダー</a>
        <a class="pub-btn" id="pub-btn" href="../index.html?pub=1">出版社一覧</a>
        <a class="fav-list-btn" id="fav-list-btn" href="../index.html?fav=1">お気に入り一覧</a>
      </nav>
    </div>
  </div>
  <div class="wrap">
    <h1>{html.escape(title)}<span class="page-lead">{html.escape(BOOK_PAGE_LEAD)}</span></h1>
    <a class="back" href="../index.html">← 一覧へ戻る</a>
    <section class="hero">
      <div class="hero-info">
      <div class="hero-cover">
        {cover}
        {credit}
      </div>
      <div class="hero-meta">
        <p class="meta-line"><span>作品名</span>{html.escape(title)}<button type="button" class="copy-title" data-title="{html.escape(title, quote=True)}">📋 コピー</button></p>
        <p class="meta-line"><span>出版社</span>{html.escape(publisher)}</p>
        <p class="meta-line"><span>レーベル</span>{html.escape(series)}</p>
        <p class="meta-line"><span>著者</span>{html.escape(author)}</p>
        <p class="meta-line"><span>ISBN</span>{html.escape(isbn)}</p>
        <p class="meta-line"><span>価格</span>{html.escape(price)}</p>
        <p class="meta-line"><span>発売日</span>{html.escape(release)}</p>
        {ndl}
        <div class="summary-chips">
          <span class="chip yes">特典あり {yes}</span>
        </div>
      </div>
      <div class="hero-actions">
        <div class="action-block">
          <p class="buy-label">試し読み</p>
          <div class="buy">{trial_html}</div>
        </div>
        <div class="action-block">
          <p class="buy-label">購入</p>
          <div class="buy">
            <a class="ext amazon" href="{html.escape(amazon)}" target="_blank" rel="noopener noreferrer"><span class="mark" aria-hidden="true">a</span>Amazon</a>
            <a class="ext rakuten" href="{html.escape(rakuten)}" target="_blank" rel="noopener noreferrer"><span class="mark" aria-hidden="true">R</span>楽天ブックス</a>
            <a class="ext mercari" href="{html.escape(mercari)}" target="_blank" rel="noopener noreferrer"><span class="mark" aria-hidden="true">m</span>mercari</a>
          </div>
        </div>
      </div>
      {_fav_button_html(slug)}
      </div>
      <aside class="hero-ad">
        <div class="ad-book ad-book-rect">
        <a href="https://px.a8.net/svt/ejp?a8mat=4BCDBN+FFHG6Q+4ADS+61JSH" rel="nofollow">
<img border="0" width="300" height="250" alt="" src="https://www27.a8.net/svt/bgt?aid=260917619933&wid=001&eno=01&mid=s00000020008001015000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=4BCDBN+FFHG6Q+4ADS+61JSH" alt="">
        </div>
        <div class="ad-book ad-book-rect">
<a href="https://px.a8.net/svt/ejp?a8mat=4BCL42+1U34XE+4Y6G+5ZMCH" rel="nofollow">
<img border="0" width="300" height="250" alt="" src="https://www26.a8.net/svt/bgt?aid=260927714111&wid=001&eno=01&mid=s00000023092001006000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www15.a8.net/0.gif?a8mat=4BCL42+1U34XE+4Y6G+5ZMCH" alt="">
        </div>
      </aside>
    </section>
    <h2>各書店の特典</h2>
    <div class="store-confirm">{store_confirm}</div>
  </div>
  {legal_html}
  <script>
    (function () {{
      var KEY = "ichikomi-favorites-v1";
      function loadMap() {{
        try {{
          var raw = JSON.parse(localStorage.getItem(KEY) || "[]");
          var map = {{}};
          (Array.isArray(raw) ? raw : []).forEach(function (id) {{
            if (id) map[String(id)] = true;
          }});
          return map;
        }} catch (e) {{
          return {{}};
        }}
      }}
      function saveMap(map) {{
        try {{
          localStorage.setItem(KEY, JSON.stringify(Object.keys(map)));
        }} catch (e) {{}}
      }}
      var favs = loadMap();
      document.querySelectorAll(".fav-btn").forEach(function (btn) {{
        var isbn = btn.getAttribute("data-isbn") || "";
        var on = !!(isbn && favs[isbn]);
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
        btn.addEventListener("click", function () {{
          if (!isbn) return;
          if (favs[isbn]) delete favs[isbn];
          else favs[isbn] = true;
          saveMap(favs);
          var now = !!favs[isbn];
          btn.classList.toggle("is-on", now);
          btn.setAttribute("aria-pressed", now ? "true" : "false");
        }});
      }});
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
      {_site_legal_script()}
      (function () {{
        var bar = document.getElementById("smart-header");
        if (!bar) return;
        var last = window.scrollY || 0;
        window.addEventListener("scroll", function () {{
          if (window.matchMedia("(min-width: 769px)").matches) {{
            bar.classList.remove("is-away");
            return;
          }}
          var y = window.scrollY || 0;
          if (y < 8) bar.classList.remove("is-away");
          else if (y > last + 6) bar.classList.add("is-away");
          else if (y < last - 6) bar.classList.remove("is-away");
          last = y;
        }}, {{ passive: true }});
      }})();
    }})();
  </script>
</body>
</html>
"""


def _store_privilege_text(check) -> str:
    return privilege_summary(check.status, check.detail)


def _store_confirm_row(check) -> str:
    detail = _store_privilege_text(check)
    detail_html = (
        f'<p class="store-detail">{html.escape(detail)}</p>' if detail else ""
    )
    return (
        '<div class="store-confirm-row">'
        f"{_badge_html(check, press=False, note=detail)}"
        f"{detail_html}"
        "</div>"
    )
