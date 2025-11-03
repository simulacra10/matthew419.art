#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import hmac
import base64
import hashlib
import datetime
from pathlib import Path

import requests
import frontmatter
import feedparser
from dateutil import tz

# =========================
# Config (tweak if desired)
# =========================
TIMEZONE = "America/New_York"

# USCCB RSS (primary & fallback) + headers
USCCB_RSS_PRIMARY = "https://bible.usccb.org/daily-readings/rss"
USCCB_RSS_FALLBACK = "https://feeds.feedburner.com/usccb/daily-readings"
HTTP_HEADERS = {
    "User-Agent": "matthew419.art-bot/1.0 (+https://matthew419.art)"
}

CONTENT_DIR = Path("content/post")

CHATGPT_RESPONSE = (
    "A contemplative AI-generated devotional artwork inspired by today’s Gospel."
)

IMAGE_PROMPT_STYLE = (
    "Catholic sacred art, reverent, contemplative, symbolic, no text, minimalist poster art, "
    "soft lighting, painterly, suitable for daily meditation"
)

OPENAI_IMAGE_MODEL = "gpt-image-1"
OPENAI_IMAGE_SIZE = "1024x1024"

# Abbreviation map commonly seen in USCCB feeds/pages
BOOK_MAP = {
    # OT (incl. deuterocanon abbreviations that may appear)
    "Gen": "Genesis", "Ex": "Exodus", "Lev": "Leviticus", "Num": "Numbers",
    "Dt": "Deuteronomy", "Deut": "Deuteronomy", "Jos": "Joshua", "Jgs": "Judges",
    "Ru": "Ruth", "1 Sm": "1 Samuel", "2 Sm": "2 Samuel", "1 Kgs": "1 Kings",
    "2 Kgs": "2 Kings", "1 Chr": "1 Chronicles", "2 Chr": "2 Chronicles",
    "Ezr": "Ezra", "Neh": "Nehemiah", "Tob": "Tobit", "Tb": "Tobit", "Jdt": "Judith",
    "Est": "Esther", "Job": "Job", "Ps": "Psalm", "Psalms": "Psalm", "Prv": "Proverbs",
    "Qoheleth": "Ecclesiastes", "Eccl": "Ecclesiastes", "Song": "Song of Songs",
    "Sg": "Song of Songs", "Wis": "Wisdom", "Sir": "Sirach", "Is": "Isaiah",
    "Jer": "Jeremiah", "Lam": "Lamentations", "Bar": "Baruch", "Ez": "Ezekiel",
    "Dn": "Daniel", "Hos": "Hosea", "Jl": "Joel", "Am": "Amos", "Ob": "Obadiah",
    "Jon": "Jonah", "Mi": "Micah", "Na": "Nahum", "Hab": "Habakkuk", "Zep": "Zephaniah",
    "Hg": "Haggai", "Zec": "Zechariah", "Mal": "Malachi", "1 Mc": "1 Maccabees",
    "2 Mc": "2 Maccabees",
    # NT
    "Mt": "Matthew", "Mk": "Mark", "Lk": "Luke", "Lk.": "Luke", "Jn": "John",
    "Acts": "Acts", "Rom": "Romans", "1 Cor": "1 Corinthians", "2 Cor": "2 Corinthians",
    "Gal": "Galatians", "Eph": "Ephesians", "Phil": "Philippians", "Col": "Colossians",
    "1 Thes": "1 Thessalonians", "2 Thes": "2 Thessalonians", "1 Tm": "1 Timothy",
    "2 Tm": "2 Timothy", "Tit": "Titus", "Phlm": "Philemon", "Heb": "Hebrews",
    "Jas": "James", "1 Pt": "1 Peter", "2 Pt": "2 Peter", "1 Jn": "1 John",
    "2 Jn": "2 John", "3 Jn": "3 John", "Jude": "Jude", "Rv": "Revelation"
}

# Deuterocanonical books not present in KJV (graceful note instead of text)
DEUTERO = {
    "Tobit", "Judith", "Wisdom", "Sirach", "Baruch", "1 Maccabees", "2 Maccabees"
}

# =========================
# Utility / Helpers
# =========================

def today_local_date():
    tzinfo = tz.gettz(TIMEZONE)
    return datetime.datetime.now(tzinfo).date()

def _normalize_book(abbr: str) -> str:
    a = abbr.strip()
    a = re.sub(r"\s+", " ", a)  # normalize inner spaces (e.g., "1  Sm" -> "1 Sm")
    return BOOK_MAP.get(a, a)

def _normalize_verses(vs: str) -> str:
    vs = vs.strip()
    vs = vs.replace("–", "-").replace("—", "-")
    vs = re.sub(r"\s+", "", vs)
    return vs

