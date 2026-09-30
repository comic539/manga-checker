"""公式試し読みURLの検索・キャッシュと、フォールバック／シーモアリンク。"""

from __future__ import annotations

import base64
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from manga_checker.dates import parse_release_date, year_month_from_pubdate
from manga_checker.links import isbn13
from manga_checker.models import Comic
from manga_checker.publishers import canonical_publisher
from manga_checker.search_title import bare_search_title

SearchFn = Callable[[str], list[str]]

OFFICIAL_HOSTS = (
    "shonenjumpplus.com",
    "plus.shonenjump.com",
    "pocket.shonenmagazine.com",
    "magazine-pocket.com",
    "sunday.webry.com",
    "www.sunday.webry.com",
    "sunday-webry.com",
    "www.sunday-webry.com",
    "comic-walker.com",
    "comic-walker.jp",
    "www.comic-walker.com",
    "shonen-sirius.com",
    "www.shonen-sirius.com",
    "championcross.jp",
    "comic-action.com",
    "younganimal.com",
    "younganimal-idas.com",
    "tonarinoyj.jp",
    "comic-days.com",
    "mangatime-square.com",
    "comic-zenon.com",
    "magcomi.com",
    "comic-gardo.com",
    "comic-ogyaaa.com",
    "comic-trail.com",
    "comic-growl.com",
    "comic-valkyrie.com",
    "web-ace.jp",
    "comic-fuz.com",
    "www.alphapolis.co.jp",
    "alphapolis.co.jp",
    "ganma.jp",
    "ganganonline.com",
    "manga.square-enix.com",
    "www.jp.square-enix.com",
    "comicbunch.com",
    "kuragebunch.com",
    "comic-earthstar.com",
    "comic-meteor.jp",
    "viewer.heros-web.com",
    "www.heros-web.com",
    "yawaspi.com",
    "comic-zenyon.jp",
    "ultrasj.jp",
    "youngjump.jp",
    "grandjump.shueisha.co.jp",
    "jumpsq.shueisha.co.jp",
    "shonenjump.com",
    "shonenjump.com",
    "palcy.jp",
    "comic-polaris.jp",
    "www.comic-valkyrie.com",
    "comic-boost.com",
    "sokuyomi.jp",
    "www.comic-days.com",
    "comic-seiga.com",
    "manga.nicovideo.jp",
    "comic.pixiv.net",
    "ciao.shogakukan.co.jp",
    "comics.shogakukan.co.jp",
    "manga-one.com",
    "corocoro.jp",
    "www.corocoro.jp",
    "cheese.jp",
    "www.cheese.jp",
    "yanmaga.jp",
    "s-manga.net",
    "www.s-manga.net",
    "shueisha.co.jp",
    "www.shueisha.co.jp",
    "sho-comi.com",
    "www.sho-comi.com",
    "pocg.net",
    "feelweb.jp",
    "comic-days.com",
    "www.yanmaga.jp",
    "comic-zenon.jp",
    "www.comic-zenon.com",
    "comicbunch.com",
    "viewer.heros-web.com",
    "cycomi.com",
    "www.cycomi.com",
    "manga-oa.com",
    "www.manga-oa.com",
    "comic-gardo.com",
    "www.comic-gardo.com",
    "to-r.jp",
    "ribon.shueisha.co.jp",
    "cookie.shueisha.co.jp",
    "you.shueisha.co.jp",
    "ultra.shueisha.co.jp",
    "jumpsq.shueisha.co.jp",
    "grandjump.shueisha.co.jp",
    "youngjump.jp",
    "www.youngjump.jp",
    "tonarinoyj.jp",
    "www.tonarinoyj.jp",
    "manga-park.com",
    "www.manga-park.com",
    "takecomic.jp",
    "www.takecomic.jp",
    "mangadx-plus.com",
    "www.mangadx-plus.com",
    "zerosumonline.com",
    "www.zerosumonline.com",
    "comic-ryu.jp",
    "www.comic-ryu.jp",
    "comic-fire.com",
    "www.comic-fire.com",
    "comic-fire.jp",
    "comic-ride.jp",
    "www.comic-ride.jp",
    "comicride.jp",
    "licomi.jp",
    "www.licomi.jp",
    "lovecoffre.com",
    "www.lovecoffre.com",
    "mangacross.jp",
    "www.mangacross.jp",
    "heros-web.com",
)

