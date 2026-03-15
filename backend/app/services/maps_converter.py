"""
Google Maps URL and Plus Code to Apple Maps converter for JARVIS.

Converts various Google Maps URL formats and Open Location Codes (Plus Codes)
into Apple Maps deep links that open natively on iOS/macOS.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, quote_plus, urlparse

logger = logging.getLogger("jarvis.maps_converter")


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════


def coordinates_to_apple_maps_url(
    lat: float,
    lng: float,
    name: str = "",
    directions: bool = False,
) -> str:
    """Generate an Apple Maps deep link from coordinates.

    Args:
        lat: Latitude.
        lng: Longitude.
        name: Optional place name shown on the pin.
        directions: If True, generate a driving directions link.

    Returns:
        Apple Maps URL string.
    """
    if directions:
        url = f"http://maps.apple.com/?daddr={lat},{lng}&dirflg=d"
        if name:
            url += f"&q={quote_plus(name)}"
        return url

    url = f"http://maps.apple.com/?ll={lat},{lng}"
    if name:
        url += f"&q={quote_plus(name)}"
    return url


async def google_maps_url_to_apple(url: str) -> str:
    """Convert a Google Maps URL to an Apple Maps deep link.

    Supports the following Google Maps URL formats:
      - https://www.google.com/maps/place/NAME/@LAT,LNG,ZOOM
      - https://www.google.com/maps/dir/ORIGIN/DEST
      - https://www.google.com/maps?q=LAT,LNG
      - https://goo.gl/maps/SHORTCODE  (resolves redirect)
      - https://maps.app.goo.gl/SHORTCODE  (resolves redirect)

    Args:
        url: A Google Maps URL in any supported format.

    Returns:
        An Apple Maps deep link URL, or an error message string.
    """
    url = url.strip()
    if not url:
        return "Error: empty URL provided."

    # Step 1: Resolve short URLs to their full form
    if _is_short_url(url):
        resolved = await _resolve_short_url(url)
        if resolved:
            url = resolved
        else:
            return f"Error: could not resolve short URL: {url}"

    parsed = urlparse(url)

    # Format: /maps?q=LAT,LNG or /maps?q=QUERY
    if parsed.query:
        qs = parse_qs(parsed.query)
        q_val = qs.get("q", qs.get("query", [""]))[0]
        if q_val:
            coords = _extract_coords_from_string(q_val)
            if coords:
                return coordinates_to_apple_maps_url(coords[0], coords[1])
            # Text query — pass through as search
            return f"http://maps.apple.com/?q={quote_plus(q_val)}"

    path = parsed.path

    # Format: /maps/place/NAME/@LAT,LNG,ZOOMz
    place_match = re.search(
        r"/maps/place/([^/]+)/@(-?[\d.]+),(-?[\d.]+)", path
    )
    if place_match:
        name = place_match.group(1).replace("+", " ")
        lat = float(place_match.group(2))
        lng = float(place_match.group(3))
        return coordinates_to_apple_maps_url(lat, lng, name=name)

    # Format: /maps/@LAT,LNG,ZOOMz (no place name)
    at_match = re.search(r"/maps/@(-?[\d.]+),(-?[\d.]+)", path)
    if at_match:
        lat = float(at_match.group(1))
        lng = float(at_match.group(2))
        return coordinates_to_apple_maps_url(lat, lng)

    # Format: /maps/dir/ORIGIN/DEST
    dir_match = re.search(r"/maps/dir/([^/]+)/([^/]+)", path)
    if dir_match:
        dest = dir_match.group(2).replace("+", " ")
        coords = _extract_coords_from_string(dest)
        if coords:
            return coordinates_to_apple_maps_url(
                coords[0], coords[1], directions=True
            )
        return f"http://maps.apple.com/?daddr={quote_plus(dest)}&dirflg=d"

    # Last resort: scan the entire URL for a coordinate pair
    coords = _extract_coords_from_string(url)
    if coords:
        return coordinates_to_apple_maps_url(coords[0], coords[1])

    return f"Error: could not parse Google Maps URL: {url}"


def plus_code_to_coordinates(plus_code: str) -> tuple[float, float]:
    """Decode an Open Location Code (Plus Code) to latitude and longitude.

    Implements the OLC decoding algorithm. Plus Codes use a base-20
    encoding over a progressively refined grid.

    Args:
        plus_code: A full Plus Code (e.g. "85GQ2C22+2V").

    Returns:
        (latitude, longitude) tuple.

    Raises:
        ValueError: If the Plus Code is invalid.
    """
    code = plus_code.strip().upper().replace(" ", "")

    # Validate
    if "+" not in code:
        raise ValueError(f"Invalid Plus Code (no '+' separator): {code}")

    # OLC character set
    alphabet = "23456789CFGHJMPQRVWX"
    separator_pos = 8

    # Remove the separator
    clean = code.replace("+", "")

    if len(clean) < 2:
        raise ValueError(f"Plus Code too short: {code}")

    # Validate characters
    for ch in clean:
        if ch not in alphabet and ch != "0":
            raise ValueError(f"Invalid character '{ch}' in Plus Code: {code}")

    # Pad with 'A' (index 0 placeholder) to at least 8 chars for decoding
    # (short codes need a reference location; we only handle full codes)
    if code.index("+") < separator_pos:
        raise ValueError(
            f"Short Plus Codes require a reference location. "
            f"Provide a full code (e.g. 85GQ2C22+2V): {code}"
        )

    # Decode pairs: each pair of characters encodes lat and lng
    # Resolution decreases by 20x for each pair
    lat = 0.0
    lng = 0.0

    # First 5 pairs (10 chars before +, positions 0-9)
    pair_resolutions = [20.0, 1.0, 0.05, 0.0025, 0.000125]

    i = 0
    pair_idx = 0
    while i < len(clean) and pair_idx < 5:
        lat_ch = clean[i] if i < len(clean) else "2"
        lng_ch = clean[i + 1] if i + 1 < len(clean) else "2"

        lat_val = alphabet.index(lat_ch) if lat_ch in alphabet else 0
        lng_val = alphabet.index(lng_ch) if lng_ch in alphabet else 0

        lat += lat_val * pair_resolutions[pair_idx]
        lng += lng_val * pair_resolutions[pair_idx]

        i += 2
        pair_idx += 1

    # After the 5th pair, remaining chars refine within a 4x5 grid
    # Each subsequent character refines in a 4-row x 5-col grid
    if i < len(clean):
        lat_res = pair_resolutions[-1]
        lng_res = pair_resolutions[-1]
        for j in range(i, len(clean)):
            ch = clean[j]
            if ch not in alphabet:
                break
            val = alphabet.index(ch)
            row = val // 4
            col = val % 4
            lat_res /= 5.0
            lng_res /= 4.0
            lat += row * lat_res
            lng += col * lng_res

    # OLC grid starts at -90 lat, -180 lng
    lat -= 90.0
    lng -= 180.0

    return (round(lat, 8), round(lng, 8))


def plus_code_to_apple_maps(plus_code: str) -> str:
    """Convert a Plus Code to an Apple Maps URL.

    Args:
        plus_code: A full Open Location Code (e.g. "85GQ2C22+2V").

    Returns:
        Apple Maps URL string, or error message.
    """
    try:
        lat, lng = plus_code_to_coordinates(plus_code)
        return coordinates_to_apple_maps_url(lat, lng, name=plus_code)
    except ValueError as exc:
        return f"Error: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


def _is_short_url(url: str) -> bool:
    """Check if URL is a Google Maps short link that needs redirect resolution."""
    return bool(
        re.match(r"https?://(goo\.gl/maps/|maps\.app\.goo\.gl/)", url)
    )


async def _resolve_short_url(url: str) -> Optional[str]:
    """Resolve a shortened Google Maps URL by following redirects.

    Uses httpx to follow the redirect chain and return the final URL.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10.0
        ) as client:
            resp = await client.head(url)
            final_url = str(resp.url)
            if "google.com/maps" in final_url:
                return final_url
            # Try GET if HEAD didn't resolve properly
            resp = await client.get(url)
            final_url = str(resp.url)
            if "google.com/maps" in final_url:
                return final_url
            return final_url
    except Exception as exc:
        logger.warning("Failed to resolve short URL %s: %s", url, exc)
        return None


def _extract_coords_from_string(s: str) -> Optional[tuple[float, float]]:
    """Extract a lat,lng pair from a string.

    Matches patterns like "40.2968,-111.6946" or "40.2968, -111.6946".
    """
    match = re.search(r"(-?[\d]{1,3}\.[\d]+)\s*,\s*(-?[\d]{1,3}\.[\d]+)", s)
    if match:
        lat = float(match.group(1))
        lng = float(match.group(2))
        # Sanity check: valid lat/lng ranges
        if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
            return (lat, lng)
    return None
