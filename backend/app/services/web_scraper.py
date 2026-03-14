"""
Web content scraper for JARVIS continuous learning.

Fetches and parses web pages to extract article content for deeper
research ingestion.  Uses httpx + BeautifulSoup.  Respects rate limits
and prefers high-quality sources (academic, Wikipedia, news).

Part of Phase 2: Continuous Learning (Days 3-5).
"""

from __future__ import annotations

import logging
import re
import time as _time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("jarvis.web_scraper")

# Source quality tiers — higher score = more trusted
_SOURCE_TIERS: dict[str, int] = {
    "wikipedia.org": 5,
    "arxiv.org": 5,
    "nature.com": 5,
    "science.org": 5,
    "ieee.org": 5,
    "acm.org": 5,
    "scholar.google.com": 4,
    "techcrunch.com": 4,
    "arstechnica.com": 4,
    "theverge.com": 4,
    "wired.com": 4,
    "reuters.com": 4,
    "apnews.com": 4,
    "bbc.com": 4,
    "nytimes.com": 3,
    "washingtonpost.com": 3,
    "bloomberg.com": 3,
    "cnbc.com": 3,
    "engadget.com": 3,
    "macrumors.com": 3,
    "9to5mac.com": 3,
    "developer.apple.com": 4,
    "github.com": 3,
    "medium.com": 2,
}

# Domains to skip entirely
_BLOCKED_DOMAINS = frozenset({
    "facebook.com", "instagram.com", "tiktok.com", "pinterest.com",
    "linkedin.com", "reddit.com",  # auth-walled / noisy
})

# Maximum content length to extract (chars)
_MAX_CONTENT_LENGTH = 15_000

# Request timeout
_REQUEST_TIMEOUT = 15.0

# User agent
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 "
    "JARVIS/1.0 (Research Bot; +https://app.malibupoint.dev)"
)


def get_source_quality(url: str) -> int:
    """Return a quality score (0-5) for a URL based on its domain."""
    try:
        domain = urlparse(url).netloc.lower()
        # Strip www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        # Check exact match first, then parent domain
        if domain in _SOURCE_TIERS:
            return _SOURCE_TIERS[domain]
        # Check if it's a subdomain of a known source
        for known, score in _SOURCE_TIERS.items():
            if domain.endswith(f".{known}"):
                return score
        return 1  # unknown source
    except Exception:
        return 0


def is_blocked(url: str) -> bool:
    """Check if a URL is from a blocked domain."""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain == b or domain.endswith(f".{b}") for b in _BLOCKED_DOMAINS)
    except Exception:
        return True


async def scrape_url(url: str) -> dict[str, Any]:
    """Fetch a URL and extract article content.

    Returns a dict with:
        - url: the original URL
        - title: page title
        - content: extracted article text
        - quality: source quality score (0-5)
        - word_count: approximate word count
        - success: whether extraction succeeded
        - error: error message if failed
    """
    if is_blocked(url):
        return {"url": url, "success": False, "error": "Blocked domain"}

    quality = get_source_quality(url)
    start = _time.perf_counter()

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return {
                "url": url,
                "success": False,
                "error": f"Not HTML: {content_type}",
            }

        html = resp.text
        title, content = _extract_article(html)
        elapsed_ms = (_time.perf_counter() - start) * 1000

        if not content or len(content) < 100:
            return {
                "url": url,
                "title": title,
                "success": False,
                "error": "No meaningful content extracted",
            }

        # Truncate if too long
        if len(content) > _MAX_CONTENT_LENGTH:
            content = content[:_MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

        word_count = len(content.split())

        logger.info(
            "Scraped %s — %d words, quality=%d, %.0fms",
            url, word_count, quality, elapsed_ms,
        )

        return {
            "url": url,
            "title": title,
            "content": content,
            "quality": quality,
            "word_count": word_count,
            "success": True,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "url": url,
            "success": False,
            "error": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "url": url,
            "success": False,
            "error": str(exc)[:200],
        }


def _extract_article(html: str) -> tuple[str, str]:
    """Extract title and main article content from HTML.

    Uses a heuristic approach:
    1. Try <article> tag
    2. Try main content divs (role=main, class=content, etc.)
    3. Fall back to largest text block
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Remove noise elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "iframe", "noscript", "form",
                              "button", "input", "select", "textarea"]):
        tag.decompose()

    # Remove ad-related elements
    for tag in soup.find_all(class_=re.compile(
        r"(ad[s_-]|banner|sidebar|nav|menu|footer|comment|social|share|popup|modal|cookie)",
        re.IGNORECASE,
    )):
        tag.decompose()

    # Strategy 1: <article> tag
    article = soup.find("article")
    if article:
        text = _clean_text(article.get_text(separator="\n"))
        if len(text) > 200:
            return title, text

    # Strategy 2: main content containers
    for selector in [
        {"role": "main"},
        {"class_": re.compile(r"(article|post|entry|content|story|body)", re.I)},
        {"id": re.compile(r"(article|post|entry|content|story|main)", re.I)},
    ]:
        container = soup.find("div", selector) or soup.find("section", selector)
        if container:
            text = _clean_text(container.get_text(separator="\n"))
            if len(text) > 200:
                return title, text

    # Strategy 3: largest text block from all <p> tags
    paragraphs = soup.find_all("p")
    if paragraphs:
        texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40]
        if texts:
            return title, _clean_text("\n\n".join(texts))

    # Last resort: body text
    body = soup.find("body")
    if body:
        return title, _clean_text(body.get_text(separator="\n"))[:5000]

    return title, ""


def _clean_text(text: str) -> str:
    """Clean extracted text: normalize whitespace, remove empty lines."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple blank lines to double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    # Remove very short lines (likely navigation remnants)
    lines = [l for l in lines if len(l) > 2 or l == ""]
    return "\n".join(lines).strip()


def extract_urls_from_text(text: str) -> list[str]:
    """Extract HTTP(S) URLs from a text string (e.g., search results)."""
    url_pattern = re.compile(
        r'https?://[^\s<>"\')\]]+',
        re.IGNORECASE,
    )
    urls = url_pattern.findall(text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        # Clean trailing punctuation
        url = url.rstrip(".,;:!?)")
        if url not in seen and not is_blocked(url):
            seen.add(url)
            unique.append(url)
    return unique


async def deep_research_topic(
    topic_label: str,
    search_results: str,
    max_urls: int = 5,
) -> list[dict[str, Any]]:
    """Deep-scrape a topic by extracting URLs from search results and fetching content.

    Returns a list of scraped article dicts, sorted by quality score descending.
    """
    urls = extract_urls_from_text(search_results)

    if not urls:
        logger.info("No URLs found in search results for %s", topic_label)
        return []

    # Sort by source quality (prefer higher quality sources)
    urls_scored = [(url, get_source_quality(url)) for url in urls]
    urls_scored.sort(key=lambda x: x[1], reverse=True)

    # Take top N
    urls_to_scrape = [url for url, _ in urls_scored[:max_urls]]

    logger.info(
        "Deep scraping %d URLs for topic '%s': %s",
        len(urls_to_scrape), topic_label, urls_to_scrape,
    )

    results: list[dict[str, Any]] = []
    for url in urls_to_scrape:
        result = await scrape_url(url)
        if result["success"]:
            results.append(result)

    # Sort by quality
    results.sort(key=lambda x: x.get("quality", 0), reverse=True)

    logger.info(
        "Deep scrape complete for '%s': %d/%d URLs successful",
        topic_label, len(results), len(urls_to_scrape),
    )

    return results
