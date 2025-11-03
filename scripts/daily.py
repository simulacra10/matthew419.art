#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import base64
import hashlib
import datetime
import html as htmlmod
from pathlib import Path

import requests
import frontmatter
import feedparser
from dateutil import tz

# =========================
# Config
# =========================
TIMEZONE = "America/New_York"

# Feeds (try Catholic.org first, then USCCB)
CATHOLIC_ORG_RSS = "https://www.catholic.org/xml/rss_dailyreadings.php"
USCCB_RSS_PRIMARY = "https://bible.usccb.org/daily-readings/rss"
USCCB_RSS_FALLBACK = "https://feeds.feedburner.com/usccb/daily-readings"

HTTP_HEADERS = {
    "User-Agent": "matthew419.art-bot/1.4 (+https://matthew419.art)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
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

# Abbreviation & full-name map commonly seen in daily-reading feeds/pages
BOOK_MAP = {
    # OT + deuterocanon
    "Gen": "Genesis", "Genesis": "Genesis",
    "Ex": "Exodus", "Exodus": "Exodus",
    "Lev": "Leviticus", "Leviticus": "Leviticus",
    "Num": "Numbers", "Numbers": "Numbers",
    "Dt": "Deuteronomy", "Deut": "Deuteronomy", "Deuteronomy": "Deuteronomy",
    "Jos": "Joshua", "Joshua": "Joshua", "Jgs": "Judges", "Judges": "Judges",
    "Ru": "Ruth", "Ruth": "Ruth",
    "1 Sm": "1 Samuel", "1 Samuel": "1 Samuel", "2 Sm": "2 Samuel", "2 Samuel": "2 Samuel",
    "1 Kgs": "1 Kings", "1 Kings": "1 Kings", "2 Kgs": "2 Kings", "2 Kings": "2 Kings",
    "1 Chr": "1 Chronicles", "1 Chronicles": "1 Chronicles",
    "2 Chr": "2 Chronicles", "2 Chronicles": "2 Chronicles",
    "Ezr": "Ezra", "Ezra": "Ezra", "Neh": "Nehemiah", "Nehemiah": "Nehemiah",
    "Tob": "Tobit", "Tb": "Tobit", "Tobit": "Tobit",
    "Jdt": "Judith", "Judith": "Judith", "Est": "Esther", "Esther": "Esther",
    "Job": "Job", "Ps": "Psalm", "Psalms": "Psalm", "Psalm": "Psalm",
    "Prv": "Proverbs", "Proverbs": "Proverbs",
    "Qoheleth": "Ecclesiastes", "Eccl": "Ecclesiastes", "Ecclesiastes": "Ecclesiastes",
    "Song": "Song of Songs", "Sg": "Song of Songs", "Song of Songs": "Song of Songs",
    "Wis": "Wisdom", "Wisdom": "Wisdom", "Sir": "Sirach", "Sirach": "Sirach",
    "Is": "Isaiah", "Isaiah": "Isaiah", "Jer": "Jeremiah", "Jeremiah": "Jeremiah",
    "Lam": "Lamentations", "Lamentations": "Lamentations",
    "Bar": "Baruch", "Baruch": "Baruch", "Ez": "Ezekiel", "Ezekiel": "Ezekiel",
    "Dn": "Daniel", "Daniel": "Daniel",
    "Hos": "Hosea", "Hosea": "Hosea", "Jl": "Joel", "Joel": "Joel",
    "Am": "Amos", "Amos": "Amos", "Ob": "Obadiah", "Obadiah": "Obadiah",
    "Jon": "Jonah", "Jonah": "Jonah", "Mi": "Micah", "Micah": "Micah",
    "Na": "Nahum", "Nahum": "Nahum", "Hab": "Habakkuk", "Habakkuk": "Habakkuk",
    "Zep": "Zephaniah", "Zephaniah": "Zephaniah", "Hg": "Haggai", "Haggai": "Haggai",
    "Zec": "Zechariah", "Zechariah": "Zechariah", "Mal": "Malachi", "Malachi": "Malachi",
    "1 Mc": "1 Maccabees", "1 Maccabees": "1 Maccabees",
    "2 Mc": "2 Maccabees", "2 Maccabees": "2 Maccabees",

    # NT
    "Mt": "Matthew", "Matthew": "Matthew",
    "Mk": "Mark", "Mark": "Mark",
    "Lk": "Luke", "Lk.": "Luke", "Luke": "Luke",
    "Jn": "John", "John": "John", "Acts": "Acts",
    "Rom": "Romans", "Romans": "Romans",
    "1 Cor": "1 Corinthians", "1 Corinthians": "1 Corinthians",
    "2 Cor": "2 Corinthians", "2 Corinthians": "2 Corinthians",
    "Gal": "Galatians", "Galatians": "Galatians",
    "Eph": "Ephesians", "Ephesians": "Ephesians",
    "Phil": "Philippians", "Philippians": "Philippians",
    "Col": "Colossians", "Colossians": "Colossians",
    "1 Thes": "1 Thessalonians", "1 Thessalonians": "1 Thessalonians",
    "2 Thes": "2 Thessalonians", "2 Thessalonians": "2 Thessalonians",
    "1 Tm": "1 Timothy", "1 Timothy": "1 Timothy",
    "2 Tm": "2 Timothy", "2 Timothy": "2 Timothy",
    "Tit": "Titus", "Titus": "Titus", "Phlm": "Philemon", "Philemon": "Philemon",
    "Heb": "Hebrews", "Hebrews": "Hebrews", "Jas": "James", "James": "James",
    "1 Pt": "1 Peter", "1 Peter": "1 Peter", "2 Pt": "2 Peter", "2 Peter": "2 Peter",
    "1 Jn": "1 John", "1 John": "1 John", "2 Jn": "2 John", "2 John": "2 John",
    "3 Jn": "3 John", "3 John": "3 John", "Jude": "Jude",
    "Rv": "Revelation", "Revelation": "Revelation",
}

DEUTERO = {
    "Tobit", "Judith", "Wisdom", "Sirach", "Baruch", "1 Maccabees", "2 Maccabees"
}

# =========================
# Helpers
# =========================

def today_local_date():
    tzinfo = tz.gettz(TIMEZONE)
    return datetime.datetime.now(tzinfo).date()

def _normalize_book(abbr: str) -> str:
    a = abbr.strip()
    a = re.sub(r"\s+", " ", a)
    return BOOK_MAP.get(a, a)

def _normalize_verses(vs: str) -> str:
    vs = (vs or "").strip()
    vs = vs.replace("–", "-").replace("—", "-").replace(" to ", "-")
    vs = re.sub(r"[^\d,\- ]+", "", vs)  # drop letter suffixes like 'b'
    vs = re.sub(r"\s+", "", vs)
    vs = re.sub(r",+", ",", vs).strip(",")
    return vs

def _sanitize_ref(ref: str) -> str:
    if not ref:
        return ref
    ref = re.sub(r"\s+", " ", ref).strip()
    m = re.match(r"^\s*([1-3]?\s?[A-Za-z ]+)\s+(\d+):(.+?)\s*$", ref)
    if not m:
        return ref.strip(" ,;:-")
    book = _normalize_book(m.group(1))
    chap = m.group(2)
    verses = _normalize_verses(m.group(3))
    return f"{book} {chap}:{verses}"

def slug_from_reference(ref: str) -> str:
    ref = _sanitize_ref(ref or "")
    m = re.match(r"^\s*([1-3]?\s?[A-Za-z ]+)\s+(\d+):([\d,\- ]+)\s*$", ref)
    if not m:
        base = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-") or "post"
        return base
    book = m.group(1).lower().replace(" ", "")
    chapter = m.group(2)
    verses = m.group(3).replace(" ", "").replace(",", "_")
    return f"{book}{chapter}_{verses}"

# =========================
# Reading references: feeds + HTML fallback
# =========================

def fetch_feed(url):
    return feedparser.parse(url, request_headers=HTTP_HEADERS)

def pick_today_entry(feed, target_date):
    fmt1 = target_date.strftime("%B %-d, %Y")
    fmt2 = target_date.strftime("%B %#d, %Y")
    for e in getattr(feed, "entries", []):
        title = e.get("title", "")
        if fmt1 in title or fmt2 in title:
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
            return _sanitize_ref(f"{book} {chap}:{verses}")
    return None

def extract_refs_from_entry_generic(entry):
    text = " ".join([
        entry.get("title", ""),
        entry.get("summary", ""),
        entry.get("description", ""),
        entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
    ])

    text = htmlmod.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    book_keys = sorted(BOOK_MAP.keys(), key=len, reverse=True)
    book_alt = "|".join([re.escape(k) for k in book_keys])

    reading_patterns = [
        r"(?:Reading\s*I|First\s*Reading|Reading\s*1)\s*[:\-–]?\s*(%s)\s*([0-9]+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt
    ]
    gospel_patterns = [
        r"Gospel\s*[:\-–]?\s*(%s)\s*([0-9]+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt
    ]

    first_ref = _find_ref_in_text(reading_patterns, text)
    gospel_ref = _find_ref_in_text(gospel_patterns, text)

    if not (first_ref and gospel_ref):
        loose_ref = r"(%s)\s*([0-9]+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt
        matches = list(re.finditer(loose_ref, text, flags=re.IGNORECASE))
        if matches:
            def mk(m):
                b = _normalize_book(m.group(1))
                c = m.group(2)
                v = _normalize_verses(m.group(3))
                return _sanitize_ref(f"{b} {c}:{v}")
            if not first_ref and len(matches) >= 1:
                first_ref = mk(matches[0])
            if not gospel_ref and len(matches) >= 2:
                gospel_ref = mk(matches[1])

    return first_ref, gospel_ref

def fetch_usccb_daily_page(target_date):
    ymd = target_date.strftime("%Y-%m-%d")
    url = f"https://bible.usccb.org/daily-bible-reading?date={ymd}"
    r = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_refs_from_html(html_str):
    text = htmlmod.unescape(html_str)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    book_keys = sorted(BOOK_MAP.keys(), key=len, reverse=True)
    book_alt = "|".join([re.escape(k) for k in book_keys])

    def after(label_regex):
        m = re.search(label_regex, text, flags=re.IGNORECASE)
        if not m:
            return None
        return text[m.end():m.end()+200]

    first_snip = after(r"(Reading\s*I|First\s*Reading|Reading\s*1)\s*[:\-–]?")
    gospel_snip = after(r"(Gospel)\s*[:\-–]?")

    def grab(snippet):
        if not snippet:
            return None
        rx = re.compile(r"(%s)\s*(\d+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt, flags=re.IGNORECASE)
        m = rx.search(snippet)
        if not m:
            return None
        book = _normalize_book(m.group(1))
        chap = m.group(2)
        verses = _normalize_verses(m.group(3))
        return _sanitize_ref(f"{book} {chap}:{verses}") if re.search(r"\d", verses) else None

    first_ref = grab(first_snip)
    gospel_ref = grab(gospel_snip)

    if not (first_ref and gospel_ref):
        reading_patterns = [
            r"(?:Reading\s*I|First\s*Reading|Reading\s*1)\s*[:\-–]?\s*(%s)\s*(\d+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt
        ]
        gospel_patterns = [
            r"Gospel\s*[:\-–]?\s*(%s)\s*(\d+)\s*[:]\s*([\d,\-–—\s]+)" % book_alt
        ]
        first_ref = first_ref or _find_ref_in_text(reading_patterns, text)
        gospel_ref = gospel_ref or _find_ref_in_text(gospel_patterns, text)

    return first_ref, gospel_ref

# =========================
# Scripture text (KJV)
# =========================

def fetch_kjv_text(ref_str):
    if not ref_str:
        return ""
    ref_str = _sanitize_ref(ref_str)
    m = re.match(r"^\s*([1-3]?\s?[A-Za-z ]+)\s+\d+:", ref_str)
    book = m.group(1).strip() if m else ""
    if book in DEUTERO:
        return f"(Text for {ref_str} is from a deuterocanonical book not present in KJV. Please see the official readings page for the full text.)"
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
            txt = v.get("text", "").rstrip()
            txt = re.sub(r"\s+", " ", txt).strip()
            lines.append(f"{num} {txt}")
        return "\n".join(lines).strip()
    except Exception:
        return f"(Unable to retrieve text for {ref_str} at this time.)"

# =========================
# Image generation + Cloudinary
# =========================

def _placeholder_png_bytes():
    """Return bytes of a tiny 1x1 transparent PNG as a safe fallback."""
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z/C/HwAGgwJ/"
        "oQvTqQAAAABJRU5ErkJggg=="
    )
    return base64.b64decode(b64)

def openai_generate_image(prompt):
    """Generate an image with OpenAI; handle b64_json or URL responses."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt[:1800],  # keep prompt conservative
        "size": OPENAI_IMAGE_SIZE,
        "n": 1,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    if not data.get("data"):
        raise RuntimeError(f"OpenAI image response missing data: {data}")
    item = data["data"][0]
    if "b64_json" in item:
        return base64.b64decode(item["b64_json"])
    if "url" in item:
        img = requests.get(item["url"], timeout=60)
        img.raise_for_status()
        return img.content
    raise RuntimeError(f"OpenAI image response missing b64_json/url: {data}")

def parse_cloudinary_url():
    """
    CLOUDINARY_URL must be: cloudinary://<api_key>:<api_secret>@<cloud_name>
    """
    conn = os.environ.get("CLOUDINARY_URL", "")
    m = re.match(r"^cloudinary://([^:]+):([^@]+)@([^/]+)", conn)
    if not m:
        raise RuntimeError("CLOUDINARY_URL is missing or invalid")
    api_key, api_secret, cloud_name = m.groups()
    return api_key, api_secret, cloud_name

def upload_to_cloudinary(file_bytes, public_id):
    """
    Signed upload with correct Cloudinary signature:
    signature = sha1("public_id=...&timestamp=...<api_secret>")
    (NOT HMAC.)
    """
    api_key, api_secret, cloud_name = parse_cloudinary_url()
    endpoint = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    ts = str(int(time.time()))
    to_sign = f"public_id={public_id}&timestamp={ts}{api_secret}"
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    files = {"file": ("image.png", file_bytes, "image/png")}
    data = {"api_key": api_key, "timestamp": ts, "signature": signature, "public_id": public_id}

    r = requests.post(endpoint, files=files, data=data, timeout=60)
    r.raise_for_status()
    return f"https://res.cloudinary.com/{cloud_name}/image/upload/f_webp,q_auto/{public_id}.webp"

# =========================
# Post rendering / write
# =========================

def render_body(image_url, first_ref, first_text, gospel_ref, gospel_text):
    parts = [f"Image: {image_url}\n"]
    if first_ref:
        parts.append(f"**First Reading — {first_ref}**\n")
        parts.append((first_text or "").strip() + "\n")
    if gospel_ref:
        parts.append(f"**Gospel — {gospel_ref}**\n")
        parts.append((gospel_text or "").strip() + "\n")
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

    # Try feeds in order: Catholic.org → USCCB primary → USCCB FeedBurner
    first_ref = gospel_ref = None
    src_used = None

    for src in ("catholic.org", "usccb_rss", "feedburner"):
        try:
            if src == "catholic.org":
                feed = fetch_feed(CATHOLIC_ORG_RSS)
            elif src == "usccb_rss":
                feed = fetch_feed(USCCB_RSS_PRIMARY)
            else:
                feed = fetch_feed(USCCB_RSS_FALLBACK)

            entry = pick_today_entry(feed, today) if getattr(feed, "entries", None) else None
            if not entry:
                continue

            fr, gr = extract_refs_from_entry_generic(entry)
            if fr or gr:
                first_ref = _sanitize_ref(fr) if fr else None
                gospel_ref = _sanitize_ref(gr) if gr else None
                src_used = src
                break
        except Exception as e:
            print(f"[debug] feed error ({src}): {e}")

    # Fallback: USCCB HTML page if needed
    if not (first_ref or gospel_ref):
        try:
            html_str = fetch_usccb_daily_page(today)
            fr, gr = extract_refs_from_html(html_str)
            if fr or gr:
                first_ref = _sanitize_ref(fr) if fr else None
                gospel_ref = _sanitize_ref(gr) if gr else None
                src_used = "usccb_html"
        except Exception as e:
            print(f"[debug] HTML fallback error: {e}")

    if not (first_ref or gospel_ref):
        raise RuntimeError("No readings found via Catholic.org RSS, USCCB RSS, or USCCB HTML fallback.")

    print(f"[info] source used: {src_used}, first={first_ref}, gospel={gospel_ref}")

    # Fetch KJV texts (with deuterocanon note)
    first_text = fetch_kjv_text(first_ref) if first_ref else ""
    gospel_text = fetch_kjv_text(gospel_ref) if gospel_ref else ""

    # Generate image (ground on Gospel when present), with graceful fallback
    ref_for_image = gospel_ref or first_ref or "the daily readings"
    prompt = (
        f"Create a devotional image inspired by the Gospel passage {ref_for_image}. "
        f"Focus on symbolism rather than literal depiction. {IMAGE_PROMPT_STYLE}"
    )

    disable_img = os.environ.get("DISABLE_IMAGE_GEN", "").strip() == "1"
    if disable_img:
        print("[info] DISABLE_IMAGE_GEN=1 set; using placeholder image.")
        img_bytes = _placeholder_png_bytes()
    else:
        try:
            img_bytes = openai_generate_image(prompt)
        except requests.HTTPError as e:
            try:
                msg = e.response.json()
            except Exception:
                msg = {"status_code": getattr(e.response, 'status_code', 'n/a'),
                       "text": getattr(e.response, 'text', '')[:300]}
            print(f"[warn] OpenAI image generation failed: {msg}")
            img_bytes = _placeholder_png_bytes()
        except Exception as e:
            print(f"[warn] OpenAI image generation error: {e}")
            img_bytes = _placeholder_png_bytes()

    # Slug/public_id from Gospel (fallback First)
    slug = slug_from_reference(gospel_ref or first_ref or "daily-gospel")
    public_id = f"matthew419/{today.year}/{today.month:02d}/{slug}"
    image_url = upload_to_cloudinary(img_bytes, public_id)

    # Title = Gospel ref preferred
    title = gospel_ref or first_ref or "Daily Readings"

    body = render_body(image_url, first_ref, first_text, gospel_ref, gospel_text)
    md_path = write_post(slug, title=title, body=body, date_iso=today.isoformat())
    print(f"Wrote {md_path}")

if __name__ == "__main__":
    main()