def slug_from_reference(ref: str) -> str:
    """
    "Matthew 5:17-19" -> "matthew5_17-19"
    "Deuteronomy 4:1,5-9" -> "deuteronomy4_1_5-9"
    """
    m = re.match(r"^\s*([1-3]?\s?[A-Za-z ]+)\s+(\d+):([\d,ab\-–—\s]+)\s*$", ref)
    if not m:
        base = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
        return base or "post"
    book = m.group(1).lower().replace(" ", "")
    chapter = m.group(2)
    verses = _normalize_verses(m.group(3)).replace(",", "_")
    return f"{book}{chapter}_{verses}"

# =========================
# Readings: RSS + HTML fallback
# =========================

def fetch_usccb_feed():
    # Try primary with request headers; fallback to FeedBurner
    feed = feedparser.parse(USCCB_RSS_PRIMARY, request_headers=HTTP_HEADERS)
    if getattr(feed, "entries", None):
        return feed
    return feedparser.parse(USCCB_RSS_FALLBACK, request_headers=HTTP_HEADERS)

def pick_today_entry(feed, target_date):
    # Titles usually include "Month D, YYYY"
    fmt1 = target_date.strftime("%B %-d, %Y")
    fmt2 = target_date.strftime("%B %#d, %Y")  # Windows quirk
    for e in getattr(feed, "entries", []):
        t = e.get("title", "")
        if fmt1 in t or fmt2 in t:
            return e
    return feed.entries[0] if getattr(feed, "entries", None) else None

def _find_ref_in_text(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            abbr = m.group(1)
            chap = m.group(2)
            verses = _normalize_verses(m.group(3))
            book = _normalize_book(abbr)
            return f"{book} {chap}:{verses}"
    return None

def extract_first_and_gospel_from_entry(entry):
    # Build a unified text blob from typical feed fields
    text = " ".join([
        entry.get("summary", ""),
        entry.get("description", ""),
        entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
    ])

    reading_patterns = [
        r"(?:Reading\s*I|First\s*Reading|Reading\s*1)\s*:\s*([1-3]?\s?[A-Za-z\. ]+)\s*([0-9]+):([\d,ab\-–—\s]+)"
    ]
    gospel_patterns = [
        r"Gospel\s*:\s*([1-3]?\s?[A-Za-z\. ]+)\s*([0-9]+):([\d,ab\-–—\s]+)"
    ]

    first_ref = _find_ref_in_text(reading_patterns, text)
    gospel_ref = _find_ref_in_text(gospel_patterns, text)
    return first_ref, gospel_ref

def fetch_usccb_daily_page(target_date):
    ymd = target_date.strftime("%Y-%m-%d")
    url = f"https://bible.usccb.org/daily-bible-reading?date={ymd}"
    r = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_first_and_gospel_from_html(html):
    # Strip tags crudely and collapse whitespace for robust regex search
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    reading_patterns = [
        r"(?:Reading\s*I|First\s*Reading|Reading\s*1)\s*:\s*([1-3]?\s?[A-Za-z\. ]+)\s*([0-9]+):([\d,ab\-–—\s]+)"
    ]
    gospel_patterns = [
        r"Gospel\s*:\s*([1-3]?\s?[A-Za-z\. ]+)\s*([0-9]+):([\d,ab\-–—\s]+)"
    ]

    first_ref = _find_ref_in_text(reading_patterns, text)
    gospel_ref = _find_ref_in_text(gospel_patterns, text)
    return first_ref, gospel_ref

# =========================
# Scripture text (KJV)
# =========================

def fetch_kjv_text(ref_str):
    """
    bible-api.com KJV. If deuterocanonical, return a note instead.
    """
    if not ref_str:
        return ""

    m = re.match(r"^\s*([1-3]?\s?[A-Za-z ]+)\s+\d+:", ref_str)
    book = m.group(1).strip() if m else ""
    if book in DEUTERO:
        return f"(Text for {ref_str} is from a deuterocanonical book not present in KJV. Please see the USCCB page for the full reading.)"

    url = f"https://bible-api.com/{requests.utils.quote(ref_str)}?translation=kjv"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        verses = data.get("verses", [])
        if not verses:
            return f"(No verses returned for {ref_str}.)"
        lines = []
        for v in verses:
            num = v.get("verse")
            text = v.get("text", "").rstrip()
            text = re.sub(r"\s+", " ", text).strip()
            lines.append(f"{num} {text}")
        return "\n".join(lines).strip()
    except Exception:
        return f"(Unable to retrieve text for {ref_str} at this time.)"

# =========================
# Image generation + Cloudinary
# =========================

def openai_generate_image(prompt):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": OPENAI_IMAGE_SIZE,
        "n": 1,
        "response_format": "b64_json",
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    b64 = r.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)

