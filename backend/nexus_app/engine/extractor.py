import re
import json
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
import lxml.html
import logging

logger = logging.getLogger("nexus.engine.extractor")

class ExtractorEngine:
    """
    Extracts structured data from HTML via CSS selectors, XPath expressions,
    JSON-LD, Meta tags, and Regex patterns.
    """

    def __init__(self, html: str, base_url: str = ""):
        self.html = html
        self.base_url = base_url
        self.soup = BeautifulSoup(html, "html.parser")
        try:
            self.lxml_tree = lxml.html.fromstring(html)
        except Exception:
            self.lxml_tree = None

    def get_page_metadata(self) -> Dict[str, Any]:
        """Extracts standard page title, meta tags, and OpenGraph metadata."""
        meta: Dict[str, Any] = {}
        title_tag = self.soup.find("title")
        meta["title"] = title_tag.get_text(strip=True) if title_tag else ""

        for tag in self.soup.find_all("meta"):
            name = tag.get("name") or tag.get("property")
            content = tag.get("content")
            if name and content:
                meta[name.strip()] = content.strip()

        return meta

    def get_json_ld(self) -> List[Dict[str, Any]]:
        """Extracts all JSON-LD structured schemas from the document."""
        schemas = []
        for script in self.soup.find_all("script", type="application/ld+json"):
            try:
                content = script.string
                if content:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        schemas.extend(parsed)
                    elif isinstance(parsed, dict):
                        schemas.append(parsed)
            except Exception as e:
                logger.debug(f"Failed to parse JSON-LD script: {e}")
        return schemas

    def get_all_links(self) -> List[str]:
        """Extracts all valid absolute href links from the document."""
        links = set()
        for a in self.soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            full_url = urljoin(self.base_url, href) if self.base_url else href
            links.add(full_url)
        return sorted(list(links))

    def _extract_from_element(
        self,
        element: Any,
        extract_type: str = "text",
        attribute_name: Optional[str] = None,
        regex_pattern: Optional[str] = None
    ) -> Optional[str]:
        """Extracts the desired value from a single DOM/Soup element."""
        if element is None:
            return None

        val = ""
        if isinstance(element, Tag):
            if extract_type == "text":
                val = element.get_text(separator=" ", strip=True)
            elif extract_type == "html":
                val = str(element)
            elif extract_type == "attr":
                attr = attribute_name or "href"
                val = element.get(attr, "")
                if isinstance(val, list):
                    val = " ".join(val)
                # Resolve relative URLs for common attributes
                if self.base_url and attr in ("href", "src", "action", "data-src"):
                    val = urljoin(self.base_url, str(val))
            else:
                val = element.get_text(strip=True)
        elif isinstance(element, (str, bytes)):
            val = str(element).strip()
            if self.base_url and attribute_name in ("href", "src"):
                val = urljoin(self.base_url, val)
        else:
            # lxml element
            try:
                if extract_type == "text":
                    val = element.text_content().strip()
                elif extract_type == "html":
                    val = lxml.html.tostring(element, encoding="unicode").strip()
                elif extract_type == "attr":
                    attr = attribute_name or "href"
                    val = element.get(attr, "")
                    if self.base_url and attr in ("href", "src"):
                        val = urljoin(self.base_url, str(val))
                else:
                    val = element.text_content().strip()
            except Exception:
                val = str(element)

        if regex_pattern and val:
            match = re.search(regex_pattern, str(val))
            if match:
                val = match.group(1) if match.groups() else match.group(0)
            else:
                return None

        return str(val) if val is not None else None

    def extract_field(
        self,
        selector: str,
        selector_type: str = "css",
        extract_type: str = "text",
        attribute_name: Optional[str] = None,
        is_multiple: bool = False,
        regex_pattern: Optional[str] = None,
        default_value: Optional[str] = None
    ) -> Union[Optional[str], List[str]]:
        """
        Extracts a specific field value using CSS or XPath.
        """
        try:
            if selector_type == "css":
                if is_multiple:
                    elements = self.soup.select(selector)
                    results = []
                    for el in elements:
                        val = self._extract_from_element(el, extract_type, attribute_name, regex_pattern)
                        if val is not None:
                            results.append(val)
                    return results if results else ([default_value] if default_value is not None else [])
                else:
                    el = self.soup.select_one(selector)
                    val = self._extract_from_element(el, extract_type, attribute_name, regex_pattern)
                    return val if val is not None else default_value

            elif selector_type == "xpath":
                if self.lxml_tree is None:
                    return [] if is_multiple else default_value
                elements = self.lxml_tree.xpath(selector)
                if not isinstance(elements, list):
                    elements = [elements]

                if is_multiple:
                    results = []
                    for el in elements:
                        val = self._extract_from_element(el, extract_type, attribute_name, regex_pattern)
                        if val is not None:
                            results.append(val)
                    return results if results else ([default_value] if default_value is not None else [])
                else:
                    el = elements[0] if elements else None
                    val = self._extract_from_element(el, extract_type, attribute_name, regex_pattern)
                    return val if val is not None else default_value

            elif selector_type == "jsonld":
                schemas = self.get_json_ld()
                # selector can be a key path e.g. "name" or "headline"
                for item in schemas:
                    if selector in item:
                        val = str(item[selector])
                        return [val] if is_multiple else val
                return [] if is_multiple else default_value

        except Exception as e:
            logger.warning(f"Error evaluating selector '{selector}' ({selector_type}): {e}")
            return [] if is_multiple else default_value

        return [] if is_multiple else default_value

    def extract_record_list(
        self,
        container_selector: str,
        container_type: str = "css",
        fields: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts a list of records (e.g. repeated product cards or table rows)
        by evaluating child selectors within each matching container element.
        """
        records = []
        fields = fields or []

        if container_type == "css":
            containers = self.soup.select(container_selector)
            for container in containers:
                rec: Dict[str, Any] = {}
                container_soup = BeautifulSoup(str(container), "html.parser")
                sub_engine = ExtractorEngine(str(container), base_url=self.base_url)
                for f in fields:
                    field_name = f.get("name")
                    sel = f.get("selector", "")
                    sel_type = f.get("selector_type", "css")
                    ext_type = f.get("extract_type", "text")
                    attr = f.get("attribute_name")
                    is_mult = f.get("is_multiple", False)
                    reg = f.get("regex_pattern")
                    def_val = f.get("default_value")

                    val = sub_engine.extract_field(
                        selector=sel,
                        selector_type=sel_type,
                        extract_type=ext_type,
                        attribute_name=attr,
                        is_multiple=is_mult,
                        regex_pattern=reg,
                        default_value=def_val
                    )
                    rec[field_name] = val
                records.append(rec)
        return records
