"""
DuckDuckGo search module for finding product codes on the web.

Uses the duckduckgo-search library (no API key needed).
Includes rate limiting, retry logic, and structured result output.
"""

import time
import random
import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException

from config import (
    SEARCH_DELAY_MIN,
    SEARCH_DELAY_MAX,
    MAX_SEARCH_RESULTS,
    SEARCH_REGION,
    LONG_PAUSE_EVERY_N,
    LONG_PAUSE_MIN,
    LONG_PAUSE_MAX,
)

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from DuckDuckGo."""
    title: str
    url: str
    domain: str      # Extracted and normalized domain (no www.)
    snippet: str


# ── Internal state for rate limiting ─────────────────────────────────
_search_count = 0


def _apply_delay(force_long: bool = False):
    """Wait between searches to avoid rate limiting."""
    global _search_count
    _search_count += 1

    if force_long or (_search_count % LONG_PAUSE_EVERY_N == 0):
        delay = random.uniform(LONG_PAUSE_MIN, LONG_PAUSE_MAX)
        logger.info(f"Long pause: {delay:.1f}s (after {_search_count} searches)")
    else:
        delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)

    time.sleep(delay)


def _extract_domain(url: str) -> str:
    """Extract and normalize domain from a URL."""
    try:
        netloc = urlparse(url).netloc.lower()
        # Strip 'www.' prefix
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def search_product(code: str, max_results: int = None) -> list[SearchResult]:
    """
    Search DuckDuckGo for a KONE product code.

    Args:
        code:        The product/material code to search for (e.g. "DEE0079892")
        max_results: Max results to fetch (default from config)

    Returns:
        List of SearchResult objects. Empty list on failure.
    """
    if max_results is None:
        max_results = MAX_SEARCH_RESULTS

    # Use exact-match quotes around the code
    query = f'"{code}"'

    results: list[SearchResult] = []

    for attempt in range(3):  # Up to 3 retries
        try:
            raw_results = DDGS().text(
                query,
                region=SEARCH_REGION,
                max_results=max_results,
            )

            for r in raw_results:
                url = r.get("href", "")
                domain = _extract_domain(url)
                if not domain:
                    continue

                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    domain=domain,
                    snippet=r.get("body", ""),
                ))

            logger.debug(f"Search for '{code}': {len(results)} results")
            break  # Success — exit retry loop

        except RatelimitException as e:
            logger.warning(f"Rate limited on attempt {attempt + 1} for '{code}': {e}")
            if attempt < 2:
                # Longer backoff for rate limits: 30s, 90s
                backoff = 30 * (attempt + 1) * 2
                logger.info(f"Rate limit backoff: {backoff}s before retry...")
                time.sleep(backoff)
            else:
                logger.error(f"Rate limit — all retries exhausted for '{code}'")

        except DDGSException as e:
            logger.warning(f"DDGS error on attempt {attempt + 1} for '{code}': {e}")
            if attempt < 2:
                backoff = 15 * (attempt + 1) * 2
                logger.info(f"Backing off for {backoff}s before retry...")
                time.sleep(backoff)
            else:
                logger.error(f"All retries exhausted for '{code}'")

        except Exception as e:
            logger.error(f"Unexpected search error for '{code}': {e}")
            break

    # Apply delay after every search (even failed ones)
    _apply_delay()

    return results


def reset_search_counter():
    """Reset the internal search counter (useful for testing)."""
    global _search_count
    _search_count = 0
