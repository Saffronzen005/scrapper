"""
KONE Unauthorized Seller Detection Tool
========================================

Scans the internet for KONE product codes and flags unauthorized sellers.

Usage:
    python main.py                          # Default: uses book.xlsx
    python main.py --input products.xlsx    # Custom input file
    python main.py --reset                  # Clear progress, start fresh

Features:
    - DuckDuckGo search (no API key, no IP blocking)
    - Automatic resume on crash/restart
    - Generic price & stock scraping from seller pages
    - Styled Excel output with summary dashboard
    - Rate limiting & anti-blocking built in
"""

import argparse
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime

from tqdm import tqdm

from config import (
    DEFAULT_INPUT_FILE,
    OUTPUT_DIR,
    PROGRESS_FILE,
    LOG_FILE,
    SAVE_EVERY_N,
)
from search import search_product, reset_search_counter
from analyzer import classify_results, get_unauthorized
from scraper import scrape_product_page
from excel_handler import (
    read_product_codes,
    create_output_workbook,
    load_output_workbook,
    append_unauthorized_row,
    append_clean_row,
    append_error_row,
    append_no_results_row,
    add_summary_sheet,
)


def setup_logging():
    """Configure logging to both file and console."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # File handler — detailed logs
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # Console handler — info and above only (tqdm-friendly)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def load_progress() -> set[str]:
    """Load the set of already-processed product codes from progress file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_progress(code: str):
    """Append a completed product code to the progress file."""
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(code + "\n")


