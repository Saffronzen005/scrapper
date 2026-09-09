"""
Result analyzer — classifies search results as AUTHORIZED, UNAUTHORIZED, or EXCLUDED.

Compares each result's domain against the configured whitelist and exclusion list.
Filters out irrelevant results that don't actually reference the product code.
"""

import logging
from dataclasses import dataclass

from config import AUTHORIZED_DOMAINS, EXCLUDED_DOMAINS

logger = logging.getLogger(__name__)


@dataclass
class SellerClassification:
    """Classification result for a single search hit."""
    product_code: str
    domain: str
    url: str
    title: str
    snippet: str
    status: str   # "UNAUTHORIZED" | "AUTHORIZED" | "EXCLUDED" | "IRRELEVANT"


def _domain_matches(domain: str, domain_list: list[str]) -> bool:
    """
    Check if a domain matches any entry in the list.

    Supports both exact match and subdomain matching.
    E.g., 'shop.elevator-parts.eu' matches 'elevator-parts.eu'.
    """
    for entry in domain_list:
        if domain == entry or domain.endswith("." + entry):
            return True
    return False


def _is_relevant(product_code: str, result) -> bool:
    """
    Check if a search result is actually relevant to the product code.

    DuckDuckGo sometimes returns unrelated results when it has no real matches.
    This filter ensures the product code actually appears in the result's
    title, URL, or snippet text — eliminating false positives like court
    websites, adult sites, etc.

    Args:
        product_code: The KONE material code (e.g. "DEE0079892")
        result:       A SearchResult object

    Returns:
        True if the result appears to genuinely reference this product code.
    """
    code_lower = product_code.lower()

    # Check if the product code appears in any of the result fields
    fields_to_check = [
        result.title.lower() if result.title else "",
        result.url.lower() if result.url else "",
        result.snippet.lower() if result.snippet else "",
    ]

    for field in fields_to_check:
        if code_lower in field:
            return True

    return False


def classify_results(
    product_code: str,
    search_results: list,
) -> list[SellerClassification]:
    """
    Classify a list of search results for a given product code.

    Results go through two filters:
      1. Relevance filter — discards results that don't mention the product code
      2. Domain classification — authorized / unauthorized / excluded

    Args:
        product_code:    The KONE material code being checked
        search_results:  List of SearchResult objects from the search module

    Returns:
        List of SellerClassification objects (one per unique domain).
        Duplicate domains are deduplicated — only the first hit per domain is kept.
    """
    classifications: list[SellerClassification] = []
    seen_domains: set[str] = set()
    irrelevant_count = 0

    for result in search_results:
        domain = result.domain

        # Deduplicate by domain — one entry per seller
        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        # Relevance filter — skip results that don't reference the product code
        if not _is_relevant(product_code, result):
            irrelevant_count += 1
            logger.debug(f"[{product_code}] Skipped irrelevant result: {domain}")
            continue

        # Classify
        if _domain_matches(domain, AUTHORIZED_DOMAINS):
            status = "AUTHORIZED"
        elif _domain_matches(domain, EXCLUDED_DOMAINS):
            status = "EXCLUDED"
        else:
            status = "UNAUTHORIZED"

        classifications.append(SellerClassification(
            product_code=product_code,
            domain=domain,
            url=result.url,
            title=result.title,
            snippet=result.snippet,
            status=status,
        ))

    # Log summary for this product
    unauthorized_count = sum(1 for c in classifications if c.status == "UNAUTHORIZED")
    if irrelevant_count > 0:
        logger.debug(f"[{product_code}] Filtered out {irrelevant_count} irrelevant results")
    if unauthorized_count > 0:
        domains = [c.domain for c in classifications if c.status == "UNAUTHORIZED"]
        logger.info(f"[{product_code}] {unauthorized_count} unauthorized seller(s): {', '.join(domains)}")
    else:
        logger.debug(f"[{product_code}] Clean — no unauthorized sellers found")

    return classifications


def get_unauthorized(classifications: list[SellerClassification]) -> list[SellerClassification]:
    """Filter to only UNAUTHORIZED classifications."""
    return [c for c in classifications if c.status == "UNAUTHORIZED"]
