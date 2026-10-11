import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Any, Set, Optional, Callable
import logging

from nexus_app.engine.fetcher import SecureFetcher, FetchResult
from nexus_app.engine.browser import BrowserWorker
from nexus_app.engine.extractor import ExtractorEngine
from nexus_app.security.ssrf import validate_url
from nexus_app.config import settings

logger = logging.getLogger("nexus.engine.crawler")

class CrawlPageItem:
    def __init__(self, url: str, data: Dict[str, Any], status_code: int, error: Optional[str] = None):
        self.url = url
        self.data = data
        self.status_code = status_code
        self.error = error

class CrawlerCoordinator:
    """
    Coordinates multi-page crawls, sitemap discovery, same-domain pagination,
    and structured field extraction across pages.
    """

    def __init__(
        self,
        starting_urls: List[str],
        selectors: List[Dict[str, Any]],
        extraction_mode: str = "http",
        max_pages: int = 10,
        max_depth: int = 2,
        crawl_delay: float = 1.0,
        same_domain_only: bool = True,
        user_agent: Optional[str] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        self.starting_urls = starting_urls
        self.selectors = selectors
        self.extraction_mode = extraction_mode
        self.max_pages = min(max_pages, settings.MAX_PAGES_HARD_LIMIT)
        self.max_depth = max_depth
        self.crawl_delay = crawl_delay
        self.same_domain_only = same_domain_only
        self.log_callback = log_callback or (lambda lvl, msg: None)
        self.progress_callback = progress_callback or (lambda curr, total: None)

        self.fetcher = SecureFetcher(user_agent=user_agent)
        self.browser_worker = BrowserWorker() if extraction_mode == "browser" else None

        self.visited_urls: Set[str] = set()
        self.allowed_domains: Set[str] = set()
        for u in starting_urls:
            try:
                p = urlparse(u)
                if p.netloc:
                    self.allowed_domains.add(p.netloc.lower())
            except Exception:
                pass

    def log(self, level: str, message: str):
        logger.info(f"[{level}] {message}")
        self.log_callback(level, message)

    def discover_sitemap_urls(self, base_url: str) -> List[str]:
        """Tries to find and parse sitemap.xml to discover seed URLs."""
        urls: List[str] = []
        rp, discovered_sitemaps = self.fetcher.get_robots_parser(base_url)
        sitemap_candidates = list(discovered_sitemaps)
        parsed = urlparse(base_url)
        default_sitemap = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        if default_sitemap not in sitemap_candidates:
            sitemap_candidates.append(default_sitemap)

        for sm_url in sitemap_candidates[:3]:
            try:
                self.log("INFO", f"Checking sitemap at {sm_url}")
                res = self.fetcher.fetch(sm_url, crawl_delay=self.crawl_delay)
                if res.status_code == 200 and ("xml" in res.content_type or "<urlset" in res.content or "<sitemapindex" in res.content):
                    root = ET.fromstring(res.content)
                    # Handle XML namespaces
                    for elem in root.iter():
                        if elem.tag.endswith("loc") and elem.text:
                            loc_url = elem.text.strip()
                            if loc_url.startswith("http"):
                                urls.append(loc_url)
                    self.log("INFO", f"Discovered {len(urls)} URLs from sitemap {sm_url}")
                    break
            except Exception as e:
                logger.debug(f"Sitemap lookup failed for {sm_url}: {e}")
        return urls

    def is_url_crawlable(self, target_url: str) -> bool:
        """Determines whether a link is allowed under current crawl rules."""
        if target_url in self.visited_urls:
            return False

        try:
            validate_url(target_url)
        except Exception:
            return False

        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return False

        if self.same_domain_only and parsed.netloc.lower() not in self.allowed_domains:
            return False

        # Exclude typical binary assets
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".zip", ".tar", ".mp4", ".mp3", ".exe"]):
            return False

        # Check robots.txt
        is_allowed, _ = self.fetcher.is_url_allowed_by_robots(target_url)
        if not is_allowed:
            self.log("WARNING", f"URL {target_url} blocked by site's robots.txt. Skipping.")
            return False

        return True

    def run_crawl(self, should_cancel: Optional[Callable[[], bool]] = None) -> List[CrawlPageItem]:
        """
        Executes the crawl BFS loop, extracting configured fields per page.
        """
        results: List[CrawlPageItem] = []
        queue: List[tuple[str, int]] = []  # (url, depth)

        for u in self.starting_urls:
            queue.append((u, 0))

        # Optional sitemap augmentation if starting from root
        if len(self.starting_urls) == 1 and self.max_pages > 1:
            try:
                sitemap_links = self.discover_sitemap_urls(self.starting_urls[0])
                for sm_link in sitemap_links[:self.max_pages]:
                    if sm_link not in [q[0] for q in queue]:
                        queue.append((sm_link, 1))
            except Exception as e:
                self.log("INFO", f"Sitemap discovery skipped: {e}")

        self.log("INFO", f"Starting crawl with {len(queue)} seed URLs. Max pages: {self.max_pages}, Mode: {self.extraction_mode}")

        while queue and len(self.visited_urls) < self.max_pages:
            if should_cancel and should_cancel():
                self.log("WARNING", "Job cancellation requested by user. Terminating crawl loop.")
                break

            current_url, depth = queue.pop(0)
            if current_url in self.visited_urls:
                continue

            # Respect robots.txt
            if not self.is_url_crawlable(current_url) and current_url not in self.starting_urls:
                continue

            self.visited_urls.add(current_url)
            self.log("INFO", f"Scraping [{len(self.visited_urls)}/{self.max_pages}]: {current_url}")
            self.progress_callback(len(self.visited_urls), self.max_pages)

            html_content = ""
            status_code = 200
            error_msg = None

            try:
                if self.extraction_mode == "browser" and self.browser_worker:
                    html_content = self.browser_worker.render_page(current_url)
                else:
                    fetch_res = self.fetcher.fetch(current_url, crawl_delay=self.crawl_delay)
                    status_code = fetch_res.status_code
                    html_content = fetch_res.content

                if status_code >= 400:
                    self.log("WARNING", f"HTTP {status_code} returned for {current_url}")
                    results.append(CrawlPageItem(url=current_url, data={}, status_code=status_code, error=f"HTTP status {status_code}"))
                    continue

                # Parse & Extract
                extractor = ExtractorEngine(html_content, base_url=current_url)
                page_data: Dict[str, Any] = {}

                for s in self.selectors:
                    field_name = s.get("name")
                    sel = s.get("selector", "")
                    sel_type = s.get("selector_type", "css")
                    ext_type = s.get("extract_type", "text")
                    attr = s.get("attribute_name")
                    is_mult = s.get("is_multiple", False)
                    reg = s.get("regex_pattern")
                    def_val = s.get("default_value")

                    val = extractor.extract_field(
                        selector=sel,
                        selector_type=sel_type,
                        extract_type=ext_type,
                        attribute_name=attr,
                        is_multiple=is_mult,
                        regex_pattern=reg,
                        default_value=def_val
                    )
                    page_data[field_name] = val

                results.append(CrawlPageItem(url=current_url, data=page_data, status_code=status_code))
                self.log("INFO", f"Extracted {len(page_data)} fields from {current_url}")

                # Queue next links if depth allows
                if depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                    new_links = extractor.get_all_links()
                    for link in new_links:
                        if self.is_url_crawlable(link):
                            queue.append((link, depth + 1))

            except Exception as e:
                error_msg = str(e)
                self.log("ERROR", f"Failed fetching {current_url}: {error_msg}")
                results.append(CrawlPageItem(url=current_url, data={}, status_code=0, error=error_msg))

        self.progress_callback(len(self.visited_urls), self.max_pages)
        self.log("INFO", f"Crawl finished. Processed {len(self.visited_urls)} pages, collected {len(results)} records.")
        return results
