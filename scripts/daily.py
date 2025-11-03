#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import base64
import hashlib
import datetime
import subprocess
import html as htmlmod
from pathlib import Path

import requests
import frontmatter
import feedparser
from dateutil import tz

# =========================
# Config
# =========================

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "post"

USCCB_RSS_PRIMARY = "https://bible.usccb.org/daily-bible-reading?format=rss"
USCCB_RSS_FALLBACK = "https://feeds.feedburner.com/USCCB-DailyReadings"
CATHOLIC_ORG_RSS = "https://www.catholic.org/rss/daily_reading.php"

CHATGPT_RESPONSE = """
(Your canned reflection/response goes here.)
""".strip()

# =========================
# Helpers
# =========================

def today_local_date():
    # America/New_York assumed; if TZ is set in env, this still works fine.
    tz_local = tz.gettz(os.environ.get("TZ", "America/New_York"))
    return datetime.datetime.now(tz_local).date()

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"—|–|−", "-", s)
    s = re.sub(r"[^a-z0-9\-/ ]+", "", s)
    s = s.replace("/", "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")

def _sanitize_ref(ref: str) -> str:
    # Normalize spacing like "Luke 14:12-14" and strip weird entities
    ref = htmlmod.unescape(ref or "")
    ref = re.sub(r"\s+", " ", ref).strip(" –—\u00a0")
    # Drop ornaments like “Daily Readings for Monday, March 4, 2024”
    ref = re.sub(r"^Daily Readings.*?:\s*", "", ref, flags=re.I)
    return ref

def slug_from_reference(ref: str) -> str:
    # e.g., "Luke 14:12-14" -> "luke14_12-14"
    core = re.sub(r"[^A-Za-z0-9:]", "", ref)
    core = core.replace(":", "_")
    return slugify(core or "daily-gospel")

def parse_cloudinary_url():
    """
    Expecting CLOUDINARY_URL or the discrete parts:
      CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    """
    url = os.environ.get("CLOUDINARY_URL")
    if url:
        # cloudinary://<api_key>:<api_secret>@<cloud_name>
        m = re.match(r"^cloudinary://([^:]+):([^@]+)@([^/]+)", url)
        if not m:
            raise RuntimeError("CLOUDINARY_URL is malformed.")
        api_key, api_secret, cloud_name = m.group(1), m.group(2), m.group(3)
        return api_key, api_secret, cloud_name
    return (
        os.environ["CLOUDINARY_API_KEY"],
        os.environ["CLOUDINARY_API_SECRET"],
        os.environ["CLOUDINARY_CLOUD_NAME"],
    )

def fetch_feed(url):
    # Cloudflare/Feedburner sometimes fusses about UA
    parsed = feedparser.parse(url, request_headers={"User-Agent": "daily/1.0"})
    if parsed.bozo and parsed.bozo_exception:
        raise RuntimeError(f"Feed parse error: {parsed.bozo_exception}")
    return parsed

def fetch_usccb_daily_page(d):
    # Fetch the HTML daily page for fallback scraping
    # Example: https://bible.usccb.org/bible/readings/110325.cfm  (mmddyy)
    mmddyy = d.strftime("%m%d%y")
    url = f"https://bible.usccb.org/bible/readings/{mmddyy}.cfm"
    r = requests.get(url, timeout=30, headers={"User-Agent": "daily/1.0"})
    r.raise_for_status()
    return r.text

def extract_refs_from_entry_generic(entry):
    """
    Try to pull First/Gospel from a generic RSS item title/summary.
    Returns (first_ref, gospel_ref) or (None, None).
    """
    title = entry.get("title", "") or ""
    summary = entry.get("summary", "") or ""

    # Look in title first
    refs = re.findall(r"(?:First Reading|Gospel)[:\s—-]+([^<]+)", title, flags=re.I)
    first_ref = gospel_ref = None

    if refs:
        # Heuristic: if 2, assume first is First, second is Gospel
        if len(refs) >= 2:
            first_ref = refs[0].strip()
            gospel_ref = refs[1].strip()
        else:
            # might only have Gospel
            if "gospel" in title.lower():
                gospel_ref = refs[0].strip()
            else:
                first_ref = refs[0].strip()

    if not (first_ref or gospel_ref):
        # Try summary fallback
        # e.g., <p>First Reading: Wisdom 2:1a,12-22</p> <p>Gospel: Luke 17:7-10</p>
        m_first = re.search(r"First Reading[:\s—-]+([^<]+)", summary, flags=re.I)
        m_gosp = re.search(r"Gospel[:\s—-]+([^<]+)", summary, flags=re.I)
        first_ref = m_first.group(1).strip() if m_first else None
        gospel_ref = m_gosp.group(1).strip() if m_gosp else None

    return first_ref, gospel_ref

