"""公式特典まとめ・出版社告知との照合。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from manga_checker.privilege import STATUS_NO, STATUS_YES
from manga_checker.title_match import titles_match
from manga_checker.volume import normalize_text

KUMA_URL = "https://www.kumabook.com/comic_tokuten/"
KIKUYA_PRODUCTS = "https://kikuyashoten.myshopify.com/products.json"
KIKUYA_SHOP = "https://kikuyashoten.myshopify.com"
MELON_PRIVILEGE = "https://www.melonbooks.co.jp/privilege/privilege.php"
GAMERS_PRIVILEGE = "https://www.gamers.co.jp/products/privilege_list.php"

PUBLISHER_PAGES = (
    "https://houbunsha.co.jp/",
    "https://tobooks.jp/",
    "https://magazine.jp.square-enix.com/top/event/",
    "https://www.kadokawa.co.jp/information/",
    "https://promo.kadokawa.co.jp/kadocomifair/",
)

STORE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("animate", ("アニメイト",)),
    ("melonbooks", ("メロンブックス", "メロン限定")),
    ("gamers", ("ゲーマーズ",)),
    ("toranoana", ("とらのあな",)),
    ("kikuya", ("喜久屋",)),
    ("kinokuniya", ("紀伊國屋", "紀伊国屋")),
    ("kumazawa", ("くまざわ",)),
)

_KIKUYA_BONUS = re.compile(
    r"イラストカード|描き下ろし|特典|ペーパー|ブロマイド|リーフレット|しおり"
)
_PUBLISHER_BONUS = re.compile(
    r"特典|描き下ろし|イラストカード|ペーパー|リーフレット|限定版"
)


@dataclass
class OfficialHit:
    store_id: str
    text: str
    url: str
    keywords: list[str] = field(default_factory=list)
    source: str = "store"


class OfficialIndex:
    def __init__(self) -> None:
        self.entries: dict[str, list[OfficialHit]] = {
            "kumazawa": [],
            "kikuya": [],
            "melonbooks": [],
            "gamers": [],
            "animate": [],
            "toranoana": [],
            "kinokuniya": [],
        }
        self.loaded = False

    def load(self, session: requests.Session) -> None:
        if self.loaded:
            return
        print("公式特典ページを照合用に取得しています…")
        self.entries["kumazawa"] = _load_kumazawa(session)
        self.entries["kikuya"] = _load_kikuya(session)
        self.entries["melonbooks"].extend(_load_link_list(session, MELON_PRIVILEGE, "melonbooks"))
        self.entries["gamers"].extend(_load_link_list(session, GAMERS_PRIVILEGE, "gamers"))
        for page in PUBLISHER_PAGES:
            for hit in _load_publisher_page(session, page):
                self.entries.setdefault(hit.store_id, []).append(hit)
            time.sleep(0.3)
        self.loaded = True
        counts = {k: len(v) for k, v in self.entries.items() if v}
        print("  照合件数: " + ", ".join(f"{k}={n}" for k, n in counts.items()))

    def lookup(self, store_id: str, title: str, isbn: str = "") -> OfficialHit | None:
        publisher_hit = None
        store_hit = None
        for hit in self.entries.get(store_id, []):
            if not titles_match(title, hit.text, isbn):
                continue
            if store_id == "kikuya" and not hit.keywords:
                continue
            if hit.source == "publisher" and publisher_hit is None:
                publisher_hit = hit
            elif hit.source != "publisher" and store_hit is None:
                store_hit = hit
        return publisher_hit or store_hit


def lookup_status(
    index: OfficialIndex,
    store_id: str,
    title: str,
    isbn: str,
    fallback_url: str,
):
    hit = index.lookup(store_id, title, isbn)
    if hit:
        label = "出版社公式" if hit.source == "publisher" else "公式特典ページ"
        detail = f"{label}で確認"
        if hit.keywords:
            detail += ": " + " / ".join(hit.keywords[:3])
        link = fallback_url
        return STATUS_YES, detail, link
    return STATUS_NO, "公式特典ページに該当タイトルはありません。", fallback_url


def _load_kumazawa(session: requests.Session) -> list[OfficialHit]:
    hits: list[OfficialHit] = []
    for page in range(1, 12):
        url = KUMA_URL if page == 1 else f"{KUMA_URL}page/{page}/"
        html = _get(session, url)
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article, .post, .entry, h2, h3")
        page_hits = 0
        for el in articles:
            text = el.get_text(" ", strip=True)
            if "特典" not in text and "タイトル" not in text:
                continue
            if len(text) < 8:
                continue
            hits.append(OfficialHit("kumazawa", text, url, ["くまざわ限定特典"]))
            page_hits += 1
        if page_hits == 0:
            break
        time.sleep(0.35)
    return _dedupe_hits(hits)


def _load_kikuya(session: requests.Session) -> list[OfficialHit]:
    hits: list[OfficialHit] = []
    for page in range(1, 15):
        try:
            response = session.get(
                KIKUYA_PRODUCTS,
                params={"limit": 250, "page": page},
                timeout=30,
            )
            if response.status_code >= 400:
                break
            payload = response.json()
        except (requests.RequestException, ValueError):
            break
        products = payload.get("products") or []
        if not products:
            break
        for product in products:
            title = product.get("title") or ""
            sku = ""
            variants = product.get("variants") or []
            if variants:
                sku = str(variants[0].get("sku") or "")
            blob = f"{title} {sku}"
            keywords = _KIKUYA_BONUS.findall(normalize_text(title))
            hits.append(OfficialHit("kikuya", blob, KIKUYA_SHOP, keywords))
        time.sleep(0.25)
    return hits


def _load_link_list(session: requests.Session, url: str, store_id: str) -> list[OfficialHit]:
    html = _get(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    hits: list[OfficialHit] = []
    for a in soup.find_all("a"):
        text = a.get_text(" ", strip=True)
        alts = " ".join(
            str(img.get("alt") or "") for img in a.find_all("img")
        )
        card_text = _privilege_card_text(a)
        blob = " ".join(part for part in (text, alts, card_text) if part)
        if len(blob.strip()) < 6:
            continue
        if not re.search(r"特典|限定|リーフレット|描き下ろし|カード", blob):
            continue
        hits.append(
            OfficialHit(
                store_id,
                blob,
                url,
                _KIKUYA_BONUS.findall(normalize_text(blob)) or ["特典"],
            )
        )
    return _dedupe_hits(hits)


def _privilege_card_text(tag) -> str:
    """特典一覧は『特典』リンクと作品名が別要素であることが多いので、カード全体を見る。"""
    for parent in tag.parents:
        name = getattr(parent, "name", None)
        if name in {"ul", "ol", "body", "html", "[document]"}:
            break
        if name not in {"li", "article", "section", "tr", "div"}:
            continue
        text = parent.get_text(" ", strip=True)
        if 8 < len(text) <= 700 and re.search(r"特典|限定", text):
            return text
    return ""


def _load_publisher_page(session: requests.Session, url: str) -> list[OfficialHit]:
    html = _get(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    hits: list[OfficialHit] = []
    for el in soup.find_all(["a", "article", "li", "h2", "h3", "p"]):
        text = el.get_text(" ", strip=True)
        if len(text) < 12 or not _PUBLISHER_BONUS.search(text):
            continue
        stores = [sid for sid, names in STORE_HINTS if any(name in text for name in names)]
        if not stores:
            continue
        keywords = _PUBLISHER_BONUS.findall(text)
        for store_id in stores:
            hits.append(
                OfficialHit(store_id, text, url, keywords, source="publisher")
            )
    return _dedupe_hits(hits)


def _get(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, timeout=25)
        if response.status_code >= 400:
            return ""
        return response.text
    except requests.RequestException:
        return ""


def _dedupe_hits(hits: list[OfficialHit]) -> list[OfficialHit]:
    seen: set[str] = set()
    unique: list[OfficialHit] = []
    for hit in hits:
        key = f"{hit.store_id}:{normalize_text(hit.text)[:180]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique
