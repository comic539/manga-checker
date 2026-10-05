"""今月発売のコミック第1巻と、主要書店の特典有無を一覧化する。"""

from __future__ import annotations

import argparse
import sys
import traceback
import warnings
from pathlib import Path

from urllib3.exceptions import InsecureRequestWarning

from manga_checker.bulk_listings import BulkListingIndex, ListingItem
from manga_checker.catalog import (
    catalog_display_months,
    fetch_months_volume_ones,
    load_catalog_json,
    merge_catalog_months,
    merge_privilege_listings_into_catalog,
    write_catalog_json,
)
from manga_checker.dates import (
    format_year_month,
    is_privilege_rematch_month,
    iter_month_offsets,
    iter_months,
    privilege_rematch_months,
    today_jst,
)
from manga_checker.http import configure_ssl, make_session
from manga_checker.models import ComicReport
from manga_checker.official import OfficialIndex
from manga_checker.publishers import publisher_sort_key
from manga_checker.rakuten_books import refresh_prices_from_rakuten
from manga_checker.privilege_index import load_melon_privileges
from manga_checker.report import SITE_TITLE, write_csv, write_html
from manga_checker.store_cache import load_checks_cache, save_checks_cache
from manga_checker.stores import check_stores


def parse_args() -> argparse.Namespace:
    today = today_jst()
    parser = argparse.ArgumentParser(
        description="今日を基準に前後3ヶ月を走査し、保存済みの過去月も残して書店特典の確認用一覧を作ります。"
    )
    parser.add_argument("--year", type=int, default=today.year, help="基準年（省略時は今年＝当月タブ）")
    parser.add_argument("--month", type=int, default=today.month, help="基準月 1-12（省略時は今月＝初期選択）")
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="指定時のみ、基準月から連続Nヶ月（省略時は前後3ヶ月走査＋保存済み過去月）",
    )
    parser.add_argument(
        "--fetch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="書店ページを取得して特典あり／なしを判定する（デフォルト: 有効。無効化は --no-fetch）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="各月の HTML/CSV に出力する件数。0（デフォルト）で全件。確認用に件数を絞るときだけ指定",
    )
    parser.add_argument(
        "--listings",
        default="",
        help="一括取得する書店ID（カンマ区切り）。空なら対象店すべて。例: toranoana",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="保存済みの書誌・特典キャッシュだけからHTMLを書き出す（書店取得をしない）",
    )
    parser.add_argument(
        "--reuse-catalog",
        action="store_true",
        help="output/catalog_by_month.json があれば書誌取得を省略し、特典判定だけやり直す",
    )
    parser.add_argument(
        "--refetch-past",
        action="store_true",
        help="保存済みの過去月も楽天から取り直す（通常は当月・未来月と未保存月だけ）",
    )
    parser.add_argument(
        "--csv-in",
        type=Path,
        default=None,
        help="追加タイトルのCSV（title,volume,author,publisher,pubdate,isbn）",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("output"), help="出力フォルダ")
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="確認用に件数を絞ったときなど、リポジトリ直下の index.html を上書きしない",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="SSL証明書の検証をスキップする（CERTIFICATE_VERIFY_FAILED 向け）",
    )
    parser.add_argument(
        "--fetch-preview",
        action="store_true",
        help="個別ページ用に公式試し読みURLを検索してキャッシュする",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=0,
        help="公式試し読み検索の最大件数（0で全件。確認時は小さく指定）",
    )
    return parser.parse_args()