def parse_cloudinary_url():
    """
    CLOUDINARY_URL = cloudinary://<api_key>:<api_secret>@<cloud_name>
    """
    conn = os.environ.get("CLOUDINARY_URL", "")
    m = re.match(r"^cloudinary://([^:]+):([^@]+)@([^/]+)", conn)
    if not m:
        raise RuntimeError("CLOUDINARY_URL is missing or invalid")
    api_key, api_secret, cloud_name = m.groups()
    return api_key, api_secret, cloud_name

def upload_to_cloudinary(file_bytes, public_id):
    api_key, api_secret, cloud_name = parse_cloudinary_url()
    endpoint = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    ts = str(int(time.time()))
    params_to_sign = f"public_id={public_id}&timestamp={ts}"
    signature = hmac.new(api_secret.encode("utf-8"),
                         params_to_sign.encode("utf-8"),
                         hashlib.sha1).hexdigest()

    files = {"file": ("image.png", file_bytes, "image/png")}
    data = {"api_key": api_key, "timestamp": ts, "signature": signature, "public_id": public_id}

    r = requests.post(endpoint, files=files, data=data, timeout=60)
    r.raise_for_status()
    # Delivery URL forcing webp + auto quality (matches your existing style)
    delivery = f"https://res.cloudinary.com/{cloud_name}/image/upload/f_webp,q_auto/{public_id}.webp"
    return delivery

# =========================
# Post rendering / write
# =========================

def render_body(image_url, first_ref, first_text, gospel_ref, gospel_text):
    parts = []
    parts.append(f"Image: {image_url}\n")
    if first_ref:
        parts.append(f"**First Reading — {first_ref}**\n")
        parts.append(first_text.strip() + "\n")
    if gospel_ref:
        parts.append(f"**Gospel — {gospel_ref}**\n")
        parts.append(gospel_text.strip() + "\n")
    parts.append("### ChatGPT Response\n")
    parts.append(CHATGPT_RESPONSE.strip())
    return "\n".join(parts).strip() + "\n"

def write_post(slug, title, body, date_iso):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = CONTENT_DIR / f"{slug}.md"
    post = frontmatter.Post(body, **{
        "title": title,
        "date": date_iso,
        "draft": False
    })
    md_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return md_path

# =========================
# Main
# =========================

def main():
    today = today_local_date()

    # Try RSS
    entry = None
    try:
        feed = fetch_usccb_feed()
        entry = pick_today_entry(feed, today) if getattr(feed, "entries", None) else None
    except Exception as e:
        print(f"RSS fetch error: {e}")

    first_ref = gospel_ref = None
    if entry:
        try:
            first_ref, gospel_ref = extract_first_and_gospel_from_entry(entry)
        except Exception as e:
            print(f"RSS parse error: {e}")

    # Fallback: official HTML page if refs not found via RSS
    if not (first_ref or gospel_ref):
        try:
            html = fetch_usccb_daily_page(today)
            fr2, gr2 = extract_first_and_gospel_from_html(html)
            first_ref = first_ref or fr2
            gospel_ref = gospel_ref or gr2
        except Exception as e:
            print(f"HTML fallback error: {e}")

    if not (first_ref or gospel_ref):
        raise RuntimeError("No readings found via RSS or HTML fallback.")

    # Fetch texts (KJV, with graceful deuterocanonical note)
    first_text = fetch_kjv_text(first_ref) if first_ref else ""
    gospel_text = fetch_kjv_text(gospel_ref) if gospel_ref else ""

    # Generate image, ground on Gospel if available, else First
    ref_for_image = gospel_ref or first_ref or "the daily readings"
    prompt = (
        f"Create a devotional image inspired by the Gospel passage {ref_for_image}. "
        f"Focus on symbolism rather than literal depiction. {IMAGE_PROMPT_STYLE}"
    )
    img_bytes = openai_generate_image(prompt)

    # Slug & Cloudinary public_id based on Gospel (fallback First)
    slug = slug_from_reference(gospel_ref or first_ref or "daily-gospel")
    public_id = f"matthew419/{today.year}/{today.month:02d}/{slug}"
    image_url = upload_to_cloudinary(img_bytes, public_id)

    # Title: prefer Gospel reference
    title = gospel_ref or first_ref or "Daily Readings"

    body = render_body(image_url, first_ref, first_text, gospel_ref, gospel_text)
    md_path = write_post(slug, title=title, body=body, date_iso=today.isoformat())
    print(f"Wrote {md_path}")

if __name__ == "__main__":
    main()
