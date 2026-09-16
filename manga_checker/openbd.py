"""openBD から書誌を補完する。楽天の書影は上書きしない。"""

from __future__ import annotations

import time

import requests

from manga_checker.dates import prefer_pubdate
from manga_checker.http import make_session
from manga_checker.models import Comic
from manga_checker.retail_dates import collect_onix_pubdates

OPENBD_GET = "https://api.openbd.jp/v1/get"


def enrich_with_openbd(comics: list[Comic], session: requests.Session | None = None) -> list[Comic]:
    session = session or make_session()
    isbn_map = {c.isbn: c for c in comics if c.isbn}
    isbns = list(isbn_map.keys())
    for i in range(0, len(isbns), 1000):
        chunk = isbns[i : i + 1000]
        response = session.post(OPENBD_GET, data={"isbn": ",".join(chunk)}, timeout=60)
        response.raise_for_status()
        payload = response.json()
        for record in payload:
            if not record:
                continue
            summary = record.get("summary") or {}
            isbn = (summary.get("isbn") or "").replace("-", "")
            comic = isbn_map.get(isbn)
            if not comic:
                continue
            comic.title = comic.title or summary.get("title") or comic.title
            comic.author = comic.author or (summary.get("author") or "").replace("／", " / ")
            comic.publisher = comic.publisher or summary.get("publisher") or ""
            comic.pubdate = prefer_pubdate(
                *collect_onix_pubdates(record),
                *_record_pubdates(record),
                comic.pubdate,
            )
            comic.volume = comic.volume or summary.get("volume") or ""
            comic.series = comic.series or summary.get("series") or ""
            if comic.cover_url:
                if "rakuten" in comic.cover_url:
                    comic.cover_source = "rakuten"
            else:
                cover = _cover_from_record(record)
                if cover:
                    comic.cover_url = cover
                    comic.cover_source = comic.cover_source or "openbd"
            comic.source = f"{comic.source}+openbd" if comic.source else "openbd"
        if i + 1000 < len(isbns):
            time.sleep(0.3)

    for comic in comics:
        if comic.cover_url and "rakuten" in comic.cover_url:
            comic.cover_source = "rakuten"
    return comics


def _record_pubdates(record: dict) -> list[str]:
    found: list[str] = []
    summary = record.get("summary") or {}
    if summary.get("pubdate"):
        found.append(str(summary.get("pubdate")))
    onix = record.get("onix") or {}
    pub_detail = onix.get("PublishingDetail") or {}
    publishing_dates = pub_detail.get("PublishingDate") or []
    if isinstance(publishing_dates, dict):
        publishing_dates = [publishing_dates]
    for item in publishing_dates:
        found.extend(_onix_date_values(item))
    product_supply = onix.get("ProductSupply") or {}
    supplies = product_supply.get("SupplyDetail") or []
    if isinstance(supplies, dict):
        supplies = [supplies]
    for supply in supplies:
        supply_dates = (supply or {}).get("SupplyDate") or []
        if isinstance(supply_dates, dict):
            supply_dates = [supply_dates]
        for item in supply_dates:
            found.extend(_onix_date_values(item))
    hanmoto = record.get("hanmoto") or {}
    for key in ("dateshuppan", "datejpro", "pubdate"):
        if hanmoto.get(key):
            found.append(str(hanmoto.get(key)))
    return [value for value in found if value]


def _onix_date_values(item: dict | str | None) -> list[str]:
    if item is None:
        return []
    if isinstance(item, str):
        return [item] if item.strip() else []
    values: list[str] = []
    raw = item.get("Date")
    if isinstance(raw, dict):
        raw = raw.get("#text") or raw.get("content") or raw.get("value") or ""
    if raw:
        values.append(str(raw).strip())
    nested = item.get("PublishingDate")
    if nested:
        values.extend(_onix_date_values(nested))
    return values


def _cover_from_record(record: dict) -> str:
    summary = record.get("summary") or {}
    cover = (summary.get("cover") or "").strip()
    if cover:
        return cover
    onix = record.get("onix") or {}
    collateral = onix.get("CollateralDetail") or {}
    resources = collateral.get("SupportingResource") or []
    if isinstance(resources, dict):
        resources = [resources]
    for resource in resources:
        version = resource.get("ResourceVersion") or resource
        if isinstance(version, list):
            version = version[0] if version else {}
        link = version.get("ResourceLink") or ""
        if isinstance(link, dict):
            link = link.get("content") or link.get("src") or ""
        if isinstance(link, str) and link.startswith("http"):
            return link
    return ""