_SKIP_PATH_PARTS = (
    "/search",
    "/login",
    "/signin",
    "/signup",
    "/account",
    "/cart",
    "/ranking",
    "/store",
    "/info",
    "/article",
    "/columns",
    "/news",
    "/feature",
    "/support",
)
_GENERIC_PATHS = {
    "",
    "/",
    "/volume/trial",
    "/trial",
    "/reader",
    "/reader/main.php",
    "/books/reader/main.php",
    "/series",
    "/manga",
    "/book",
    "/titles",
    "/titles/rensai",
}

FALLBACK_LABEL = "試し読みを検索"
_PUBLISHER_LINKS = {
    "講談社": "https://kc.kodansha.co.jp/search?q={q}",
    "集英社": "https://www.s-manga.net/search/search.html?searchword={q}",
    "小学館": "https://www.shogakukan.co.jp/search/site/{q}",
    "KADOKAWA": "https://www.kadokawa.co.jp/product/search/?keyword={q}",
    "秋田書店": "https://www.akitashoten.co.jp/?s={q}",
    "芳文社": "https://houbunsha.co.jp/?s={q}",
    "スクウェア・エニックス": "https://www.jp.square-enix.com/magazine/top/search/?word={q}",
    "白泉社": "https://www.hakusensha.co.jp/?s={q}",
    "竹書房": "https://www.takeshobo.co.jp/?s={q}",
    "双葉社": "https://www.futabasha.co.jp/search?q={q}",
    "一迅社": "https://www.ichijinsha.co.jp/?s={q}",
    "アルファポリス": "https://www.alphapolis.co.jp/search?query={q}",
    "少年画報社": "https://www.shonengahosha.co.jp/?s={q}",
    "マッグガーデン": "https://magcomi.com/search?q={q}",
    "徳間書店": "https://www.tokuma.jp/",
    "コアミックス": "https://www.coamix.jp/",
    "TOブックス": "https://www.tobooks.jp/",
    "オーバーラップ": "https://over-lap.co.jp/",
    "フロンティアワークス": "https://www.fwinc.co.jp/",
    "ホビージャパン": "https://hobbyjapan.co.jp/",
    "ブシロードワークス": "https://bushiroad.com/",
    "マイクロマガジン社": "https://micromagazine.net/",
    "イマジカインフォス": "https://www.imagica.com/",
    "一二三書房": "https://www.hitotose.co.jp/",
    "スターツ出版": "https://www.starts-pub.jp/",
    "新潮社": "https://www.shinchosha.co.jp/",
    "日本文芸社": "https://www.nihonbungeisha.co.jp/",
    "フレックスコミックス": "https://flex-comi.jp/",
    "Cygames": "https://www.cycomi.com/",
    "ぶんか社": "https://www.bunkasha.co.jp/",
    "幻冬舎コミックス": "https://www.gentosha-comics.net/",
    "アース・スター": "https://www.earthstar.jp/",
    "リイド社": "https://www.leed.co.jp/",
    "ヒーローズ": "https://heros-web.com/",
    "主婦と生活社": "https://www.shufu.co.jp/",
    "ハーパーコリンズ": "https://www.harpercollins.co.jp/",
    "ナンバーナイン": "https://number-nine.co.jp/",
    "SBクリエイティブ": "https://www.sbcr.jp/",
    "祥伝社": "https://www.shodensha.co.jp/",
    "秋水社": "https://www.akisuisha.co.jp/",
    "ジーオーティー": "https://www.got-online.co.jp/",
    "文藝春秋": "https://www.bunshun.co.jp/",
    "ホーム社": "https://www.homesha.jp/",
    "海王社": "https://www.kaiousha.co.jp/",
    "大都社": "https://www.daitosha.co.jp/",
    "宝島社": "https://tkj.jp/",
    "光文社": "https://www.kobunsha.com/",
    "新書館": "https://www.shinshokan.co.jp/",
    "星海社": "https://www.seikaisha.co.jp/",
    "早川書房": "https://www.hayakawa-online.co.jp/",
    "マガジンハウス": "https://magazineworld.jp/",
}


def preview_cache_key(comic: Comic) -> str:
    digits = isbn13(comic.isbn)
    return digits or (comic.display_title or comic.title or "").strip()


def _full_preview_name(comic: Comic) -> str:
    """試し読み検索用の作品名。長いタイトルは切らない。"""
    name = bare_search_title(comic.title, comic.volume)
    name = re.sub(r"[〜～:：/／]", " ", name)
    name = re.sub(r"[\s　]+", " ", name).strip()
    return name


def _preview_name(comic: Comic) -> str:
    """site:検索向け。長いタイトルは20〜30文字程度に切る。"""
    name = _full_preview_name(comic)
    if len(name) > 30:
        cut = name[:30]
        space = cut.rfind(" ")
        if space >= 20:
            cut = cut[:space]
        name = cut.rstrip()
    return name


def _short_search_name(name: str) -> str:
    """site:検索向けの短い先頭語。長文クエリだとBingが公式サイトを落とす。"""
    first = re.split(r"\s+", (name or "").strip(), maxsplit=1)[0]
    first = first.rstrip("!！?？。．")
    if 4 <= len(first) < len(name or ""):
        return first
    return ""


def search_query(comic: Comic) -> str:
    return f"{_full_preview_name(comic)} 1話"


def search_queries(comic: Comic, *, include_sites: bool = True) -> list[str]:
    full = _full_preview_name(comic)
    short = _preview_name(comic)
    base_full = f"{full} 1話"
    queries: list[str] = [base_full, f'"{full}" 1話']
    if short != full:
        queries.append(f"{short} 1話")
    queries.append(f"{base_full} 試し読み")
    if include_sites:
        for site in preview_hosts_for(comic)[:6]:
            queries.append(f"{base_full} site:{site}")
            if short != full:
                queries.append(f"{short} 1話 site:{site}")
    return queries


_ISBN_PUBLISHER_PREFIX = {
    "406": "講談社",
    "408": "集英社",
    "409": "小学館",
    "404": "KADOKAWA",
    "425": "秋田書店",
    "483": "芳文社",
    "430": "スクウェア・エニックス",
}

_CROSS_PREVIEW_SITES = (
    "comic-days.com",
    "pocket.shonenmagazine.com",
    "shonenjumpplus.com",
    "comic-walker.com",
    "shonen-sirius.com",
    "manga-one.com",
    "sunday-webry.com",
    "sunday.webry.com",
    "ciao.shogakukan.co.jp",
    "corocoro.jp",
    "comic-fuz.com",
    "championcross.jp",
    "ganganonline.com",
    "magcomi.com",
    "alphapolis.co.jp",
    "kuragebunch.com",
    "comic-action.com",
    "manga-park.com",
    "takecomic.jp",
    "comic-gardo.com",
    "comic-zenon.com",
    "comic-growl.com",
    "comic-boost.com",
)


def isbn_publisher_guess(isbn: str) -> str:
    digits = isbn13(isbn)
    if len(digits) < 6 or not digits.startswith("978"):
        return ""
    return _ISBN_PUBLISHER_PREFIX.get(digits[3:6], "")


def publisher_preview_hosts(publisher: str) -> tuple[str, ...]:
    return _PUBLISHER_SITES.get(canonical_publisher(publisher), ())


def preview_hosts_for(comic: Comic) -> tuple[str, ...]:
    """表示出版社に加え、ISBNから推測したレーベルの配信サイトも見る。"""
    seen: list[str] = []
    for key in (canonical_publisher(comic.publisher), isbn_publisher_guess(comic.isbn)):
        for host in _PUBLISHER_SITES.get(key, ()):
            if host not in seen:
                seen.append(host)
    return tuple(seen)


