 #!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
daily.py
Generates a Daily Post using pre-parsed readings from scripts/readings.tsv
(chronological TSV produced by your PDF parser).

- Looks up today's date (America/New_York) in readings.tsv
- Builds a Markdown post at content/post/<slug>.md
- Uploads the generated image to Cloudinary with overwrite + cache-bust
- Adds image URL to front matter (image:)
- Runs `hugo --minify` to build the site

Expected TSV columns (tab-separated, with header):
date    dow     title   first   psalm   second  alleluia    gospel  source_pdf
"""

import os
import re
import time
import base64
import hashlib
import datetime
import subprocess
from pathlib import Path
from typing import Dict, Optional

import requests
import frontmatter
from dateutil import tz

# =========================
# Paths & Config
# =========================

ROOT = Path(__file__).resolve().parent.parent            # repo root
SCRIPTS_DIR = Path(__file__).resolve().parent            # scripts/
CONTENT_DIR = ROOT / "content" / "post"                  # Hugo posts
TSV_PATH = SCRIPTS_DIR / "readings.tsv"                  # placed next to this script

CHATGPT_RESPONSE = """
(Add your reflection here. You can replace this block with an actual generated response.)
""".strip()

# =========================
# Utilities
# =========================

def today_local_date() -> datetime.date:
    tz_local = tz.gettz(os.environ.get("TZ", "America/New_York"))
    return datetime.datetime.now(tz_local).date()

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[—–−]", "-", s)
    s = re.sub(r"[^a-z0-9\-/ _:]+", "", s)
    s = s.replace("/", "-").replace(":", "_")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")

def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

# =========================
# TSV Reading
# =========================

def load_readings_tsv(tsv_path: Path) -> Dict[str, Dict[str, str]]:
    """
    Load readings.tsv into a dict keyed by YYYY-MM-DD.
    """
    if not tsv_path.exists():
        raise FileNotFoundError(f"Missing readings file: {tsv_path}")

    with tsv_path.open("r", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]

    if not lines:
        raise RuntimeError("readings.tsv is empty.")

    header = lines[0].split("\t")
    indexes = {name: idx for idx, name in enumerate(header)}
    required = ["date", "title", "first", "psalm", "second", "alleluia", "gospel", "dow"]
    for r in required:
        if r not in indexes:
            raise RuntimeError(f"TSV missing required column: {r}")

    rows = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        # Guard against ragged lines
        parts += [""] * (len(header) - len(parts))
        rec = {name: norm_spaces(parts[indexes[name]]) for name in header if name in indexes}
        rows[rec["date"]] = rec
    return rows

def get_today_record(tsv_dict: Dict[str, Dict[str, str]], d: datetime.date) -> Optional[Dict[str, str]]:
    key = d.isoformat()
    return tsv_dict.get(key)

# =========================
# Image generation (placeholder)
# =========================

def generate_image_for_ref(ref: str) -> bytes:
    """
    Stub: replace with your real image generation logic.
    Returns PNG bytes (currently a 1x1 pixel placeholder).
    """
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
    )
    return tiny_png

# =========================
# Cloudinary upload (cache-busting)
# =========================

def parse_cloudinary_env():
    """
    Support either CLOUDINARY_URL or discrete pieces.
    CLOUDINARY_URL format: cloudinary://<API_KEY>:<API_SECRET>@<CLOUD_NAME>
    """
    url = os.environ.get("CLOUDINARY_URL")
    if url:
        m = re.match(r"^cloudinary://([^:]+):([^@]+)@([^/]+)", url.strip())
        if not m:
            raise RuntimeError("CLOUDINARY_URL is malformed.")
        return m.group(1), m.group(2), m.group(3)
    # Fallback to discrete env vars
    return (
        os.environ["CLOUDINARY_API_KEY"],
        os.environ["CLOUDINARY_API_SECRET"],
        os.environ["CLOUDINARY_CLOUD_NAME"],
    )

def upload_to_cloudinary(file_bytes: bytes, public_id: str) -> str:
    """
    Uploads bytes to Cloudinary with overwrite + invalidate and returns
    a VERSIONED URL so CDN shows the fresh image.
    """
    api_key, api_secret, cloud_name = parse_cloudinary_env()
    endpoint = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    ts = str(int(time.time()))
    # Sign exactly the params sent, sorted alphabetically:
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
    return f"{base}/v{version}/{public_id}.webp" if version is not None else f"{base}/{public_id}.webp"

# =========================
# Content rendering
# =========================

def render_body(cal_title: str, first_ref: str, psalm_ref: str,
                second_ref: str, alleluia_ref: str, gospel_ref: str,
                first_text: str, psalm_text: str, second_text: str,
                alleluia_text: str, gospel_text: str) -> str:
    """
    Compose Markdown body. Image is set in front matter (not in body).
    """
    parts = []
    if cal_title:
        parts.append(f"**{cal_title}**\n")

    if first_ref:
        parts.append(f"**First Reading — {first_ref}**\n")
        parts.append((first_text or "").strip() + "\n")

    if psalm_ref:
        parts.append(f"**Responsorial Psalm — {psalm_ref}**\n")
        parts.append((psalm_text or "").strip() + "\n")

    if second_ref:
        parts.append(f"**Second Reading — {second_ref}**\n")
        parts.append((second_text or "").strip() + "\n")

    if alleluia_ref:
        parts.append(f"**Alleluia — {alleluia_ref}**\n")
        parts.append((alleluia_text or "").strip() + "\n")

    if gospel_ref:
        parts.append(f"**Gospel — {gospel_ref}**\n")
        parts.append((gospel_text or "").strip() + "\n")

    parts.append("### ChatGPT Response\n")
    parts.append(CHATGPT_RESPONSE.strip())

    return "\n".join(parts).strip() + "\n"

# Stub scripture fetchers; keep placeholders for now
def fetch_text_for_ref(ref: str) -> str:
    if not ref:
        return ""
    return f"(Text for {ref} would be inserted here.)"

# =========================
# Post writing
# =========================

def write_post(slug: str, title: str, body: str, date_iso: str, image_url: str) -> Path:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = CONTENT_DIR / f"{slug}.md"

    if md_path.exists():
        existing = frontmatter.load(md_path)
        fm = dict(existing.metadata)
        fm.setdefault("title", title)
        fm.setdefault("date", date_iso)
        fm["draft"] = False
        fm["image"] = image_url
        post = frontmatter.Post(body, **fm)
    else:
        post = frontmatter.Post(body, **{
            "title": title,
            "date": date_iso,
            "draft": False,
            "image": image_url,
        })

    md_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return md_path

# =========================
# Main
# =========================

def main():
    # Load readings table
    table = load_readings_tsv(TSV_PATH)
    today = today_local_date()
    rec = get_today_record(table, today)
    if not rec:
        raise RuntimeError(f"No entry for {today.isoformat()} in {TSV_PATH.name}")

    cal_title   = rec.get("title", "")
    first_ref   = rec.get("first", "")
    psalm_ref   = rec.get("psalm", "")
    second_ref  = rec.get("second", "")
    alleluia_ref= rec.get("alleluia", "")
    gospel_ref  = rec.get("gospel", "")

    # Choose title and slug
    chosen_ref_for_title = gospel_ref or first_ref or cal_title or "Daily Readings"
    slug = slugify(gospel_ref or first_ref or cal_title or today.isoformat())

    # Fetch texts (placeholder; replace with real Bible API if desired)
    first_text    = fetch_text_for_ref(first_ref)
    psalm_text    = fetch_text_for_ref(psalm_ref)
    second_text   = fetch_text_for_ref(second_ref)
    alleluia_text = fetch_text_for_ref(alleluia_ref)
    gospel_text   = fetch_text_for_ref(gospel_ref)

    # Generate/upload image (ground it on the Gospel if present)
    ref_for_image = gospel_ref or first_ref or cal_title or today.isoformat()
    img_bytes = generate_image_for_ref(ref_for_image)
    public_id = f"matthew419/{today.year}/{today.month:02d}/{slug}"
    image_url = upload_to_cloudinary(img_bytes, public_id)

    # Build body
    body = render_body(
        cal_title, first_ref, psalm_ref, second_ref, alleluia_ref, gospel_ref,
        first_text, psalm_text, second_text, alleluia_text, gospel_text
    )

    # Write/overwrite post
    md_path = write_post(slug, chosen_ref_for_title, body, today.isoformat(), image_url)
    print(f"[info] Wrote {md_path}")

    # Build site with Hugo
    try:
        subprocess.run(["hugo", "--minify"], check=True, cwd=str(ROOT))
        print("[info] Hugo site built successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[error] Hugo build failed: {e}")
        raise

if __name__ == "__main__":
    main()
