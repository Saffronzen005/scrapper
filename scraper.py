"""
Generic product page scraper — extracts price and stock/availability data.

Uses multiple extraction strategies in priority order:
  1. JSON-LD structured data (schema.org Product)
  2. Microdata (itemprop attributes)
  3. Open Graph / product meta tags
  4. Common CSS class patterns
  5. Regex patterns as last resort

Works across most e-commerce sites without site-specific code.
"""

import json
import re
import random
import time
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    USER_AGENTS,
    SCRAPE_TIMEOUT,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    MAX_SCRAPE_RETRIES,
)

logger = logging.getLogger(__name__)


@dataclass
class ProductData:
    """Extracted product information from a seller page."""
    price: str = ""
    currency: str = ""
    stock_status: str = "Unknown"
    page_title: str = ""
    error: str = ""


def scrape_product_page(url: str) -> ProductData:
    """
    Fetch a product page and extract price + stock data.

    Args:
        url: Full URL of the product page to scrape

    Returns:
        ProductData with whatever could be extracted.
        On failure, the 'error' field will contain the reason.
    """
    for attempt in range(MAX_SCRAPE_RETRIES + 1):
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "DNT": "1",
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=SCRAPE_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            page_title = ""
            if soup.title and soup.title.string:
                page_title = soup.title.get_text(strip=True)

            price, currency = _extract_price(soup)
            stock = _extract_stock(soup)

            # Small delay between scrapes
            time.sleep(random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX))

            return ProductData(
                price=price,
                currency=currency,
                stock_status=stock,
                page_title=page_title,
            )

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout scraping {url} (attempt {attempt + 1})")
            if attempt < MAX_SCRAPE_RETRIES:
                time.sleep(5 * (attempt + 1))
                continue
            return ProductData(error="Timeout")

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else "?"
            logger.warning(f"HTTP {status_code} scraping {url}")
            return ProductData(error=f"HTTP {status_code}")

        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error scraping {url} (attempt {attempt + 1})")
            if attempt < MAX_SCRAPE_RETRIES:
                time.sleep(5 * (attempt + 1))
                continue
            return ProductData(error="Connection Error")

        except Exception as e:
            logger.error(f"Unexpected error scraping {url}: {e}")
            return ProductData(error=str(e)[:100])

    return ProductData(error="Max retries exceeded")


# ═════════════════════════════════════════════════════════════════════
# PRICE EXTRACTION
# ═════════════════════════════════════════════════════════════════════

def _extract_price(soup: BeautifulSoup) -> tuple[str, str]:
    """
    Try multiple strategies to extract price and currency.
    Returns (price_string, currency_code). Empty strings if not found.
    """
    # Strategy 1: JSON-LD (most reliable — structured data)
    result = _price_from_jsonld(soup)
    if result[0]:
        return result

    # Strategy 2: Microdata (itemprop="price")
    result = _price_from_microdata(soup)
    if result[0]:
        return result

    # Strategy 3: Open Graph / product meta tags
    result = _price_from_meta_tags(soup)
    if result[0]:
        return result

    # Strategy 4: Common CSS class patterns
    result = _price_from_css_classes(soup)
    if result[0]:
        return result

    return ("", "")


