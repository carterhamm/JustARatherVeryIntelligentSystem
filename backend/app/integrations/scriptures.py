"""
Scripture lookup integration for JARVIS.

Three-tier lookup strategy:
1. api.nephi.org — covers ALL LDS scriptures (Bible, BoM, D&C, PGP) in one call
2. book-of-mormon-api.vercel.app — Book of Mormon specific (random, daily, exact verse)
3. bible-api.com — Bible KJV fallback

All free, no API keys required.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0

# ── Primary: api.nephi.org (all LDS scriptures) ─────────────────────────

_NEPHI_API = "https://api.nephi.org/scriptures/"


async def _lookup_nephi(reference: str) -> dict[str, Any]:
    """Look up any scripture via api.nephi.org.

    Supports Bible (KJV), Book of Mormon, D&C, Pearl of Great Price.
    Accepts standard references: "1 Nephi 3:7", "John 3:16", "D&C 121:7-8",
    "Moses 1:39", "Alma 32:21", etc.
    """
    query = reference.strip().replace(" ", "+")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_NEPHI_API, params={"q": query})
            if resp.status_code != 200:
                return {"error": f"api.nephi.org returned {resp.status_code}"}
            data = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"api.nephi.org request failed: {e}"}

    scriptures = data.get("scriptures", [])
    if not scriptures:
        return {"error": f"No results from api.nephi.org for: '{reference}'"}

    verses = []
    for s in scriptures:
        verses.append({
            "reference": s.get("scripture", ""),
            "book": s.get("book", ""),
            "chapter": s.get("chapter", 0),
            "verse": s.get("verse", 0),
            "text": s.get("text", "").strip(),
        })

    full_text = " ".join(
        f"{v['verse']} {v['text']}" if len(verses) > 1 else v["text"]
        for v in verses
    )

    return {
        "reference": verses[0]["reference"] if len(verses) == 1 else reference,
        "text": full_text,
        "verses": verses,
        "verse_count": len(verses),
        "source": "api.nephi.org",
    }


# ── Secondary: book-of-mormon-api.vercel.app (BoM specific) ─────────────

_BOM_API = "https://book-of-mormon-api.vercel.app"

_BOM_BOOKS: dict[str, str] = {
    "1 nephi": "1nephi", "1 ne": "1nephi", "1ne": "1nephi",
    "2 nephi": "2nephi", "2 ne": "2nephi", "2ne": "2nephi",
    "jacob": "jacob", "enos": "enos", "jarom": "jarom", "omni": "omni",
    "words of mormon": "wordsofmormon", "mosiah": "mosiah",
    "alma": "alma", "helaman": "helaman",
    "3 nephi": "3nephi", "3 ne": "3nephi", "3ne": "3nephi",
    "4 nephi": "4nephi", "4 ne": "4nephi", "4ne": "4nephi",
    "mormon": "mormon", "ether": "ether", "moroni": "moroni",
}


async def _lookup_bom_api(reference: str) -> dict[str, Any]:
    """Fallback: look up Book of Mormon verse via BraydenTW API."""
    ref_lower = reference.lower().strip()
    api_book = None
    chapter = ""
    verse_str = ""

    for alias in sorted(_BOM_BOOKS, key=len, reverse=True):
        if ref_lower.startswith(alias):
            remainder = ref_lower[len(alias):].strip()
            api_book = _BOM_BOOKS[alias]
            parts = remainder.split(":")
            chapter = parts[0].strip()
            if len(parts) > 1:
                verse_str = parts[1].strip()
            break

    if not api_book or not chapter:
        return {"error": f"Could not parse BoM reference: '{reference}'"}

    target_verses = _parse_verse_range(verse_str) if verse_str else None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if target_verses:
                fetched = []
                for vnum in sorted(target_verses):
                    resp = await client.get(f"{_BOM_API}/{api_book}/{chapter}/{vnum}")
                    if resp.status_code == 200:
                        d = resp.json()
                        fetched.append({
                            "verse": d.get("verse", vnum),
                            "text": d.get("text", "").strip(),
                            "reference": d.get("reference", ""),
                        })
                if not fetched:
                    return {"error": f"No verses found: {reference}"}
                full_text = " ".join(f"{v['verse']} {v['text']}" for v in fetched)
                return {
                    "reference": reference,
                    "text": full_text,
                    "verses": fetched,
                    "verse_count": len(fetched),
                    "source": "book-of-mormon-api.vercel.app",
                }
            else:
                # Whole chapter — fetch sequentially until 404
                all_verses = []
                for vnum in range(1, 101):
                    resp = await client.get(f"{_BOM_API}/{api_book}/{chapter}/{vnum}")
                    if resp.status_code != 200:
                        break
                    d = resp.json()
                    text = d.get("text", "").strip()
                    if not text:
                        break
                    all_verses.append({"verse": vnum, "text": text})
                if all_verses:
                    full_text = " ".join(f"{v['verse']} {v['text']}" for v in all_verses)
                    return {
                        "reference": f"{reference} (full chapter)",
                        "text": full_text,
                        "verses": all_verses,
                        "verse_count": len(all_verses),
                        "source": "book-of-mormon-api.vercel.app",
                    }
                return {"error": f"Chapter not found: {reference}"}
    except httpx.HTTPError as e:
        return {"error": f"BoM API error: {e}"}


async def lookup_bom_random(book: str = "", chapter: str = "") -> dict[str, Any]:
    """Get a random Book of Mormon verse."""
    api_book = ""
    if book:
        bl = book.lower().strip()
        for alias in sorted(_BOM_BOOKS, key=len, reverse=True):
            if bl.startswith(alias) or alias.startswith(bl):
                api_book = _BOM_BOOKS[alias]
                break

    if api_book and chapter:
        url = f"{_BOM_API}/random/{api_book}/{chapter}"
    elif api_book:
        url = f"{_BOM_API}/random/{api_book}"
    else:
        url = f"{_BOM_API}/random"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"error": f"BoM random API returned {resp.status_code}"}
            data = resp.json()
        return {
            "reference": data.get("reference", "Unknown"),
            "text": data.get("text", "").strip(),
            "verse": data.get("verse", 0),
            "source": "Book of Mormon",
        }
    except httpx.HTTPError as e:
        return {"error": f"BoM random API error: {e}"}


# ── Tertiary: bible-api.com (Bible KJV fallback) ────────────────────────

_BIBLE_API = "https://bible-api.com"


async def _lookup_bible(reference: str) -> dict[str, Any]:
    """Fallback: look up Bible verse via bible-api.com (KJV)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BIBLE_API}/{reference}?translation=kjv")
            if resp.status_code != 200:
                return {"error": f"Bible API returned {resp.status_code}"}
            data = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"Bible API error: {e}"}

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
        "source": "bible-api.com",
    }


