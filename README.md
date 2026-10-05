# イッコミ特典＋

今月（または指定した月）に発売されるコミックのうち、**第1巻**を集め、次の書店の特典状況へすぐ飛べる一覧を作ります。

アニメイト / メロンブックス / ゲーマーズ / とらのあな / COMIC ZIN / こみらの！ / 喜久屋書店

## できること

1. [国立国会図書館サーチ](https://ndlsearch.ndl.go.jp/help/api/specifications) から、その月の漫画（分類 NDC 726）を取得する
2. ISBN があれば [openBD](https://openbd.jp/) で書誌を補完する
3. タイトルや巻次に `1` `(1)` `第1巻` `Vol.1` があるものだけ残す（巻数のない単巻、短編集・上巻、下巻・後編は除外）
4. 書店検索では `第1巻` `(1)` `@COMIC` などを除いた作品名を使う
5. 書影付きカードに Amazon / 楽天ブックスの購入導線と書店特典バッジを出す

書店サイトには公式の横断APIがないため、**特典の最終確認は各店の商品ページで行う**前提です。`--fetch` を付けたときだけページを取得し、特典関連語が確認できた場合に限り **特典あり** とします。

## 用意するもの

- Python 3.10 以降（コマンドプロンプトまたは PowerShell で `python --version` が通ること）
  - `python` と打つと Microsoft Store が開くだけのときは、[python.org](https://www.python.org/downloads/) からインストールし、**Add python.exe to PATH** にチェックを入れてください
- インターネット接続

## インストール

PowerShell の場合、プロジェクトフォルダで次を実行します。

```powershell
cd C:\Users\shota\Desktop\manga-checker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`Activate.ps1` が禁止されているときは、次でも同じです。

```powershell
.\.venv\Scripts\activate
```

コマンドプロンプト（cmd）の場合:

```bat
cd C:\Users\shota\Desktop\manga-checker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 実行

仮想環境を有効にした状態で:

```powershell
python main.py
```

今月の第1巻を集め、`output\volume1_privileges.html`（発売日カレンダー風カード）と `output\volume1_privileges.csv` を作ります。HTMLをブラウザで開いてください。

### よく使うオプション

| コマンド | 意味 |
| --- | --- |
| `python main.py` | **今月の第1巻を全件**処理する（`--limit` なしがデフォルト） |
| `python main.py --year 2026 --month 9` | 2026年9月を対象にする |
| `python main.py --limit 5` | 動作確認用に最初の5件だけ処理する |
| `python main.py --fetch` | 書店ページを取得し、特典語が確認できた店だけ「特典あり」にする |
| `python main.py --csv-in samples\extra_titles.csv` | NDLに無い近刊をCSVで追加する |
| `python main.py --insecure` | SSL証明書エラー（CERTIFICATE_VERIFY_FAILED）を回避する |

`--fetch` はアニメイト等の検索結果（商品カード単位）を取得します。COMIC ZIN は入荷カレンダー、こみらの！は特典付きコミック一覧を一括取得して照合します。喜久屋は公式特典ページと常に照合します。

`CERTIFICATE_VERIFY_FAILED` が出る場合は、仮想環境を有効にしたうえで次を実行してください。

```powershell
pip install -r requirements.txt
python main.py --insecure
```

`--insecure` なしでも、certifi の証明書で失敗したときは自動的に検証なしで再試行します。環境変数 `MANGA_CHECKER_SSL_VERIFY=0` でも同じ回避ができます。

## 第1巻の判定ルール

次のいずれかに当てはまるものを第1巻とします。

- 巻次が `1` `１` `第1巻` `1巻`
- タイトルに `(1)` `（１）` `第1巻` `1巻` `Vol.1`

`10巻` や `11`、`1日10分で〜` のような「1」は対象外です。巻表示が無い新刊は自動では拾いません。その場合は `samples\extra_titles.csv` をコピーして追加してください。

## 出力の見方

HTMLは出版社順のカードです。左に書影、タイトル下に **Amazonで探す** と **楽天ブックスで探す**、その下に各書店の特典バッジがあります。

アフィリエイトIDは `affiliate.json.example` を `affiliate.json` にコピーするか、環境変数 `MANGA_CHECKER_AMAZON_TAG` / `MANGA_CHECKER_RAKUTEN_AFFILIATE_ID` で一括付与できます。

| 表示 | 意味 |
| --- | --- |
| 未確認 | まだページを取得していない（`--fetch` なし）、または検索ヒットなし |
| 特典あり | 特典 / 描き下ろしカード / 有償特典 / ペーパー / ブロマイドなどが確認できた |
| 通常/なし | 商品は見つかったが、特典を示す語はなかった |

## テスト

```powershell
python -m unittest discover -s tests -v
```

## 注意

- NDLの書誌は納本・登録ベースのため、発売直前の近刊がまだ無いことがあります。足りない分は CSV で足してください。
- 版元ドットコムの新刊RSSは、現時点では取得できないため使っていません。
- 特典情報の商用利用や、書店サイトへの過度なアクセスはしないでください。
