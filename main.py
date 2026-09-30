"""今月発売のコミック第1巻と、主要書店の特典有無を一覧化する。"""

from __future__ import annotations

import argparse
import warnings
from datetime import date
from pathlib import Path

from urllib3.exceptions import InsecureRequestWarning

from manga_checker.catalog import (
    catalog_display_months,
    fetch_months_volume_ones,
    load_catalog_json,
    merge_catalog_months,
    write_catalog_json,
)
from manga_checker.dates import format_year_month, iter_month_offsets, iter_months
from manga_checker.http import configure_ssl, make_session
from manga_checker.models import ComicReport
from manga_checker.official import OfficialIndex
from manga_checker.publishers import publisher_sort_key
from manga_checker.report import SITE_TITLE, write_csv, write_html
from manga_checker.store_cache import load_checks_cache, save_checks_cache
from manga_checker.stores import check_stores


def parse_args() -> argparse.Namespace:
    today = date.today()
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


def main() -> None:
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
    labels = "、".join(format_year_month(year, month) for year, month in live_windows)
    print(f"書誌を走査します… {labels}（各月は初日〜末日。保存済みの過去月は走査窓から外れても残します）")
    if args.fetch:
        print("各書店の特典ページを取得して判定します（時間がかかります。スキップは --no-fetch）。")
    else:
        print("書店ページの取得はスキップします。特典欄は公式一覧の照合分を除き未確認になります。")

    session = make_session()
    catalog = OfficialIndex()
    catalog.load(session)

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
            today=date.today(),
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

    checks_cache_path = args.out_dir / "store_checks.json"
    checks_cache = load_checks_cache(checks_cache_path)
    if checks_cache:
        print(f"判定キャッシュを読みました: {checks_cache_path.resolve()}（特典あり／なしのみ再利用。未確認は再取得します）")

    month_panels: list[tuple[int, int, list[ComicReport]]] = []
    all_reports: list[ComicReport] = []
    for year, month in windows:
        print()
        print(f"===== {format_year_month(year, month)} =====")
        comics = list(comics_by_month.get((year, month), []))
        comics.sort(
            key=lambda c: publisher_sort_key(c.publisher, c.pubdate, c.display_title)
        )
        if args.limit and args.limit > 0:
            comics = comics[: args.limit]
            print(
                f"--limit {args.limit} により {format_year_month(year, month)}の出力を "
                f"{len(comics)} 件に絞りました。"
            )
        else:
            print(f"{format_year_month(year, month)}の第1巻を全件処理します: {len(comics)} 件")

        reports: list[ComicReport] = []
        for i, comic in enumerate(comics, start=1):
            print(f"[{i}/{len(comics)}] {comic.display_title}")
            reports.append(
                ComicReport(
                    comic=comic,
                    checks=check_stores(
                        comic,
                        fetch=args.fetch,
                        delay_sec=1.5 if args.fetch else 0,
                        session=session,
                        catalog=catalog,
                        cache=checks_cache,
                    ),
                    period_year=year,
                    period_month=month,
                )
            )
            if args.fetch:
                save_checks_cache(checks_cache_path, checks_cache)
        month_panels.append((year, month, reports))
        all_reports.extend(reports)

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
        fetch_preview=args.fetch_preview,
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
    print("HTMLをブラウザで開くと、月タブと各書店の検索リンクから特典を確認できます。")


if __name__ == "__main__":
    main()
