from __future__ import annotations

import argparse
import csv
import json
import ipaddress
import logging
import random
import re
import sqlite3
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]
MAX_RETRIES = 4
BACKOFF_FACTOR = 1.5
REQUEST_TIMEOUT = 20
MAX_RESPONSE_BYTES = 5_000_000
DEFAULT_DELAY_RANGE = (1.0, 2.5)

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
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not supported")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except (OSError, ValueError) as exc:
        raise ValueError("The URL host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Local and private network targets are not allowed")
    return url.strip()


def log_url(url: str) -> str:
    """Keep queries and fragments, which may contain credentials, out of logs."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def fetch_page(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        for _ in range(6):
            validate_url(url)
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True)
            if response.is_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise requests.exceptions.HTTPError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                response.close()
                raise ValueError("The server response is not HTML")
            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    response.close()
                    raise ValueError("The page exceeds the 5 MB response limit")
                chunks.append(chunk)
            response.close()
            return BeautifulSoup(b"".join(chunks), "html.parser")
        raise requests.exceptions.TooManyRedirects("Too many redirects")
    except requests.exceptions.RequestException as exc:
        logger.error("Request failed for %s: %s", log_url(url), exc.__class__.__name__)
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
    if not href or href.startswith("#"):
        return None
    full_url = urljoin(page_url, href).split("#", 1)[0]
    parsed = urlparse(full_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return full_url


def get_page_title(soup: BeautifulSoup, default_url: str) -> str:
    title = safe_text(soup.title)
    if title:
        return title
    return safe_text(soup.select_one("h1")) or default_url


def collect_text(soup: BeautifulSoup) -> str:
    root = soup.select_one("main, article, .content, #content, .post, .entry") or soup.body or soup
    chunks = []
    for tag in root.select("h1, h2, h3, p, li, td, th"):
        text = safe_text(tag)
        if text and len(text) > 1:
            chunks.append(text)
    if not chunks:
        return safe_text(root) or ""
    return "\n".join(dict.fromkeys(chunks))


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
    next_link = soup.select_one("a[rel~='next'], a[aria-label*='next' i], a.next, a.pagination-next")
    if next_link:
        next_url = clean_url(next_link.get("href"), current_url)
        if next_url:
            return next_url

    for link in soup.select("a[href]"):
        label = (safe_text(link) or "").strip().lower()
        if label == ">" or label.startswith("next"):
            next_url = clean_url(link.get("href"), current_url)
            if next_url:
                return next_url

    parsed = urlparse(current_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    for index, (key, value) in enumerate(query):
        if key.lower() in {"page", "p", "pg"} and value.isdigit():
            query[index] = (key, str(int(value) + 1))
            return urlunparse(parsed._replace(query=urlencode(query)))
    match = re.search(r"(/page/)(\d+)(/?)$", parsed.path, re.IGNORECASE)
    if match:
        path = parsed.path[:match.start(2)] + str(int(match.group(2)) + 1) + match.group(3)
        return urlunparse(parsed._replace(path=path))

    return None


def parse_generic_page(soup: BeautifulSoup, page_url: str) -> ScrapedPage:
    return ScrapedPage(
        title=get_page_title(soup, page_url),
        url=page_url,
        text=collect_text(soup),
        links=collect_links(soup, page_url),
    )


def extract_page(soup: BeautifulSoup, page_url: str, selectors: dict[str, str] | None = None) -> dict:
    """Return normalized common page fields plus user-defined CSS selector fields."""
    result = asdict(parse_generic_page(soup, page_url))
    metadata = {"description": (soup.select_one('meta[name="description"]') or {}).get("content", ""),
                "keywords": (soup.select_one('meta[name="keywords"]') or {}).get("content", ""),
                "canonical": clean_url((soup.select_one('link[rel="canonical"]') or {}).get("href"), page_url),
                "open_graph": {tag.get("property", "")[3:]: tag.get("content", "")
                               for tag in soup.select('meta[property^="og:"][content]')}}
    tables = []
    for table in soup.select("table"):
        rows = [[safe_text(cell) or "" for cell in row.select("th, td")] for row in table.select("tr")]
        if rows:
            tables.append(rows)
    result.update({
        "headings": [safe_text(node) for node in soup.select("h1, h2, h3") if safe_text(node)],
        "link_details": [{"text": safe_text(node) or "", "url": clean_url(node.get("href"), page_url)}
                         for node in soup.select("a[href]") if clean_url(node.get("href"), page_url)],
        "images": [{"url": clean_url(node.get("src"), page_url), "alt": (node.get("alt") or "").strip()} for node in soup.select("img[src]")],
        "tables": tables,
        "metadata": metadata,
        "structured_data": [node.string for node in soup.select('script[type="application/ld+json"]') if node.string],
    })
    if selectors:
        selected = {}
        for name, selector in selectors.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(selector, str) or len(selector) > 500:
                raise ValueError("Each selector needs a field name and a CSS selector under 500 characters")
            try:
                nodes = soup.select(selector)
            except Exception as exc:
                raise ValueError(f"Invalid CSS selector for {name!r}") from exc
            values = [safe_text(node) for node in nodes if safe_text(node)]
            selected[name.strip()[:100]] = values[0] if len(values) == 1 else values
        result["fields"] = selected
    return result


def scrape_all(
    start_url: str,
    max_pages: Optional[int] = 1,
    delay_range: tuple[float, float] = DEFAULT_DELAY_RANGE,
    selectors: dict[str, str] | None = None,
    on_page=None,
    cancelled=None,
    errors: list[str] | None = None,
) -> list[dict]:
    current_url = validate_url(start_url)
    session = build_session()
    visited: set[str] = set()
    pages: list[dict] = []
    robots_cache: dict[str, object] = {}
    try:
        while current_url and current_url not in visited:
            if cancelled and cancelled():
                break
            if max_pages is not None and len(pages) >= max_pages:
                logger.info("Reached max_pages=%d limit.", max_pages)
                break
            visited.add(current_url)
            parsed = urlparse(current_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in robots_cache:
                from urllib.robotparser import RobotFileParser
                rules = RobotFileParser()
                rules.set_url(urljoin(origin, "/robots.txt"))
                try:
                    validate_url(rules.url)
                    robot_response = session.get(rules.url, timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True)
                    if robot_response.status_code == 200:
                        body = robot_response.raw.read(512_001)
                        rules.parse(body[:512_000].decode("utf-8", errors="replace").splitlines())
                    else:
                        rules.parse([])
                    robot_response.close()
                except (requests.exceptions.RequestException, ValueError):
                    rules.parse([])
                robots_cache[origin] = rules
            if not robots_cache[origin].can_fetch("WebScraper/1.0", current_url):
                logger.warning("robots.txt disallows %s", current_url)
                current_url = None
                continue
            if pages:
                time.sleep(random.uniform(*delay_range))
            logger.info("Fetching page %d: %s", len(pages) + 1, log_url(current_url))
            soup = fetch_page(session, current_url)
            if soup is None:
                if errors is not None:
                    errors.append(f"Unable to fetch {log_url(current_url)}")
                current_url = find_next_page_url(soup, current_url) if soup else None
                continue
            page_data = extract_page(soup, current_url, selectors)
            pages.append(page_data)
            if on_page:
                on_page(page_data, len(pages))
            next_url = find_next_page_url(soup, current_url)
            if (not next_url or next_url in visited
                    or urlparse(next_url).netloc.lower() != urlparse(start_url).netloc.lower()):
                break
            current_url = next_url
    finally:
        session.close()
    logger.info("Scrape complete: %d page(s) collected.", len(pages))
    return pages


def prepare_output(filepath: str) -> Path:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_csv(pages: list[ScrapedPage], filepath: str) -> None:
    path = prepare_output(filepath)
    rows = [asdict(page) if isinstance(page, ScrapedPage) else page for page in pages]
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()}
            writer.writerow(row)
    logger.info("Saved %d page(s) to %s", len(pages), path)


def save_json(pages: list[ScrapedPage], filepath: str) -> None:
    path = prepare_output(filepath)
    with path.open("w", encoding="utf-8") as output:
        json.dump([asdict(page) if isinstance(page, ScrapedPage) else page for page in pages], output, indent=2, ensure_ascii=False)
    logger.info("Saved %d page(s) to %s", len(pages), path)


def save_sqlite(pages: list[ScrapedPage], filepath: str) -> None:
    path = prepare_output(filepath)
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS scraped_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                links TEXT NOT NULL DEFAULT '',
                scraped_at TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}'
            )
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(scraped_pages)")}
        if "data" not in columns:
            connection.execute("ALTER TABLE scraped_pages ADD COLUMN data TEXT NOT NULL DEFAULT '{}'")
        connection.executemany(
            "INSERT INTO scraped_pages (title, url, text, links, scraped_at, data) VALUES (?, ?, ?, ?, ?, ?)",
            [(row.get("title", ""), row.get("url", ""), row.get("text", ""), " | ".join(row.get("links", [])),
              row.get("scraped_at", ""), json.dumps(row, ensure_ascii=False))
             for row in (asdict(page) if isinstance(page, ScrapedPage) else page for page in pages)],
        )
    logger.info("Saved %d page(s) to %s (table: scraped_pages)", len(pages), path)


SAVERS = {"csv": save_csv, "json": save_json, "sqlite": save_sqlite}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape page titles, text, and links from a website.")
    parser.add_argument("--url", required=True, help="Starting website URL (http or https)")
    parser.add_argument("--output-format", choices=SAVERS, default="json", help="Output format (default: json)")
    parser.add_argument("--output-file", help="Output file path (default: scraped_site.<format>)")
    parser.add_argument("--max-pages", type=int, default=1, help="Maximum pages to scrape; use 0 for no limit")
    parser.add_argument("--delay-min", type=float, default=DEFAULT_DELAY_RANGE[0], help="Minimum delay between page requests")
    parser.add_argument("--delay-max", type=float, default=DEFAULT_DELAY_RANGE[1], help="Maximum delay between page requests")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_pages < 0:
        logger.error("--max-pages must be zero or greater")
        return 2
    if args.delay_min < 0 or args.delay_max < args.delay_min:
        logger.error("Delay values must be non-negative and --delay-min must be <= --delay-max")
        return 2
    max_pages = args.max_pages or None
    extension = {"csv": "csv", "json": "json", "sqlite": "db"}[args.output_format]
    output_file = args.output_file or f"scraped_site.{extension}"
    try:
        pages = scrape_all(args.url, max_pages, (args.delay_min, args.delay_max))
        if not pages:
            logger.error("No pages were scraped from %s", args.url)
            return 1
        SAVERS[args.output_format](pages, output_file)
    except (ValueError, OSError, sqlite3.Error, requests.exceptions.RequestException) as exc:
        logger.error("Scraper failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