_PUBLISHER_SITES = {
    "集英社": (
        "shonenjumpplus.com",
        "tonarinoyj.jp",
        "youngjump.jp",
        "plus.shonenjump.com",
        "s-manga.net",
        "jumpsq.shueisha.co.jp",
        "grandjump.shueisha.co.jp",
        "ultrasj.jp",
    ),
    "小学館": (
        "manga-one.com",
        "sunday-webry.com",
        "sunday.webry.com",
        "ciao.shogakukan.co.jp",
        "cheese.jp",
        "corocoro.jp",
        "sho-comi.com",
        "pocg.net",
    ),
    "講談社": (
        "comic-days.com",
        "pocket.shonenmagazine.com",
        "magazine-pocket.com",
        "yanmaga.jp",
        "palcy.jp",
    ),
    "KADOKAWA": (
        "comic-walker.com",
        "comic-walker.jp",
        "shonen-sirius.com",
        "web-ace.jp",
    ),
    "スクウェア・エニックス": ("manga.square-enix.com", "ganganonline.com"),
    # マンガクロスは2024-04-23にチャンピオンクロスへ統合。現行の公式ウェブはここだけ。
    "秋田書店": ("championcross.jp",),
    "芳文社": ("comic-fuz.com",),
    "白泉社": (
        "manga-park.com",
        "younganimal.com",
        "younganimal-idas.com",
        "feelweb.jp",
    ),
    "竹書房": ("takecomic.jp",),
    "双葉社": ("comic-action.com",),
    "少年画報社": ("mangadx-plus.com",),
    "徳間書店": ("comic-ryu.jp",),
    "一迅社": ("zerosumonline.com",),
    "マッグガーデン": ("magcomi.com",),
    "コアミックス": ("comic-zenon.com", "comic-zenon.jp"),
    "TOブックス": ("comic-gardo.com",),
    "アルファポリス": ("alphapolis.co.jp",),
    "オーバーラップ": ("comic-gardo.com",),
    "フロンティアワークス": ("comic-growl.com",),
    "ホビージャパン": ("comic-fire.com", "comic-fire.jp"),
    "ブシロードワークス": ("comic-boost.com",),
    "マイクロマガジン社": ("comic-ride.jp", "licomi.jp"),
    "イマジカインフォス": ("lovecoffre.com",),
    "ヒーローズ": ("viewer.heros-web.com", "heros-web.com"),
    "Cygames": ("cycomi.com",),
    "新潮社": ("kuragebunch.com", "comicbunch.com"),
    "アース・スター": ("comic-earthstar.com",),
    "フレックスコミックス": ("comic-meteor.jp",),
}


def cmoa_search_url(comic: Comic) -> str:
    # keyword= は無視されて全件一覧になる。現行の検索パラメータは word=
    name = bare_search_title(comic.title, comic.volume)
    return "https://www.cmoa.jp/search/result/?word=" + quote(name, safe="")


def is_released(pubdate: str, today: date | None = None) -> bool:
    """発売日が今日以前なら発売済み（シーモアボタン用）。"""
    today = today or date.today()
    parsed = parse_release_date(pubdate)
    if parsed:
        return parsed <= today
    ym = year_month_from_pubdate(pubdate)
    if ym is None:
        return False
    return (ym[0], ym[1]) <= (today.year, today.month)


def fallback_catalog_url(comic: Comic) -> tuple[str, str]:
    """公式試し読みが無いときの検索リンク。出版社トップはヒットしないことが多い。"""
    name = bare_search_title(comic.title, comic.volume)
    q = quote(f"{name} 1話")
    return f"https://www.google.com/search?q={q}", FALLBACK_LABEL


