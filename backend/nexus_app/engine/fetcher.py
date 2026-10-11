import time
import httpx
from typing import Optional, Dict, Any, Tuple, List
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urljoin
import logging

from nexus_app.security.ssrf import validate_url, validate_redirect, SSRFSecurityError
from nexus_app.config import settings

logger = logging.getLogger("nexus.engine.fetcher")

class FetchResult:
    def __init__(
        self,
        url: str,
        status_code: int,
        content: str,
        content_type: str,
        headers: Dict[str, str],
        elapsed_seconds: float,
        redirected_url: Optional[str] = None
    ):
        self.url = url
        self.status_code = status_code
        self.content = content
        self.content_type = content_type
        self.headers = headers
        self.elapsed_seconds = elapsed_seconds
        self.redirected_url = redirected_url or url

class SecureFetcher:
    """
    Polite and secure HTTP fetcher.
    - Strictly blocks SSRF targets
    - Validates each redirect hop
    - Enforces response size bounds
    - Checks robots.txt
    - Honors crawl delays and rate limits
    """

    def __init__(self, user_agent: Optional[str] = None, timeout: Optional[int] = None):
        self.user_agent = user_agent or settings.USER_AGENT
        self.timeout = timeout or settings.REQUEST_TIMEOUT_SECONDS
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.last_domain_request: Dict[str, float] = {}

    def get_robots_parser(self, url: str) -> Tuple[Optional[RobotFileParser], List[str]]:
        """Fetches and parses robots.txt for the given target host safely."""
        parsed = urlparse(url)
        base_host = f"{parsed.scheme}://{parsed.netloc}"
        if base_host in self.robots_cache:
            rp = self.robots_cache[base_host]
            sitemaps = getattr(rp, "sitemaps", []) or []
            return rp, sitemaps

        robots_url = f"{base_host}/robots.txt"
        sitemaps: List[str] = []
        rp = RobotFileParser()

        try:
            # Validate robots.txt URL against SSRF
            validate_url(robots_url)
            with httpx.Client(
                timeout=5.0,
                headers={"User-Agent": self.user_agent},
                follow_redirects=False
            ) as client:
                res = client.get(robots_url)
                if res.status_code == 200:
                    lines = res.text.splitlines()
                    rp.parse(lines)
                    for line in lines:
                        if line.strip().lower().startswith("sitemap:"):
                            parts = line.split(":", 1)
                            if len(parts) == 2 and parts[1].strip():
                                sitemaps.append(parts[1].strip())
                else:
                    rp.allow_all = True
        except Exception as e:
            logger.debug(f"Unable to fetch robots.txt for {base_host}: {e}")
            rp.allow_all = True

        self.robots_cache[base_host] = rp
        return rp, sitemaps

    def is_url_allowed_by_robots(self, url: str) -> Tuple[bool, Optional[float]]:
        """Checks if URL is allowed and returns (is_allowed, crawl_delay)."""
        rp, _ = self.get_robots_parser(url)
        if not rp:
            return True, None
        
        # Check standard robotparser
        is_allowed = rp.can_fetch(self.user_agent, url)
        # Check crawl-delay if available
        delay = None
        try:
            delay = rp.crawl_delay(self.user_agent)
        except Exception:
            pass
        return is_allowed, delay

    def _apply_domain_rate_limit(self, domain: str, delay: float):
        """Ensures delay between requests to the same domain."""
        now = time.time()
        last_req = self.last_domain_request.get(domain, 0.0)
        elapsed = now - last_req
        if elapsed < delay:
            sleep_needed = delay - elapsed
            time.sleep(sleep_needed)
        self.last_domain_request[domain] = time.time()

    def fetch(
        self,
        url: str,
        custom_headers: Optional[Dict[str, str]] = None,
        crawl_delay: Optional[float] = None
    ) -> FetchResult:
        """
        Executes an SSRF-safe HTTP GET request with streaming size control.
        """
        # Step 1: Pre-validation of starting URL
        validate_url(url)

        parsed = urlparse(url)
        domain = parsed.netloc

        # Step 2: Rate limit
        effective_delay = crawl_delay if crawl_delay is not None else settings.DEFAULT_CRAWL_DELAY_SECONDS
        self._apply_domain_rate_limit(domain, effective_delay)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if custom_headers:
            headers.update(custom_headers)

        start_time = time.time()
        current_url = url
        max_redirects = 5

        # Manual redirect following to guarantee SSRF validation on every redirect step
        for _ in range(max_redirects):
            with httpx.Client(
                timeout=self.timeout,
                headers=headers,
                follow_redirects=False
            ) as client:
                response = client.get(current_url)

                # Check redirect
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        break
                    # Revalidate redirect URL against SSRF
                    current_url = validate_redirect(location, current_url)
                    continue

                # Streamed size check
                content_bytes = bytearray()
                max_bytes = settings.MAX_RESPONSE_SIZE_BYTES

                for chunk in response.iter_bytes():
                    content_bytes.extend(chunk)
                    if len(content_bytes) > max_bytes:
                        raise ValueError(f"Response size exceeded hard cap of {max_bytes} bytes.")

                elapsed = time.time() - start_time
                content_type = response.headers.get("content-type", "")
                
                # Decode text
                encoding = response.encoding or "utf-8"
                try:
                    text_content = content_bytes.decode(encoding, errors="replace")
                except Exception:
                    text_content = content_bytes.decode("utf-8", errors="replace")

                return FetchResult(
                    url=url,
                    status_code=response.status_code,
                    content=text_content,
                    content_type=content_type,
                    headers=dict(response.headers),
                    elapsed_seconds=elapsed,
                    redirected_url=current_url
                )

        raise ValueError("Exceeded maximum redirect hops.")