# ── Universal lookup with fallback chain ─────────────────────────────────

async def lookup_scripture(reference: str) -> dict[str, Any]:
    """Universal scripture lookup with three-tier fallback.

    1. api.nephi.org (all scriptures)
    2. book-of-mormon-api.vercel.app (BoM fallback)
    3. bible-api.com (Bible fallback)
    """
    ref = reference.strip()

    # Handle random requests
    if ref.lower().startswith("random"):
        return await lookup_bom_random()

    # Tier 1: api.nephi.org (covers everything)
    result = await _lookup_nephi(ref)
    if not result.get("error"):
        return result

    logger.debug("api.nephi.org failed for '%s': %s", ref, result.get("error"))

    # Tier 2: BoM-specific API (if it looks like a BoM reference)
    ref_lower = ref.lower()
    is_bom = any(ref_lower.startswith(alias) for alias in _BOM_BOOKS)
    if is_bom:
        result = await _lookup_bom_api(ref)
        if not result.get("error"):
            return result
        logger.debug("BoM API failed for '%s': %s", ref, result.get("error"))

    # Tier 3: Bible API fallback
    result = await _lookup_bible(ref)
    if not result.get("error"):
        return result

    # All tiers failed
    return {
        "error": (
            f"Could not find scripture: '{ref}'. "
            "Try: 'John 3:16', '1 Nephi 3:7', 'Alma 32:21', 'D&C 121:7-8', "
            "'Moroni 10:4-5', or 'Moses 1:39'."
        ),
        "reference": ref,
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
