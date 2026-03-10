"""
Scripture lookup integration for JARVIS.

Provides verse lookup for:
- Bible (KJV via bible-api.com — free, no key)
- Book of Mormon, Doctrine & Covenants, Pearl of Great Price
  (via churchofjesuschrist.org public content)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0

# ── Bible (KJV) via bible-api.com ────────────────────────────────────────

_BIBLE_API = "https://bible-api.com"

# Book name normalization for bible-api.com
_BIBLE_BOOKS = {
    "genesis", "exodus", "leviticus", "numbers", "deuteronomy",
    "joshua", "judges", "ruth", "1 samuel", "2 samuel",
    "1 kings", "2 kings", "1 chronicles", "2 chronicles",
    "ezra", "nehemiah", "esther", "job", "psalms", "psalm",
    "proverbs", "ecclesiastes", "song of solomon",
    "isaiah", "jeremiah", "lamentations", "ezekiel", "daniel",
    "hosea", "joel", "amos", "obadiah", "jonah", "micah",
    "nahum", "habakkuk", "zephaniah", "haggai", "zechariah", "malachi",
    "matthew", "mark", "luke", "john", "acts", "romans",
    "1 corinthians", "2 corinthians", "galatians", "ephesians",
    "philippians", "colossians", "1 thessalonians", "2 thessalonians",
    "1 timothy", "2 timothy", "titus", "philemon",
    "hebrews", "james", "1 peter", "2 peter",
    "1 john", "2 john", "3 john", "jude", "revelation",
}

# ── LDS Scripture paths for churchofjesuschrist.org ─────────────────────

_LDS_BOOK_PATHS: dict[str, str] = {
    # Book of Mormon
    "1 nephi": "bofm/1-ne",
    "1 ne": "bofm/1-ne",
    "1ne": "bofm/1-ne",
    "2 nephi": "bofm/2-ne",
    "2 ne": "bofm/2-ne",
    "2ne": "bofm/2-ne",
    "jacob": "bofm/jacob",
    "enos": "bofm/enos",
    "jarom": "bofm/jarom",
    "omni": "bofm/omni",
    "words of mormon": "bofm/w-of-m",
    "mosiah": "bofm/mosiah",
    "alma": "bofm/alma",
    "helaman": "bofm/hel",
    "3 nephi": "bofm/3-ne",
    "3 ne": "bofm/3-ne",
    "3ne": "bofm/3-ne",
    "4 nephi": "bofm/4-ne",
    "4 ne": "bofm/4-ne",
    "4ne": "bofm/4-ne",
    "mormon": "bofm/morm",
    "ether": "bofm/ether",
    "moroni": "bofm/moro",
    # Doctrine and Covenants
    "d&c": "dc-testament/dc",
    "dc": "dc-testament/dc",
    "doctrine and covenants": "dc-testament/dc",
    # Pearl of Great Price
    "moses": "pgp/moses",
    "abraham": "pgp/abr",
    "joseph smith—matthew": "pgp/js-m",
    "js-m": "pgp/js-m",
    "joseph smith—history": "pgp/js-h",
    "js-h": "pgp/js-h",
    "articles of faith": "pgp/a-of-f",
    "a of f": "pgp/a-of-f",
}


def classify_reference(reference: str) -> str:
    """Classify a scripture reference as 'bible', 'lds', or 'unknown'."""
    ref_lower = reference.lower().strip()

    # Check LDS books first (more specific)
    for alias in _LDS_BOOK_PATHS:
        if ref_lower.startswith(alias):
            return "lds"

    # Check Bible books
    for book in _BIBLE_BOOKS:
        if ref_lower.startswith(book):
            return "bible"

    return "unknown"


async def lookup_bible(reference: str) -> dict[str, Any]:
    """Look up a Bible verse/passage via bible-api.com (KJV)."""
    # bible-api.com uses format like "john 3:16" or "romans 8:28-30"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BIBLE_API}/{reference}?translation=kjv")
        if resp.status_code != 200:
            return {"error": f"Bible API returned {resp.status_code}", "reference": reference}
        data = resp.json()

    if "error" in data:
        return {"error": data["error"], "reference": reference}

    verses = []
    for v in data.get("verses", []):
        verses.append({
            "book": v.get("book_name", ""),
            "chapter": v.get("chapter", 0),
            "verse": v.get("verse", 0),
            "text": v.get("text", "").strip(),
        })

    return {
        "reference": data.get("reference", reference),
        "translation": "KJV",
        "text": data.get("text", "").strip(),
        "verses": verses,
        "verse_count": data.get("verse_count", len(verses)),
    }


async def lookup_lds(reference: str) -> dict[str, Any]:
    """Look up an LDS scripture (Book of Mormon, D&C, Pearl of Great Price).

    Fetches from churchofjesuschrist.org and extracts verse text.
    """
    ref_lower = reference.lower().strip()
    book_path = None
    chapter = ""
    verses_range = ""

    # Parse reference: e.g. "1 Nephi 3:7", "Alma 32:21", "D&C 121:7-8"
    for alias, path in sorted(_LDS_BOOK_PATHS.items(), key=lambda x: -len(x[0])):
        if ref_lower.startswith(alias):
            remainder = ref_lower[len(alias):].strip()
            book_path = path
            # Parse chapter:verse(s)
            parts = remainder.split(":")
            chapter = parts[0].strip() if parts else ""
            if len(parts) > 1:
                verses_range = parts[1].strip()
            break

    if not book_path or not chapter:
        return {"error": f"Could not parse LDS scripture reference: '{reference}'"}

    url = f"https://www.churchofjesuschrist.org/study/scriptures/{book_path}/{chapter}?lang=eng"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "JARVIS/1.0"})
            if resp.status_code != 200:
                return {
                    "error": f"Church website returned {resp.status_code}",
                    "reference": reference,
                    "url": url,
                }

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract verses from the page
        verse_elements = soup.find_all("p", class_=re.compile(r"verse"))
        if not verse_elements:
            # Try alternate selector
            verse_elements = soup.find_all(attrs={"data-aid": True})

        extracted = []
        target_verses = _parse_verse_range(verses_range) if verses_range else None

        for el in verse_elements:
            # Get verse number from the element
            verse_num_el = el.find("span", class_=re.compile(r"verse-number"))
            if verse_num_el:
                try:
                    vnum = int(verse_num_el.get_text(strip=True).rstrip("."))
                except (ValueError, TypeError):
                    continue

                if target_verses and vnum not in target_verses:
                    continue

                # Get verse text (exclude the verse number span)
                verse_num_el.decompose()
                text = el.get_text(strip=True)
                extracted.append({"verse": vnum, "text": text})

        if not extracted:
            # Fallback: return the URL for manual lookup
            return {
                "reference": reference,
                "text": f"Verse text could not be extracted automatically.",
                "url": url,
                "source": "The Church of Jesus Christ of Latter-day Saints",
            }

        full_text = " ".join(f"{v['verse']} {v['text']}" for v in extracted)
        display_ref = reference.title() if not any(c.isupper() for c in reference[1:]) else reference

        return {
            "reference": display_ref,
            "text": full_text,
            "verses": extracted,
            "verse_count": len(extracted),
            "url": url,
            "source": "The Church of Jesus Christ of Latter-day Saints",
        }

    except httpx.HTTPError as e:
        return {"error": f"HTTP error fetching scripture: {e}", "reference": reference, "url": url}


async def lookup_scripture(reference: str) -> dict[str, Any]:
    """Universal scripture lookup — auto-detects Bible vs LDS scriptures."""
    kind = classify_reference(reference)

    if kind == "bible":
        return await lookup_bible(reference)
    elif kind == "lds":
        return await lookup_lds(reference)
    else:
        # Try Bible first, then LDS
        result = await lookup_bible(reference)
        if not result.get("error"):
            return result
        return {
            "error": (
                f"Could not identify scripture reference: '{reference}'. "
                "Try a specific format like 'John 3:16', '1 Nephi 3:7', or 'D&C 121:7-8'."
            ),
            "reference": reference,
        }


def _parse_verse_range(verses_str: str) -> set[int]:
    """Parse verse range like '7', '7-10', '1,3,5-8' into a set of ints."""
    result = set()
    for part in verses_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                result.update(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                pass
        else:
            try:
                result.add(int(part))
            except ValueError:
                pass
    return result