def extract_refs_from_html(html_str):
    """
    USCCB HTML fallback parse.
    """
    first_ref = gospel_ref = None
    # Non-robust but usually good enough selectors via regex
    # First reading block
    m_first = re.search(r'first-reading.*?<h3[^>]*>(.*?)</h3>', html_str, flags=re.I | re.S)
    if m_first:
        first_ref = _sanitize_ref(re.sub("<[^<]+?>", "", m_first.group(1)))

    # Gospel block
    m_gosp = re.search(r'gospel.*?<h3[^>]*>(.*?)</h3>', html_str, flags=re.I | re.S)
    if m_gosp:
        gospel_ref = _sanitize_ref(re.sub("<[^<]+?>", "", m_gosp.group(1)))

    return first_ref, gospel_ref

# --- Image generation ---

def generate_image_for_ref(ref: str) -> bytes:
    """
    Placeholder: assume another service created an image and we have the bytes.
    In your workflow, this likely calls your image API and returns PNG bytes.
    """
    # Replace with your actual generation call or file read.
    # For the example, return a tiny 1x1 PNG so upload path stays exercised.
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
    )
    return tiny_png

def upload_to_cloudinary(file_bytes, public_id):
    """
    Uploads bytes to Cloudinary with overwrite + cache invalidation and returns
    a *versioned* URL so the CDN won't serve stale images.
    """
    api_key, api_secret, cloud_name = parse_cloudinary_url()
    endpoint = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    ts = str(int(time.time()))
    # Sign exactly the params we're sending (alphabetically sorted)
    # format=webp&invalidate=true&overwrite=true&public_id=...&timestamp=... + api_secret
    to_sign = f"format=webp&invalidate=true&overwrite=true&public_id={public_id}&timestamp={ts}{api_secret}"
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    files = {"file": ("image.png", file_bytes, "image/png")}
    data = {
        "api_key": api_key,
        "timestamp": ts,
        "signature": signature,
        "public_id": public_id,
        "overwrite": "true",
        "invalidate": "true",
        "format": "webp",
    }

    r = requests.post(endpoint, files=files, data=data, timeout=60)
    r.raise_for_status()
    info = r.json()
    version = info.get("version")
    base = f"https://res.cloudinary.com/{cloud_name}/image/upload/f_webp,q_auto"
    if version is not None:
        return f"{base}/v{version}/{public_id}.webp"
    return f"{base}/{public_id}.webp"

# --- Content rendering ---

def render_body(image_url, first_ref, first_text, gospel_ref, gospel_text):
    parts = []
    if first_ref:
        parts.append(f"**First Reading — {first_ref}**\n")
        parts.append((first_text or "").strip() + "\n")
    if gospel_ref:
        parts.append(f"**Gospel — {gospel_ref}**\n")
        parts.append((gospel_text or "").strip() + "\n")
    parts.append("### ChatGPT Response\n")
    parts.append(CHATGPT_RESPONSE.strip())
    return "\n".join(parts).strip() + "\n"

# --- Bible text fetch ---

def fetch_kjv_text(ref: str) -> str:
    """
    Replace with your preferred API. This is a simple placeholder that returns
    the reference line only.
    """
    return f"(KJV text for {ref} would be inserted here.)"

