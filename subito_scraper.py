#!/usr/bin/env python3
import json
import os
import re
import time
from urllib.parse import quote_plus, urlparse, urlunparse
import cloudscraper
import requests

KEYWORDS = ["olympus", "lumix"]
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TUO_TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TUO_CHAT_ID")
DB_FILE = "seen_subito.json"

def get_scraper():
    return cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})

def canon_url(url):
    if not url: return ""
    if url.startswith("/"): url = "https://www.subito.it" + url
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))

def extract_next_data(text):
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    return json.loads(m.group(1)) if m else None

def walk_ads(node):
    if isinstance(node, dict):
        urls = node.get("urls")
        if isinstance(node.get("subject"), str) and isinstance(urls, dict) and urls.get("default"):
            yield node
            return
        for v in node.values():
            yield from walk_ads(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_ads(v)

def parse_subito_page(kw):
    # Cerca nella categoria 'fotografia' in tutta Italia ordinando per data decrescente
    url = f"https://www.subito.it/annunci-italia/vendita/fotografia/?q={quote_plus(kw)}&order=datedesc"
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code != 200: return []
    except Exception:
        return []

    data = extract_next_data(res.text)
    if not data: return []

    items = []
    for ad in walk_ads(data):
        title = ad.get("subject", "").strip()
        link = canon_url(ad.get("urls", {}).get("default", ""))
        
        # Prezzo
        price = ""
        for f in ad.get("features", []):
            if f.get("uri") == "/price" or f.get("label") == "Prezzo":
                val = f.get("values", [{}])[0].get("value", "")
                if val: price = f"{val} €"
                break

        # Luogo
        geo = ad.get("geo") or {}
        town = geo.get("town", {}).get("value", "") if isinstance(geo.get("town"), dict) else ""
        city = geo.get("city", {}).get("shortName", "") if isinstance(geo.get("city"), dict) else ""
        location = f"{town} ({city})" if town and city else town or city or "Italia"

        if link and title:
            items.append({
                "key": link,
                "title": title,
                "link": link,
                "price": price,
                "location": location,
                "kw": kw.upper()
            })
    return items

def send_telegram(item):
    text = (
        f"📷 <b>Nuovo annuncio [{item['kw']}]</b>\n\n"
        f"📌 <b>{item['title']}</b>\n"
        f"💶 <b>Prezzo:</b> {item['price'] or 'Non specificato'}\n"
        f"📍 <b>Luogo:</b> {item['location']}\n\n"
        f"🔗 <a href='{item['link']}'>Apri su Subito.it</a>"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def load_seen():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_seen(seen):
    with open(DB_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def main():
    seen = load_seen()
    new_count = 0
    for kw in KEYWORDS:
        ads = parse_subito_page(kw)
        for ad in ads:
            if ad["key"] not in seen:
                if send_telegram(ad):
                    seen[ad["key"]] = time.time()
                    new_count += 1
                time.sleep(1)
    if new_count > 0:
        save_seen(seen)

if __name__ == "__main__":
    main()