def _price_from_jsonld(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract price from JSON-LD structured data."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            text = script.string
            if not text:
                continue
            data = json.loads(text)

            # JSON-LD can be a single object or a list
            items = data if isinstance(data, list) else [data]

            for item in items:
                result = _parse_product_jsonld(item)
                if result[0]:
                    return result

                # Handle @graph structure (common on WordPress/WooCommerce)
                if "@graph" in item:
                    for graph_item in item["@graph"]:
                        result = _parse_product_jsonld(graph_item)
                        if result[0]:
                            return result
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    return ("", "")


def _parse_product_jsonld(data: dict) -> tuple[str, str]:
    """Parse a single JSON-LD Product object for price."""
    item_type = data.get("@type", "")

    # Handle both "Product" and ["Product", "SomeOtherType"]
    if isinstance(item_type, list):
        if "Product" not in item_type:
            return ("", "")
    elif item_type != "Product":
        return ("", "")

    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    if isinstance(offers, dict):
        # Direct price
        price = str(offers.get("price", ""))
        currency = offers.get("priceCurrency", "")

        if not price:
            # AggregateOffer — use lowPrice
            price = str(offers.get("lowPrice", ""))

        if price and price != "0" and price != "None":
            return (price, currency)

    return ("", "")


def _price_from_microdata(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract price from itemprop microdata attributes."""
    price_elem = soup.find(attrs={"itemprop": "price"})
    if price_elem:
        price_val = price_elem.get("content") or price_elem.get_text(strip=True)
        price_clean = re.sub(r"[^\d.,]", "", price_val)

        currency_elem = soup.find(attrs={"itemprop": "priceCurrency"})
        currency_val = ""
        if currency_elem:
            currency_val = currency_elem.get("content") or currency_elem.get_text(strip=True)

        if price_clean:
            return (price_clean, currency_val)

    return ("", "")


def _price_from_meta_tags(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract price from <meta> tags (Open Graph / product)."""
    price_selectors = [
        {"property": "product:price:amount"},
        {"property": "og:price:amount"},
        {"name": "price"},
        {"name": "twitter:data1"},
    ]

    for selector in price_selectors:
        meta = soup.find("meta", selector)
        if meta and meta.get("content"):
            price = meta["content"]

            # Try to find matching currency meta
            currency = ""
            curr_meta = (
                soup.find("meta", {"property": "product:price:currency"})
                or soup.find("meta", {"property": "og:price:currency"})
            )
            if curr_meta:
                currency = curr_meta.get("content", "")

            return (price, currency)

    return ("", "")


def _price_from_css_classes(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract price from common e-commerce CSS class patterns."""
    selectors = [
        ".product-price",
        ".price .amount",
        ".price",
        ".current-price",
        ".sale-price",
        ".offer-price",
        ".woocommerce-Price-amount",
        ".product__price",
        "#product-price",
        "[data-price]",
    ]

    for selector in selectors:
        elem = soup.select_one(selector)
        if not elem:
            continue

        # Check for data-price attribute first
        if elem.get("data-price"):
            return (elem["data-price"], "")

        text = elem.get_text(strip=True)
        if not text:
            continue

        # Try to parse currency symbol + number
        price, currency = _parse_price_text(text)
        if price:
            return (price, currency)

    return ("", "")


# ═════════════════════════════════════════════════════════════════════
# STOCK EXTRACTION
# ═════════════════════════════════════════════════════════════════════

def _extract_stock(soup: BeautifulSoup) -> str:
    """
    Try multiple strategies to extract stock/availability status.
    Returns a normalized stock string.
    """
    # Strategy 1: JSON-LD
    stock = _stock_from_jsonld(soup)
    if stock:
        return stock

    # Strategy 2: Microdata
    avail_elem = soup.find(attrs={"itemprop": "availability"})
    if avail_elem:
        val = (
            avail_elem.get("content")
            or avail_elem.get("href")
            or avail_elem.get_text(strip=True)
        )
        return _normalize_stock(val)

    # Strategy 3: Common CSS patterns
    stock = _stock_from_css_classes(soup)
    if stock:
        return stock

    return "Unknown"


def _stock_from_jsonld(soup: BeautifulSoup) -> str:
    """Extract stock/availability from JSON-LD."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            text = script.string
            if not text:
                continue
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]

            for item in items:
                stock = _parse_stock_jsonld(item)
                if stock:
                    return stock

                if "@graph" in item:
                    for graph_item in item["@graph"]:
                        stock = _parse_stock_jsonld(graph_item)
                        if stock:
                            return stock
        except (json.JSONDecodeError, TypeError):
            continue

    return ""


def _parse_stock_jsonld(data: dict) -> str:
    """Parse stock from a JSON-LD Product object."""
    item_type = data.get("@type", "")
    if isinstance(item_type, list):
        if "Product" not in item_type:
            return ""
    elif item_type != "Product":
        return ""

    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    if isinstance(offers, dict):
        availability = offers.get("availability", "")
        if availability:
            return _normalize_stock(availability)

    return ""


def _stock_from_css_classes(soup: BeautifulSoup) -> str:
    """Extract stock from common CSS class patterns."""
    selectors = [
        ".stock",
        ".availability",
        ".product-stock",
        ".in-stock",
        ".out-of-stock",
        ".product-availability",
        "#product-availability",
    ]

    for selector in selectors:
        elem = soup.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            if text:
                return _normalize_stock(text[:80])

    # Also check for class names that indicate stock status
    in_stock = soup.find(class_=re.compile(r"\bin[-_]?stock\b", re.IGNORECASE))
    if in_stock:
        return "In Stock"

    out_of_stock = soup.find(class_=re.compile(r"\bout[-_]?of[-_]?stock\b", re.IGNORECASE))
    if out_of_stock:
        return "Out of Stock"

    return ""


# ═════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "Fr": "CHF",
    "kr": "SEK",   # Also DKK, NOK — ambiguous
    "zł": "PLN",
    "Kč": "CZK",
    "R$": "BRL",
}


def _parse_price_text(text: str) -> tuple[str, str]:
    """
    Parse a raw price string like '€123.45' or '123,45 €' into (price, currency).
    """
    # Pattern: symbol then number  (e.g., €123.45, $99.00)
    match = re.search(r"([\$€£¥₹₩])\s*(\d[\d.,]*\d|\d+)", text)
    if match:
        symbol = match.group(1)
        price = match.group(2)
        currency = CURRENCY_SYMBOLS.get(symbol, symbol)
        return (price, currency)

    # Pattern: number then symbol (e.g., 123.45€, 99,00 €)
    match = re.search(r"(\d[\d.,]*\d|\d+)\s*([\$€£¥₹₩])", text)
    if match:
        price = match.group(1)
        symbol = match.group(2)
        currency = CURRENCY_SYMBOLS.get(symbol, symbol)
        return (price, currency)

    # Pattern: number then currency code (e.g., 123.45 EUR)
    match = re.search(r"(\d[\d.,]*\d|\d+)\s*(EUR|USD|GBP|CHF|SEK|DKK|NOK|PLN|CZK)", text)
    if match:
        return (match.group(1), match.group(2))

    # Pattern: currency code then number (e.g., EUR 123.45)
    match = re.search(r"(EUR|USD|GBP|CHF|SEK|DKK|NOK|PLN|CZK)\s*(\d[\d.,]*\d|\d+)", text)
    if match:
        return (match.group(2), match.group(1))

    return ("", "")


def _normalize_stock(raw: str) -> str:
    """Normalize various stock status strings into a clean label."""
    if not raw:
        return "Unknown"

    raw_lower = raw.lower()

    if "instock" in raw_lower or "in_stock" in raw_lower or "in stock" in raw_lower:
        return "In Stock"
    elif "outofstock" in raw_lower or "out_of_stock" in raw_lower or "out of stock" in raw_lower:
        return "Out of Stock"
    elif "preorder" in raw_lower or "pre-order" in raw_lower:
        return "Pre-order"
    elif "backorder" in raw_lower or "back-order" in raw_lower:
        return "Back Order"
    elif "limited" in raw_lower:
        return "Limited Stock"
    elif "discontinued" in raw_lower:
        return "Discontinued"
    elif "available" in raw_lower:
        return "Available"
    elif "unavailable" in raw_lower or "not available" in raw_lower:
        return "Unavailable"

    # If it's a schema.org URL, extract the last segment
    if "schema.org" in raw_lower:
        parts = raw.rstrip("/").split("/")
        return _normalize_stock(parts[-1]) if parts else raw[:50]

    return raw[:50]
