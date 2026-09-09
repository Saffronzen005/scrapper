"""
Configuration for the KONE Unauthorized Seller Detection Tool.

All tunable settings are here. Modify as needed.
"""

# ──────────────────────────────────────────────────────────────────────
# AUTHORIZED KONE DOMAINS (will NOT be flagged as unauthorized)
# ──────────────────────────────────────────────────────────────────────
AUTHORIZED_DOMAINS = [
    "kone.com",
    "parts.kone.com",
]

# ──────────────────────────────────────────────────────────────────────
# EXCLUDED DOMAINS (not sellers — skip these in results)
# ──────────────────────────────────────────────────────────────────────
EXCLUDED_DOMAINS = [
    # Social media & forums
    "scribd.com",
    "reddit.com",
    "youtube.com",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "quora.com",
    "instagram.com",
    "tiktok.com",

    # Reference / non-commercial
    "wikipedia.org",
    "github.com",
    "stackoverflow.com",
    "archive.org",

    # Document / file sharing
    "slideshare.net",
    "issuu.com",
    "academia.edu",
    "researchgate.net",

    # Search engines (their own cached pages)
    "google.com",
    "bing.com",
    "duckduckgo.com",
    "yahoo.com",

    # Job / company review sites
    "glassdoor.com",
    "indeed.com",
]

# ──────────────────────────────────────────────────────────────────────
# SEARCH SETTINGS
# ──────────────────────────────────────────────────────────────────────
SEARCH_DELAY_MIN = 4            # Minimum seconds between DuckDuckGo searches
SEARCH_DELAY_MAX = 8            # Maximum seconds between DuckDuckGo searches
MAX_SEARCH_RESULTS = 20         # Results to fetch per product code
SEARCH_REGION = "wt-wt"        # Worldwide (DuckDuckGo region code)

# Longer delay after every N searches to avoid rate limiting
LONG_PAUSE_EVERY_N = 30         # After every 30 searches...
LONG_PAUSE_MIN = 30             # ...wait 30–60 seconds
LONG_PAUSE_MAX = 60

# ──────────────────────────────────────────────────────────────────────
# SCRAPING SETTINGS
# ──────────────────────────────────────────────────────────────────────
SCRAPE_TIMEOUT = 15             # Seconds before page fetch times out
SCRAPE_DELAY_MIN = 1            # Delay between scraping different sites
SCRAPE_DELAY_MAX = 3
MAX_SCRAPE_RETRIES = 2          # Retries on transient errors

# ──────────────────────────────────────────────────────────────────────
# FILE PATHS
# ──────────────────────────────────────────────────────────────────────
DEFAULT_INPUT_FILE = "book.xlsx"
OUTPUT_DIR = "results"
PROGRESS_FILE = "progress.txt"
LOG_FILE = "scrapper.log"

# Save the output Excel every N product codes (crash safety)
SAVE_EVERY_N = 10

# ──────────────────────────────────────────────────────────────────────
# USER-AGENT ROTATION (realistic browser headers)
# ──────────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]
