#!/usr/bin/env python3
"""
Production-grade web scraper
=============================

Target site   : https://opmcm.gov.np/category/information-and-news/
                 (सूचना तथा समाचार — "Notices & News" section of Nepal's
                 Office of the Prime Minister and Council of Ministers)
Data extracted : Title (शीर्षक), Published Date (प्रकाशित मिति), Link (URL)
Stack          : requests + BeautifulSoup4 (static server-rendered HTML table)
Output         : CSV, JSON, or SQLite (configurable via CLI flag)

Site structure notes (found by inspecting the live page):
- Listings render as a plain HTML <table> with one <tr> per notice.
- Columns (in order): क्र.स. (row number), शीर्षक (title, contains the <a>
  link to the notice), प्रकाशित मिति (published date + time), फाइल प्रकार
  (PDF attachment link), कार्य (duplicate link to the content page).
- Pagination is a simple query string: ?page=1, ?page=2, ?page=3, ...
- There is no reliable "next" link markup to follow (the visible pager
  is just numbered links), so this script paginates by incrementing
  ?page=N and stops as soon as a page returns zero table rows.

To adapt this script to a different site, you mainly need to change:
1. LISTING_URL_TEMPLATE
2. parse_listing_page() -- the row/cell selectors
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sqlite3
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

BASE_URL = "https://opmcm.gov.np/"
CATEGORY_URL = urljoin(BASE_URL, "category/information-and-news/")
# The site paginates via a query string appended to the category URL.
LISTING_URL_TEMPLATE = CATEGORY_URL + "?page={page}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 "
    "Firefox/125.0",
]

MAX_RETRIES = 4
BACKOFF_FACTOR = 1.5          # exponential backoff between retries
REQUEST_TIMEOUT = 15          # seconds
DELAY_RANGE = (1.5, 3.0)      # polite randomized delay between page fetches
                               # (kept a bit higher than default -- this is
                               # a government server, be extra respectful)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scraper")


# --------------------------------------------------------------------------
# DATA MODEL
# --------------------------------------------------------------------------

@dataclass
class Notice:
    """Structured representation of a single scraped notice/news item."""
    title: str
    published_date: Optional[str] = None
    url: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


# --------------------------------------------------------------------------
# HTTP SESSION WITH RETRIES + UA ROTATION
# --------------------------------------------------------------------------

def build_session() -> requests.Session:
    """Create a requests.Session with automatic retry/backoff on transient
    failures (connection errors, 429, 5xx) baked into the transport layer.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_page(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    """Fetch a URL and return a parsed BeautifulSoup tree.

    Rotates User-Agent per request, applies a randomized polite delay,
    and never raises -- returns None on unrecoverable failure so the
    caller can decide whether to skip or abort.
    """
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "ne,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        time.sleep(random.uniform(*DELAY_RANGE))
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error fetching %s: %s", url, e)
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error fetching %s: %s", url, e)
    except requests.exceptions.Timeout as e:
        logger.error("Timeout fetching %s: %s", url, e)
    except requests.exceptions.RequestException as e:
        logger.error("Unexpected request error fetching %s: %s", url, e)

    return None


# --------------------------------------------------------------------------
# PARSING
# --------------------------------------------------------------------------

def safe_text(node) -> Optional[str]:
    """Extract stripped text from a BeautifulSoup node, tolerating None."""
    if node is None:
        return None
    text = node.get_text(strip=True)
    return text or None


def parse_listing_page(soup: BeautifulSoup, page_url: str) -> list[Notice]:
    """Parse one listing page's table into a list of Notice records.

    Each row is wrapped in its own try/except so one malformed row can't
    abort extraction of the rest of the page.
    """
    notices: list[Notice] = []

    # The listing renders as a <table>; data rows are every <tr> that
    # contains a link to a /content/<id>/<slug>/ detail page.
    rows = soup.select("table tr")

    for row in rows:
        try:
            # Title + link: the शीर्षक column's <a> tag pointing at /content/
            title_link = row.find("a", href=lambda h: h and "/content/" in h)
            if title_link is None:
                # Header row or a row without a content link -- skip silently.
                continue

            title = safe_text(title_link)
            if not title:
                logger.warning("Skipping row with empty title on %s", page_url)
                continue

            url = urljoin(page_url, title_link["href"])

            # Published date: the cell that follows the title cell.
            # We look for the first <td> whose text contains typical Nepali
            # date/month markers; falling back to the 3rd <td> if present.
            cells = row.find_all("td")
            published_date = None
            for cell in cells:
                text = safe_text(cell)
                if text and any(ch.isdigit() for ch in text) and "," in text:
                    # Dates on this site look like "भदौ ३, २०८३, बुधबार १०:२४"
                    published_date = text
                    break
            if published_date is None and len(cells) >= 3:
                published_date = safe_text(cells[2])

            notices.append(Notice(
                title=title,
                published_date=published_date,
                url=url,
            ))

        except Exception as e:
            logger.warning("Failed to parse a row on %s: %s", page_url, e)
            continue

    # De-duplicate: the same /content/ link can appear more than once per
    # row (title link + "कार्य" action link) if selectors overlap.
    seen = set()
    deduped = []
    for n in notices:
        if n.url not in seen:
            seen.add(n.url)
            deduped.append(n)

    return deduped


# --------------------------------------------------------------------------
# PAGINATION LOOP
# --------------------------------------------------------------------------

def scrape_all(max_pages: Optional[int] = None) -> list[Notice]:
    """Walk ?page=1, ?page=2, ... until a page returns zero notices, or
    max_pages is reached. Robust to individual page failures: a failed
    page is logged and the loop stops gracefully rather than crashing.
    """
    session = build_session()
    all_notices: list[Notice] = []
    page_num = 1

    while True:
        if max_pages and page_num > max_pages:
            logger.info("Reached max_pages=%s limit, stopping.", max_pages)
            break

        current_url = LISTING_URL_TEMPLATE.format(page=page_num)
        logger.info("Fetching page %d: %s", page_num, current_url)
        soup = fetch_page(session, current_url)

        if soup is None:
            logger.error("Giving up on page %d after retries exhausted; stopping.", page_num)
            break

        page_notices = parse_listing_page(soup, current_url)

        if not page_notices:
            logger.info("Page %d returned no notices -- assuming end of pagination.", page_num)
            break

        logger.info("  -> extracted %d notices", len(page_notices))
        all_notices.extend(page_notices)
        page_num += 1

    logger.info("Scrape complete: %d total notices across %d page(s).", len(all_notices), page_num - 1)
    return all_notices


# --------------------------------------------------------------------------
# OUTPUT / STORAGE
# --------------------------------------------------------------------------

def save_csv(notices: list[Notice], filepath: str) -> None:
    if not notices:
        logger.warning("No notices to save (CSV).")
        return
    fieldnames = list(asdict(notices[0]).keys())
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        # utf-8-sig so Excel on Windows renders Nepali (Devanagari) text
        # correctly instead of mangling it.
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for n in notices:
            writer.writerow(asdict(n))
    logger.info("Saved %d records to %s", len(notices), filepath)


def save_json(notices: list[Notice], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump([asdict(n) for n in notices], f, indent=2, ensure_ascii=False)
    logger.info("Saved %d records to %s", len(notices), filepath)


def save_sqlite(notices: list[Notice], filepath: str) -> None:
    conn = sqlite3.connect(filepath)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            published_date TEXT,
            url TEXT,
            scraped_at TEXT
        )
    """)
    cur.executemany(
        """INSERT INTO notices (title, published_date, url, scraped_at)
           VALUES (:title, :published_date, :url, :scraped_at)""",
        [asdict(n) for n in notices],
    )
    conn.commit()
    conn.close()
    logger.info("Saved %d records to %s (table: notices)", len(notices), filepath)


SAVERS = {
    "csv": save_csv,
    "json": save_json,
    "sqlite": save_sqlite,
}


# --------------------------------------------------------------------------
# CLI ENTRY POINT
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape opmcm.gov.np Notices & News (सूचना तथा समाचार) into CSV/JSON/SQLite."
    )
    parser.add_argument("--output-format", choices=["csv", "json", "sqlite"], default="csv",
                         help="Output format (default: csv)")
    parser.add_argument("--output-file", default=None,
                         help="Output file path (default: opmcm_notices.<ext>)")
    parser.add_argument("--max-pages", type=int, default=None,
                         help="Limit number of pages to scrape (default: all pages)")
    parser.add_argument("--delay-min", type=float, default=DELAY_RANGE[0],
                         help="Minimum delay between requests, seconds")
    parser.add_argument("--delay-max", type=float, default=DELAY_RANGE[1],
                         help="Maximum delay between requests, seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    global DELAY_RANGE
    DELAY_RANGE = (args.delay_min, args.delay_max)

    default_ext = {"csv": "csv", "json": "json", "sqlite": "db"}[args.output_format]
    output_file = args.output_file or f"opmcm_notices.{default_ext}"

    try:
        notices = scrape_all(max_pages=args.max_pages)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 1

    if not notices:
        logger.error("No notices were scraped. Exiting without writing output.")
        return 1

    SAVERS[args.output_format](notices, output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())