def write_published_site(
    args: argparse.Namespace,
    comics_by_month: dict[tuple[int, int], list],
    windows: list[tuple[int, int]],
    active_period: tuple[int, int],
    *,
    fetch: bool,
    rematch_ok: bool,
    session=None,
    catalog: OfficialIndex | None = None,
    listings: BulkListingIndex | None = None,
    checks_cache: dict | None = None,
) -> None:
    checks_cache_path = args.out_dir / "store_checks.json"
    checks_cache = checks_cache if checks_cache is not None else load_checks_cache(checks_cache_path)
    if checks_cache and not fetch:
        print(f"判定キャッシュを読みました: {checks_cache_path.resolve()}")
    month_panels: list[tuple[int, int, list[ComicReport]]] = []
    all_reports: list[ComicReport] = []
    for year, month in windows:
        comics = list(comics_by_month.get((year, month), []))
        comics.sort(
            key=lambda c: publisher_sort_key(c.publisher, c.pubdate, c.display_title)
        )
        if args.limit and args.limit > 0:
            comics = comics[: args.limit]
        rematch = rematch_ok and is_privilege_rematch_month(year, month)
        print()
        print(f"===== {format_year_month(year, month)} ===== {len(comics)} 件")
        if rematch and fetch:
            print("特典を再照合します。")
        else:
            print("保存済みの特典判定でHTMLを書きます。")
        reports: list[ComicReport] = []
        for i, comic in enumerate(comics, start=1):
            if fetch:
                print(f"[{i}/{len(comics)}] {comic.display_title}", flush=True)
            try:
                checks = check_stores(
                    comic,
                    fetch=fetch and rematch,
                    delay_sec=1.5 if fetch and rematch else 0,
                    session=session,
                    catalog=catalog,
                    cache=checks_cache,
                    listings=listings if rematch else None,
                    rematch=rematch,
                )
            except Exception as exc:
                print(f"  特典判定に失敗しました: {exc}")
                traceback.print_exc()
                checks = []
            reports.append(
                ComicReport(
                    comic=comic,
                    checks=checks,
                    period_year=year,
                    period_month=month,
                )
            )
            if fetch:
                save_checks_cache(checks_cache_path, checks_cache)
        month_panels.append((year, month, reports))
        all_reports.extend(reports)
    save_checks_cache(checks_cache_path, checks_cache)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    heading = SITE_TITLE
    csv_path = args.out_dir / "volume1_privileges.csv"
    html_path = args.out_dir / "volume1_privileges.html"
    index_path = Path("index.html")
    write_csv(all_reports, csv_path)
    write_html(
        all_reports,
        html_path,
        heading,
        month_panels=month_panels,
        active_period=active_period,
        book_dir=Path("books"),
        sitemap_path=Path("sitemap.xml"),
        preview_cache_path=args.out_dir / "preview_urls.json",
        fetch_preview=bool(args.fetch_preview) and fetch,
        preview_limit=args.preview_limit,
    )
    if not args.no_index and html_path.resolve() != index_path.resolve():
        index_path.write_bytes(html_path.read_bytes())
    print()
    print("完了しました。")
    print(f"  CSV : {csv_path.resolve()}")
    print(f"  HTML: {html_path.resolve()}")
    print(f"  Pages: {index_path.resolve()}")
    print(f"  Books: {Path('books').resolve()}")
    print(f"  Sitemap: {Path('sitemap.xml').resolve()}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args()
    if not 1 <= args.month <= 12:
        raise SystemExit("month は 1〜12 で指定してください。")
    if args.months is not None and args.months < 1:
        raise SystemExit("months は 1 以上で指定してください。")

    configure_ssl(insecure=True if args.insecure else None)
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    if args.insecure:
        print("SSL検証を無効化しています（--insecure）。")

    if args.months is not None:
        windows = iter_months(args.year, args.month, args.months)
        active_period = windows[0]
    else:
        windows = iter_month_offsets(args.year, args.month, before=3, after=3)
        active_period = (args.year, args.month)
    live_windows = list(windows)

    if args.html_only:
        catalog_json = args.out_dir / "catalog_by_month.json"
        if not catalog_json.exists():
            raise SystemExit(f"書誌JSONがありません: {catalog_json}")
        print("保存済み書誌・特典からHTMLだけ書き出します（書店取得なし）。")
        comics_by_month = load_catalog_json(catalog_json, refresh_covers=False)
        write_catalog_json(catalog_json, comics_by_month)
        windows = catalog_display_months(live_windows, comics_by_month)
        write_published_site(
            args,
            comics_by_month,
            windows,
            active_period,
            fetch=False,
            rematch_ok=False,
        )
        return

    labels = "、".join(format_year_month(year, month) for year, month in live_windows)
    print(f"書誌を走査します… {labels}（各月は初日〜末日。保存済みの過去月は走査窓から外れても残します）")
    if args.fetch:
        print("各書店の特典ページを取得して判定します（時間がかかります。スキップは --no-fetch）。")
    else:
        print("書店ページの取得はスキップします。特典欄は公式一覧の照合分を除き未確認になります。")

    session = make_session()
    catalog = OfficialIndex()
    try:
        catalog.load(session)
    except Exception as exc:
        print(f"公式特典ページの取得に失敗しました: {exc}")
        traceback.print_exc()

    catalog_json = args.out_dir / "catalog_by_month.json"
    keep_saved_months = args.months is None
    load_months = None if keep_saved_months else live_windows
    saved_catalog = (
        load_catalog_json(catalog_json, load_months, refresh_covers=False)
        if catalog_json.exists()
        else {}
    )
    if args.reuse_catalog and saved_catalog:
        print(f"保存済み書誌を読みます: {catalog_json.resolve()}（楽天/NDLの再取得はしません）")
        comics_by_month = saved_catalog
        if keep_saved_months:
            windows = catalog_display_months(live_windows, comics_by_month)
        write_catalog_json(catalog_json, comics_by_month)
    else:
        if args.refetch_past:
            print("過去月も含めて書誌を取り直します（--refetch-past）。")
        else:
            print("書誌: 過去月は保存済みがあれば再利用し、当月・未来月だけ楽天を走査します。")
        fetched = fetch_months_volume_ones(
            live_windows,
            extra_csv=args.csv_in,
            session=session,
            saved=saved_catalog,
            today=today_jst(),
            refetch_past=args.refetch_past,
        )
        comics_by_month = (
            merge_catalog_months(saved_catalog, fetched)
            if keep_saved_months
            else fetched
        )
        if keep_saved_months:
            windows = catalog_display_months(live_windows, comics_by_month)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_catalog_json(catalog_json, comics_by_month)
    print(
        "掲載月: "
        + "、".join(format_year_month(year, month) for year, month in windows)
    )

    listings = BulkListingIndex()
    priv_months = privilege_rematch_months()
    only_listings = {part.strip() for part in (args.listings or "").split(",") if part.strip()}
    melon_wanted = (not only_listings) or ("melonbooks" in only_listings)
    if args.fetch and melon_wanted:
        try:
            melon_raw = load_melon_privileges(session, priv_months)
            for year, month in priv_months:
                comics_by_month[(year, month)] = [
                    comic
                    for comic in comics_by_month.get((year, month), [])
                    if comic.source != "melonbooks"
                ]
            added = merge_privilege_listings_into_catalog(comics_by_month, melon_raw)
            listings.items["melonbooks"] = [
                ListingItem(title=item.title, url=item.url, extra=item.extra, isbn=item.isbn)
                for item in melon_raw
            ]
            if not listings.items["melonbooks"]:
                listings.items.pop("melonbooks", None)
            print(f"メロン特典カレンダーの第1巻をカタログへ {added} 件補完しました。")
            windows = catalog_display_months(live_windows, comics_by_month)
        except Exception as exc:
            print(f"メロン特典カレンダーの取得に失敗しました: {exc}")
            traceback.print_exc()
    all_comics = [comic for comics in comics_by_month.values() for comic in comics]
    try:
        refresh_prices_from_rakuten(all_comics, session=session)
    except Exception as exc:
        print(f"楽天価格の補完に失敗しました: {exc}")
        traceback.print_exc()
    write_catalog_json(catalog_json, comics_by_month)
    try:
        listings.load(
            session,
            windows,
            privilege_months_window=priv_months,
            comics=all_comics,
            only=only_listings or None,
        )
    except Exception as exc:
        print(f"書店特典一覧の取得に失敗しました: {exc}")
        traceback.print_exc()
    checks_cache = load_checks_cache(args.out_dir / "store_checks.json")
    if checks_cache:
        print(f"判定キャッシュを読みました: {args.out_dir / 'store_checks.json'}（特典あり／なしのみ再利用。未確認は再取得します）")
    try:
        write_published_site(
            args,
            comics_by_month,
            windows,
            active_period,
            fetch=bool(args.fetch),
            rematch_ok=True,
            session=session,
            catalog=catalog,
            listings=listings,
            checks_cache=checks_cache,
        )
    except Exception as exc:
        print(f"サイト生成に失敗したため、保存済みデータからHTMLだけ書き出します: {exc}")
        traceback.print_exc()
        write_published_site(
            args,
            comics_by_month,
            windows,
            active_period,
            fetch=False,
            rematch_ok=False,
        )
    print("HTMLをブラウザで開くと、月タブと各書店の検索リンクから特典を確認できます。")


if __name__ == "__main__":
    main()