# =========================
# Reference normalization
# =========================

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
    "Ezr": "Ezra", "Ezra": "Ezra",
    "Neh": "Nehemiah", "Nehemiah": "Nehemiah",
    "Tob": "Tobit", "Tb": "Tobit", "Tobit": "Tobit",
    "Jdt": "Judith", "Judith": "Judith",
    "Est": "Esther", "Esther": "Esther",
    "1 Macc": "1 Maccabees", "2 Macc": "2 Maccabees",
    "Job": "Job",
    "Ps": "Psalms", "Psalms": "Psalms",
    "Prv": "Proverbs", "Prov": "Proverbs", "Proverbs": "Proverbs",
    "Eccl": "Ecclesiastes", "Qoheleth": "Ecclesiastes",
    "Wis": "Wisdom", "Wisdom": "Wisdom",
    "Sir": "Sirach", "Ecclesiasticus": "Sirach",
    "Is": "Isaiah", "Isa": "Isaiah", "Isaiah": "Isaiah",
    "Jer": "Jeremiah", "Jeremiah": "Jeremiah",
    "Lam": "Lamentations",
    "Bar": "Baruch",
    "Ez": "Ezekiel", "Ezek": "Ezekiel", "Ezekiel": "Ezekiel",
    "Dan": "Daniel", "Dn": "Daniel", "Daniel": "Daniel",
    "Hos": "Hosea", "Hosea": "Hosea",
    "Joel": "Joel",
    "Am": "Amos", "Amos": "Amos",
    "Ob": "Obadiah",
    "Jon": "Jonah",
    "Mic": "Micah",
    "Nah": "Nahum",
    "Hab": "Habakkuk",
    "Zeph": "Zephaniah",
    "Hag": "Haggai",
    "Zech": "Zechariah",
    "Mal": "Malachi",

    # NT
    "Mt": "Matthew", "Matt": "Matthew", "Matthew": "Matthew",
    "Mk": "Mark", "Mark": "Mark",
    "Lk": "Luke", "Luke": "Luke",
    "Jn": "John", "John": "John",
    "Acts": "Acts",
    "Rom": "Romans", "Romans": "Romans",
    "1 Cor": "1 Corinthians", "2 Cor": "2 Corinthians",
    "Gal": "Galatians",
    "Eph": "Ephesians",
    "Phil": "Philippians",
    "Col": "Colossians",
    "1 Thes": "1 Thessalonians", "2 Thes": "2 Thessalonians",
    "1 Tim": "1 Timothy", "2 Tim": "2 Timothy",
    "Titus": "Titus",
    "Phlm": "Philemon", "Philemon": "Philemon",
    "Heb": "Hebrews",
    "Jas": "James",
    "1 Pt": "1 Peter", "2 Pt": "2 Peter",
    "1 Jn": "1 John", "2 Jn": "2 John", "3 Jn": "3 John",
    "Jude": "Jude",
    "Rev": "Revelation", "Revelation": "Revelation",
}

def normalize_book_name(name: str) -> str:
    return BOOK_MAP.get(name.strip(), name.strip())

def normalize_reference(ref: str) -> str:
    """
    From inputs like 'Lk 14:12-14' → 'Luke 14:12-14'
    """
    # Split on first space between book and chapter
    m = re.match(r"^([1-3]?\s?[A-Za-z. ]+)\s+([0-9].*)$", ref.strip())
    if not m:
        return ref.strip()
    book, rest = m.group(1), m.group(2)
    return f"{normalize_book_name(book)} {rest}"

# =========================
# Writing
# =========================

def write_post(slug, title, body, date_iso):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = CONTENT_DIR / f"{slug}.md"
    if md_path.exists():
        existing = frontmatter.load(md_path)
        fm = dict(existing.metadata)
        fm.setdefault("title", title)
        fm.setdefault("date", date_iso)
        fm["draft"] = False
        # Overwrite body by default; change to existing.content to preserve manual edits
        post = frontmatter.Post(body, **fm)
    else:
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

            # Iterate entries newest-first
            for entry in feed.entries:
                fr, gr = extract_refs_from_entry_generic(entry)
                if fr or gr:
                    first_ref = _sanitize_ref(fr) if fr else None
                    gospel_ref = _sanitize_ref(gr) if gr else None
                    src_used = src
                    break
            if first_ref or gospel_ref:
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
    ref_for_image = gospel_ref or first_ref
    img_bytes = generate_image_for_ref(ref_for_image) if ref_for_image else generate_image_for_ref("Psalm 23")

    # Slug/public_id from Gospel (fallback First)
    slug = slug_from_reference(gospel_ref or first_ref or "daily-gospel")
    public_id = f"matthew419/{today.year}/{today.month:02d}/{slug}"
    image_url = upload_to_cloudinary(img_bytes, public_id)

    # Title = Gospel ref preferred
    title = gospel_ref or first_ref or "Daily Readings"

    body = render_body(image_url, first_ref, first_text, gospel_ref, gospel_text)
    md_path = write_post(slug, title=title, body=body, date_iso=today.isoformat())
    print(f"Wrote {md_path}")

    # Attach image to front matter for Hugo theme compatibility
    post = frontmatter.load(md_path)
    post.metadata["image"] = image_url
    md_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    # --- Build Hugo site ---
    try:
        subprocess.run(["hugo", "--minify"], check=True, cwd=str(ROOT))
        print("[info] Hugo site built successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[error] Hugo build failed: {e}")

if __name__ == "__main__":
    main()
