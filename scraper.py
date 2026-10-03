

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

MAX_RETRIES = 4
BACKOFF_FACTOR = 1.5
REQUEST_TIMEOUT = 20
DELAY_RANGE = (1.0, 2.5)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("generic_scraper")


@dataclass
class ScrapedPage:
    title: str
    url: str
    text: str
    links: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


def build_session() -> requests.Session:
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
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        time.sleep(random.uniform(*DELAY_RANGE))
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP error fetching %s: %s", url, exc)
    except requests.exceptions.ConnectionError as exc:
        logger.error("Connection error fetching %s: %s", url, exc)
    except requests.exceptions.Timeout as exc:
        logger.error("Timeout fetching %s: %s", url, exc)
    except requests.exceptions.RequestException as exc:
        logger.error("Unexpected request error fetching %s: %s", url, exc)
    return None


def safe_text(node) -> Optional[str]:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def clean_url(href: Optional[str], page_url: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("#"):
        return None
    full_url = urljoin(page_url, href)
    return full_url.split("#", 1)[0]


def get_page_title(soup: BeautifulSoup, default_url: str) -> str:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        return title
    h1 = soup.select_one("h1")
    if h1:
        return safe_text(h1) or default_url
    return default_url


def collect_text(soup: BeautifulSoup) -> str:
    preferred = soup.select("main, article, section, .content, #content, .post, .entry")
    root = preferred[0] if preferred else soup.body or soup

    text_chunks = []
    for tag in root.select("h1, h2, h3, p, li, td, th, span"):
        text = safe_text(tag)
        if text and len(text) > 1:
            text_chunks.append(text)

    if not text_chunks:
        all_text = safe_text(root)
        if all_text:
            return all_text
        return ""

    joined = "\n".join(text_chunks)
    return "\n".join(dict.fromkeys(line.strip() for line in joined.splitlines() if line.strip()))


def collect_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    links = []
    seen = set()
    for tag in soup.select("a[href]"):
        href = clean_url(tag.get("href"), page_url)
        if href and href not in seen:
            links.append(href)
            seen.add(href)
    return links


def find_next_page_url(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    next_link = soup.select_one("a[rel='next'], a[aria-label*='next' i], a.next, a.pagination-next")
    if next_link:
        next_href = clean_url(next_link.get("href"), current_url)
        if next_href:
            return next_href

    for a in soup.select("a[href]"):
        text = (a.get_text(" ", strip=True) or "").lower()
        href = a.get("href")
        if text.startswith("next") or "next" in text or text == ">":
            cleaned = clean_url(href, current_url)
            if cleaned:
                return cleaned

    parsed = urlparse(current_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("page", "p", "pg"):
        if key in params and params[key].isdigit():
            next_page = int(params[key]) + 1
            new_params = params.copy()
            new_params[key] = str(next_page)
            query = urlencode(new_params)
            return parsed._replace(query=query).geturl()
    return None


def parse_generic_page(soup: BeautifulSoup, page_url: str) -> ScrapedPage:
    title = get_page_title(soup, page_url)
    text = collect_text(soup)
    links = collect_links(soup, page_url)
    return ScrapedPage(title=title, url=page_url, text=text, links=links)


def scrape_all(start_url: str, max_pages: Optional[int] = 1) -> list[ScrapedPage]:
    session = build_session()
    current_url = start_url
    visited = set()
    pages: list[ScrapedPage] = []
    page_count = 0

    while current_url and current_url not in visited:
        if max_pages is not None and page_count >= max_pages:
            logger.info("Reached max_pages=%s limit, stopping.", max_pages)
            break

        visited.add(current_url)
        page_count += 1
        logger.info("Fetching page %d: %s", page_count, current_url)
        soup = fetch_page(session, current_url)
        if soup is None:
            logger.error("Failed to fetch %s; stopping.", current_url)
            break

        page = parse_generic_page(soup, current_url)
        pages.append(page)

        next_url = find_next_page_url(soup, current_url)
        if not next_url:
            break
        if next_url in visited:
            break
        current_url = next_url

    logger.info("Scrape complete: %d page(s) collected.", len(pages))
    return pages


def save_csv(pages: list[ScrapedPage], filepath: str) -> None:
    if not pages:
        logger.warning("No data to save (CSV).")
        return
    fieldnames = ["title", "url", "text", "links", "scraped_at"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for page in pages:
            writer.writerow({
                "title": page.title,
                "url": page.url,
                "text": page.text,
                "links": " | ".join(page.links),
                "scraped_at": page.scraped_at,
            })
    logger.info("Saved %d pages to %s", len(pages), filepath)


def save_json(pages: list[ScrapedPage], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump([asdict(page) for page in pages], f, indent=2, ensure_ascii=False)
    logger.info("Saved %d pages to %s", len(pages), filepath)


def save_sqlite(pages: list[ScrapedPage], filepath: str) -> None:
    conn = sqlite3.connect(filepath)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scraped_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT,
            text TEXT,
            links TEXT,
            scraped_at TEXT
        )
    """)
    cur.executemany(
        """INSERT INTO scraped_pages (title, url, text, links, scraped_at)
           VALUES (:title, :url, :text, :links, :scraped_at)""",
        [{
            "title": page.title,
            "url": page.url,
            "text": page.text,
            "links": " | ".join(page.links),
            "scraped_at": page.scraped_at,
        } for page in pages],
    )
    conn.commit()
    conn.close()
    logger.info("Saved %d pages to %s (table: scraped_pages)", len(pages), filepath)


SAVERS = {
    "csv": save_csv,
    "json": save_json,
    "sqlite": save_sqlite,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generic website scraper for extracting page titles, text, and links.")
    parser.add_argument("--url", required=True, help="Website URL to scrape")
    parser.add_argument("--output-format", choices=["csv", "json", "sqlite"], default="json", help="Output format")
    parser.add_argument("--output-file", default=None, help="Output file path")
    parser.add_argument("--max-pages", type=int, default=1, help="Maximum number of pages to scrape (default: 1)")
    parser.add_argument("--delay-min", type=float, default=DELAY_RANGE[0], help="Minimum delay between requests in seconds")
    parser.add_argument("--delay-max", type=float, default=DELAY_RANGE[1], help="Maximum delay between requests in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global DELAY_RANGE
    DELAY_RANGE = (args.delay_min, args.delay_max)

    if not args.url:
        logger.error("A website URL is required. Use --url https://example.com")
        return 1

    default_ext = {"csv": "csv", "json": "json", "sqlite": "db"}[args.output_format]
    output_file = args.output_file or f"scraped_site.{default_ext}"

    try:
        pages = scrape_all(args.url, max_pages=args.max_pages)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 1

    if not pages:
        logger.error("No data was scraped from %s", args.url)
        return 1

    SAVERS[args.output_format](pages, output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())