def _host_of(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _unwrap_ddg(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unquote(uddg[0])
    return url


def _unwrap_bing(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "bing.com" not in host:
        return url
    raw = (parse_qs(parsed.query).get("u") or [""])[0]
    if not raw:
        return url
    if raw.startswith("a1"):
        payload = raw[2:]
        pad = "=" * ((4 - len(payload) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload + pad).decode("utf-8", "ignore")
        except Exception:
            return url
        if decoded.startswith("http"):
            return decoded
    if raw.startswith("http"):
        return unquote(raw)
    return url


def _unwrap_google(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    if path.startswith("/url") and not host:
        parsed = urlparse("https://www.google.com" + url)
        host = parsed.netloc.lower()
        path = parsed.path
    if "google." not in host:
        return url
    if path.startswith("/url"):
        target = (parse_qs(parsed.query).get("q") or [""])[0]
        if target.startswith("http"):
            return target
    return url


def _search_result_url(href: str) -> str:
    raw = (href or "").strip()
    if raw.startswith("/url") or raw.startswith("/imgres"):
        raw = "https://www.google.com" + raw
    return _unwrap_search_url(raw)


def _unwrap_search_url(url: str) -> str:
    raw = (url or "").strip()
    raw = _unwrap_ddg(raw)
    raw = _unwrap_bing(raw)
    raw = _unwrap_google(raw)
    return raw


_STRICT_HOST_PATHS = {
    "shueisha.co.jp": ("/reader", "/trial", "/episode"),
    "s-manga.net": ("/reader",),
}


def _host_matches(host: str, allowed: tuple[str, ...] | list[str]) -> bool:
    return any(host == h or host.endswith("." + h) for h in allowed)


def is_official_preview_url(url: str, allowed_hosts: tuple[str, ...] | list[str] | None = None) -> bool:
    raw = _unwrap_search_url((url or "").strip())
    if not raw.startswith("http"):
        return False
    parsed = urlparse(raw)
    host = _host_of(raw)
    if not host:
        return False
    hosts = tuple(allowed_hosts) if allowed_hosts else OFFICIAL_HOSTS
    if not _host_matches(host, hosts):
        return False
    path = (parsed.path or "").lower()
    if any(part in path for part in _SKIP_PATH_PARTS):
        return False
    for suffix, needles in _STRICT_HOST_PATHS.items():
        if host == suffix or host.endswith("." + suffix):
            if not any(n in path for n in needles):
                return False
            break
    if path.rstrip("/") in _GENERIC_PATHS or path in _GENERIC_PATHS:
        if not (parsed.query or "").strip():
            return False
    if host in ("shogakukan-comic.jp",) or host.endswith(".shogakukan-comic.jp"):
        return False
    return True


def pick_official_url(
    urls: list[str],
    allowed_hosts: tuple[str, ...] | list[str] | None = None,
) -> str:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in urls:
        url = _search_result_url((raw or "").strip())
        if not is_official_preview_url(url, allowed_hosts=allowed_hosts):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        path = urlparse(url).path.lower()
        score = 0
        if "/episode" in path or "/chapter" in path:
            score += 6
        if "/viewer" in path:
            score += 5
        if "/detail/" in path:
            score += 4
        if "/trial" in path or "/reader" in path:
            score += 2
        if "/volume/" in path:
            score += 1
        if "/title" in path or "/comics/" in path or "/comic" in path or "/series" in path:
            score += 2
        if "/book" in path or "/manga" in path:
            score += 2
        ranked.append((score, url))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _ddg_library_search(query: str, max_results: int = 10) -> list[str]:
    DDGS = None
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            return []
    urls: list[str] = []
    try:
        with DDGS() as ddgs:
            rows = ddgs.text(query, region="jp-jp", max_results=max_results) or []
            for row in rows:
                href = (row.get("href") or row.get("url") or "").strip()
                if href:
                    urls.append(href)
    except Exception:
        return []
    return urls


def _ddg_html_search(query: str, max_results: int = 10) -> list[str]:
    from bs4 import BeautifulSoup

    from manga_checker.http import make_session

    session = make_session()
    try:
        response = session.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            timeout=20,
        )
    except Exception:
        return []
    if response.status_code >= 400:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    for a in soup.select("a.result__a, a.result-link"):
        href = (a.get("href") or "").strip()
        if href:
            urls.append(_unwrap_ddg(href))
        if len(urls) >= max_results:
            break
    return urls


def _google_html_search(query: str, max_results: int = 10) -> list[str]:
    from bs4 import BeautifulSoup

    from manga_checker.http import make_session

    session = make_session()
    try:
        response = session.get(
            "https://www.google.com/search",
            params={
                "q": query,
                "hl": "ja",
                "lr": "lang_ja",
                "num": str(max_results),
                "gbv": "1",
                "pws": "0",
            },
            headers={"Accept-Language": "ja,en;q=0.8"},
            timeout=20,
        )
    except Exception:
        return []
    if response.status_code >= 400:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = _search_result_url((a.get("href") or "").strip())
        if not href.startswith("http"):
            continue
        if "google." in _host_of(href):
            continue
        key = href.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        urls.append(href)
        if len(urls) >= max_results:
            break
    return urls


def _bing_html_search(query: str, max_results: int = 10) -> list[str]:
    from bs4 import BeautifulSoup

    from manga_checker.http import make_session

    session = make_session()
    try:
        response = session.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "ja-jp", "cc": "JP", "mkt": "ja-JP"},
            timeout=20,
        )
    except Exception:
        return []
    if response.status_code >= 400:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for a in soup.select("li.b_algo h2 a, h2 a"):
        href = _unwrap_search_url((a.get("href") or "").strip())
        if not href.startswith("http"):
            continue
        key = href.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        urls.append(href)
        if len(urls) >= max_results:
            break
    return urls


_NOISE_HOST_PARTS = (
    "crowdworks.jp",
    "translate.google",
    "yahoo.co.jp",
    "yahoo.com",
    "login.live.com",
)


def _filter_noise_urls(urls: list[str]) -> list[str]:
    cleaned: list[str] = []
    for url in urls:
        low = (url or "").lower()
        host = _host_of(url)
        if any(part in low or part in host for part in _NOISE_HOST_PARTS):
            continue
        cleaned.append(url)
    return cleaned


def _urls_have_official(urls: list[str]) -> bool:
    return any(is_official_preview_url(u) for u in urls)


def _first_official_search_hits(batches: list[list[str]]) -> list[str]:
    leftover: list[str] = []
    for raw in batches:
        urls = _filter_noise_urls(list(raw or []))
        if not urls:
            continue
        if _urls_have_official(urls):
            return urls
        if not leftover:
            leftover = urls
    return leftover


def default_web_search(query: str) -> list[str]:
    batches: list[list[str]] = []
    for fn in (_google_html_search, _bing_html_search, _ddg_html_search, _ddg_library_search):
        try:
            urls = fn(query) or []
        except Exception:
            urls = []
        batches.append(urls)
    return _first_official_search_hits(batches)


def _compact_text(text: str) -> str:
    return re.sub(r"[\s　、。・!！?？『』「」【】（）()\-〜～]+", "", text or "").lower()


def pick_giga_first_episode(html: str, name: str, host: str) -> str:
    from bs4 import BeautifulSoup

    needle = _compact_text(name)
    if not needle or not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for box in soup.select("div.title-box"):
        title_el = box.select_one("p.series-title, [test-title]")
        title = title_el.get_text(" ", strip=True) if title_el else box.get_text(" ", strip=True)
        compact = _compact_text(title)
        if needle not in compact and compact not in needle:
            continue
        link = box.select_one("a.main-link, a[test-first-url]")
        href = (link.get("href") if link else "") or ""
        if not href:
            continue
        if href.startswith("/"):
            href = f"https://{host}{href}"
        if is_official_preview_url(href):
            return href
    return ""


def _title_hit(needle: str, haystack: str) -> bool:
    n = _compact_text(needle)
    h = _compact_text(haystack)
    if not n or not h:
        return False
    if n in h:
        return True
    return len(h) >= min(8, len(n)) and h in n


def _absolutize(href: str, host: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return f"https://{host}{href}"
    return href


def _normalize_preview_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    host = _host_of(url)
    if host == "championcross.jp":
        m = re.match(r"^/series/([^/]+)/?$", path)
        if m:
            return f"https://championcross.jp/series/{m.group(1)}/1"
    return url


def pick_matching_preview_link(
    html: str,
    name: str,
    host: str,
    *,
    require_full_title: bool = False,
) -> str:
    found = pick_giga_first_episode(html, name, host)
    if found:
        return _normalize_preview_url(found)
    from bs4 import BeautifulSoup

    if not html or not name:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = _absolutize(a.get("href") or "", host)
        href = _normalize_preview_url(href)
        if not is_official_preview_url(href):
            continue
        hay = a.get_text(" ", strip=True)
        for img in a.select("img[alt]"):
            hay += " " + (img.get("alt") or "")
        node = a.parent
        for _ in range(6):
            if node is None:
                break
            if node.name in {"body", "html", "main", "header", "footer", "nav"}:
                break
            hay += " " + node.get_text(" ", strip=True)[:240]
            if node.name in {"li", "article"}:
                break
            node = node.parent
        if require_full_title:
            if _compact_text(name) not in _compact_text(hay):
                continue
        elif not _title_hit(name, hay):
            continue
        key = href.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        path = urlparse(href).path.lower()
        score = 0
        if _title_hit(name, hay):
            score += 5
        if "/episode" in path:
            score += 4
        if "/viewer" in path:
            score += 4
        if "1話" in hay or "はじめから" in hay:
            score += 3
        ranked.append((score, href))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def search_giga_preview(comic: Comic) -> str:
    from manga_checker.http import make_session

    name = _full_preview_name(comic)
    short = _preview_name(comic)
    hosts = list(preview_hosts_for(comic)) or list(_CROSS_PREVIEW_SITES)
    if not name:
        return ""
    session = make_session()
    terms = [name]
    if short and short not in terms:
        terms.append(short)
    first = name.split()[0]
    if first and first not in terms:
        terms.append(first)
    for host in hosts:
        for term in terms:
            for search_url in _host_search_urls(host, term):
                try:
                    response = session.get(search_url, timeout=20)
                except Exception:
                    response = None
                url = ""
                if response is not None and response.status_code < 400:
                    url = pick_matching_preview_link(
                        response.text,
                        name,
                        host,
                        require_full_title=(term != name),
                    )
                if url:
                    return url
        try:
            hits = default_web_search(f"{name} 1話 site:{host}")
        except Exception:
            hits = []
        url = pick_official_url(hits, allowed_hosts=(host,))
        if not url and short != name:
            try:
                hits = default_web_search(f"{short} 1話 site:{host}")
            except Exception:
                hits = []
            url = pick_official_url(hits, allowed_hosts=(host,))
        if not url:
            tiny = _short_search_name(name)
            if tiny:
                try:
                    hits = default_web_search(f"{tiny} 1話 site:{host}")
                except Exception:
                    hits = []
                url = pick_official_url(hits, allowed_hosts=(host,))
        if url:
            return _normalize_preview_url(url)
        time.sleep(0.12)
    return ""


def _host_search_urls(host: str, term: str) -> list[str]:
    q = quote(term)
    if "comic-walker" in host:
        return [
            f"https://comic-walker.com/search/?keyword={q}",
            f"https://comic-walker.com/search?keyword={q}",
        ]
    if "comic-days" in host:
        return [f"https://comic-days.com/search?q={q}"]
    if "pocket.shonenmagazine" in host or "magazine-pocket" in host:
        return [
            f"https://pocket.shonenmagazine.com/search?q={q}",
            f"https://pocket.shonenmagazine.com/episode/search?q={q}",
        ]
    if "sirius" in host:
        return [
            f"https://shonen-sirius.com/search?q={q}",
            f"https://www.shonen-sirius.com/?s={q}",
        ]
    if "sunday-webry" in host:
        return [f"https://www.sunday-webry.com/search?q={q}"]
    if "sunday.webry" in host:
        return [f"https://www.sunday.webry.com/search?q={q}"]
    if host == "ciao.shogakukan.co.jp":
        return [f"https://ciao.shogakukan.co.jp/search?q={q}"]
    if "corocoro" in host:
        return [f"https://www.corocoro.jp/search?q={q}"]
    if host == "championcross.jp":
        return [f"https://championcross.jp/search?q={q}"]
    if "alphapolis" in host:
        return [f"https://www.alphapolis.co.jp/search?query={q}"]
    return [f"https://{host}/search?q={q}"]


def _pick_official_from_query(fn: SearchFn, query: str) -> str:
    try:
        results = fn(query) or []
    except Exception:
        results = []
    url = pick_official_url(list(results))
    if url:
        return _normalize_preview_url(url)
    return ""


def search_official_preview(comic: Comic, *, search_fn: SearchFn | None = None) -> str:
    """出版社の公式配信サイトを先に探し、無ければウェブの『タイトル 1話』へ。"""
    if search_fn is None:
        url = search_giga_preview(comic)
        if url:
            return url
    fn = search_fn or default_web_search
    web_queries = search_queries(comic, include_sites=False)
    for query in web_queries:
        url = _pick_official_from_query(fn, query)
        if url:
            return url
    for query in search_queries(comic, include_sites=True):
        if query in web_queries:
            continue
        url = _pick_official_from_query(fn, query)
        if url:
            return url
    return ""


def load_preview_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, row in payload.items():
        if not isinstance(row, dict):
            continue
        official = str(row.get("official_url") or "")
        if official and not is_official_preview_url(official):
            official = ""
        result[str(key)] = {
            "official_url": official,
            "title": str(row.get("title") or ""),
        }
    return result


def save_preview_cache(path: Path, cache: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def preview_links_for(
    comic: Comic,
    cache_row: dict[str, str] | None = None,
    *,
    today: date | None = None,
) -> dict[str, str]:
    official = (cache_row or {}).get("official_url") or ""
    if official and not is_official_preview_url(official):
        official = ""
    fallback_url, fallback_label = fallback_catalog_url(comic)
    cmoa = cmoa_search_url(comic) if is_released(comic.pubdate, today=today) else ""
    return {
        "official_url": official,
        "fallback_url": "" if official else fallback_url,
        "fallback_label": "" if official else fallback_label,
        "cmoa_url": cmoa,
    }


def preview_fetch_order(
    comics: list[Comic],
    today: date | None = None,
) -> list[Comic]:
    """当月→未来月→過去月の順。時間切れでも来月分が後回しにならないようにする。"""
    today = today or date.today()
    current = (today.year, today.month)

    def key(comic: Comic) -> tuple[int, tuple[int, int], str]:
        ym = year_month_from_pubdate(comic.pubdate) or current
        if ym == current:
            bucket = 0
        elif ym > current:
            bucket = 1
        else:
            bucket = 2
        return (bucket, ym, comic.display_title)

    return sorted(comics, key=key)


def resolve_preview_cache(
    comics: list[Comic],
    cache: dict[str, dict[str, str]],
    *,
    fetch: bool = False,
    limit: int = 0,
    delay_sec: float = 1.2,
    search_fn: SearchFn | None = None,
    today: date | None = None,
) -> int:
    """キャッシュを更新する。戻り値は新規検索した件数。"""
    searched = 0
    for comic in preview_fetch_order(comics, today=today):
        key = preview_cache_key(comic)
        if not key:
            continue
        row = cache.get(key) or {}
        if not fetch:
            continue
        existing = row.get("official_url") or ""
        if existing and is_official_preview_url(existing):
            continue
        if limit and searched >= limit:
            continue
        url = search_official_preview(comic, search_fn=search_fn)
        cache[key] = {
            "official_url": url,
            "title": comic.display_title,
        }
        searched += 1
        if delay_sec > 0:
            time.sleep(delay_sec)
    return searched