def get_output_path() -> str:
    """Get the output file path. Reuses existing file for resume."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Check for an existing output file (for resume)
    existing = [
        f for f in os.listdir(OUTPUT_DIR)
        if f.startswith("unauthorized_sellers_") and f.endswith(".xlsx")
    ]

    if existing:
        # Use the most recent one
        existing.sort(reverse=True)
        path = os.path.join(OUTPUT_DIR, existing[0])
        return path

    # Create a new one
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(OUTPUT_DIR, f"unauthorized_sellers_{timestamp}.xlsx")


def process_product(code: str, sheet, stats: dict, domain_counter: Counter):
    """
    Process a single product code:
      1. Search DuckDuckGo
      2. Classify results
      3. Scrape unauthorized seller pages
      4. Write to Excel

    Args:
        code:           Product/material code
        sheet:          Active Excel sheet to write results to
        stats:          Running statistics dictionary (mutated in place)
        domain_counter: Counter of unauthorized seller domains (mutated)
    """
    logger = logging.getLogger("main")

    # Step 1: Search
    results = search_product(code)

    if not results:
        append_no_results_row(sheet, code)
        stats["no_results"] += 1
        logger.info(f"[{code}] No search results found")
        return

    # Step 2: Classify
    classifications = classify_results(code, results)
    unauthorized = get_unauthorized(classifications)

    if not unauthorized:
        append_clean_row(sheet, code)
        stats["clean"] += 1
        return

    # Step 3: Scrape each unauthorized seller + write rows
    stats["unauthorized"] += 1

    for seller in unauthorized:
        domain_counter[seller.domain] += 1

        # Attempt to scrape price & stock from the seller's page
        product_data = scrape_product_page(seller.url)

        append_unauthorized_row(
            sheet=sheet,
            product_code=code,
            domain=seller.domain,
            url=seller.url,
            title=product_data.page_title or seller.title,
            price=product_data.price,
            currency=product_data.currency,
            stock_status=product_data.stock_status,
            snippet=seller.snippet,
            scrape_error=product_data.error,
        )

        logger.info(
            f"[{code}] UNAUTHORIZED: {seller.domain} | "
            f"Price: {product_data.price} {product_data.currency} | "
            f"Stock: {product_data.stock_status}"
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="KONE Unauthorized Seller Detection Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        default=DEFAULT_INPUT_FILE,
        help=f"Input Excel file with product codes in column A (default: {DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear progress and start from the beginning",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("main")

    # ── Handle reset ─────────────────────────────────────────────────
    if args.reset:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print("[OK] Progress cleared.")
        # Remove existing output files
        if os.path.exists(OUTPUT_DIR):
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("unauthorized_sellers_") and f.endswith(".xlsx"):
                    os.remove(os.path.join(OUTPUT_DIR, f))
            print("[OK] Previous output files removed.")
        print()

    # ── Load product codes ───────────────────────────────────────────
    if not os.path.exists(args.input):
        print(f"ERROR: Input file '{args.input}' not found.")
        sys.exit(1)

    all_codes = read_product_codes(args.input)
    if not all_codes:
        print("ERROR: No product codes found in the input file.")
        sys.exit(1)

    # ── Resume support ───────────────────────────────────────────────
    completed = load_progress()
    remaining = [c for c in all_codes if c not in completed]

    print("=" * 60)
    print("  KONE Unauthorized Seller Detection Tool")
    print("=" * 60)
    print(f"  Input file:       {args.input}")
    print(f"  Total products:   {len(all_codes)}")
    print(f"  Already done:     {len(completed)}")
    print(f"  Remaining:        {len(remaining)}")
    print("=" * 60)
    print()

    if not remaining:
        print("All products have already been processed!")
        print("Use --reset to start fresh.")
        sys.exit(0)

    # ── Prepare output workbook ──────────────────────────────────────
    output_path = get_output_path()

    if os.path.exists(output_path) and not args.reset:
        wb = load_output_workbook(output_path)
    else:
        wb = create_output_workbook(output_path)

    sheet = wb["Unauthorized Sellers"]

    # ── Stats tracking ───────────────────────────────────────────────
    stats = {
        "total": 0,
        "unauthorized": 0,
        "clean": 0,
        "no_results": 0,
        "errors": 0,
    }
    domain_counter = Counter()
    unsaved_count = 0
    start_time = time.time()

    logger.info(f"Starting scan of {len(remaining)} product codes")

    # ── Main processing loop ─────────────────────────────────────────
    try:
        for code in tqdm(remaining, desc="Scanning products", unit="code", ncols=80):
            stats["total"] += 1

            try:
                process_product(code, sheet, stats, domain_counter)
            except KeyboardInterrupt:
                raise  # Let it propagate
            except Exception as e:
                logger.error(f"[{code}] Processing error: {e}", exc_info=True)
                append_error_row(sheet, code, str(e)[:200])
                stats["errors"] += 1

            # Record progress
            save_progress(code)
            unsaved_count += 1

            # Periodically save the Excel file
            if unsaved_count >= SAVE_EVERY_N:
                wb.save(output_path)
                unsaved_count = 0

    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user. Saving progress...")
        logger.warning("Scan interrupted by user")

    finally:
        # Always save on exit
        # Add summary sheet
        stats["unique_domains"] = len(domain_counter)
        stats["top_domains"] = domain_counter.most_common(25)

        # Add previously completed items to total count for summary
        stats["total"] += len(completed)
        stats["clean"] += len(completed)  # Approximate — previously completed assumed clean

        try:
            add_summary_sheet(wb, stats)
            wb.save(output_path)
            print(f"\n[OK] Results saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save final output: {e}")
            # Try saving without summary
            try:
                wb.save(output_path)
                print(f"\n[OK] Results saved (without summary) to: {output_path}")
            except Exception as e2:
                print(f"\n[FAIL] FAILED to save output: {e2}")

    # ── Print summary ────────────────────────────────────────────────
    elapsed = time.time() - start_time
    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

    print()
    print("-" * 60)
    print("  SCAN COMPLETE")
    print("-" * 60)
    print(f"  Time elapsed:              {elapsed_str}")
    print(f"  Products scanned (this run): {stats['total'] - len(completed)}")
    print(f"  [!] With unauthorized sellers: {stats['unauthorized']}")
    print(f"  [OK] Clean:                    {stats['clean'] - len(completed)}")
    print(f"  [?] No search results:         {stats['no_results']}")
    print(f"  [ERR] Errors:                  {stats['errors']}")
    print(f"  Unique unauthorized domains:   {stats['unique_domains']}")
    print("-" * 60)

    if domain_counter:
        print("\n  Top unauthorized seller domains:")
        for domain, count in domain_counter.most_common(10):
            print(f"    {count:>4}x  {domain}")

    print(f"\n  Full report: {output_path}")
    print(f"  Detailed log: {LOG_FILE}")
    print()


if __name__ == "__main__":
    main()