import re
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

class DataCleaner:
    """
    Cleans, validates, transforms, and deduplicates extracted datasets.
    """

    @staticmethod
    def clean_text_trim(val: Any) -> Any:
        if isinstance(val, str):
            return " ".join(val.split())
        return val

    @staticmethod
    def clean_strip_html(val: Any) -> Any:
        if isinstance(val, str):
            clean = re.sub(r"<[^>]+>", "", val)
            return " ".join(clean.split())
        return val

    @staticmethod
    def clean_to_lower(val: Any) -> Any:
        if isinstance(val, str):
            return val.lower()
        return val

    @staticmethod
    def clean_to_upper(val: Any) -> Any:
        if isinstance(val, str):
            return val.upper()
        return val

    @staticmethod
    def clean_to_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        if isinstance(val, int):
            return val
        s = str(val).replace(",", "").strip()
        # Find numeric sequence
        m = re.search(r"[-+]?\d+", s)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def clean_to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace(",", "").strip()
        # Find floating point pattern
        m = re.search(r"[-+]?\d*\.?\d+", s)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def clean_to_date(val: Any) -> Optional[str]:
        """Attempts to parse common date formats into ISO 8601 YYYY-MM-DD string."""
        if not val or not isinstance(val, str):
            return None
        s = val.strip()
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Fallback: check if standard ISO date is inside text
        iso_m = re.search(r"\b\d{4}-\d{2}-\d{2}\b", s)
        if iso_m:
            return iso_m.group(0)
        return s

    @staticmethod
    def clean_normalize_url(val: Any) -> Any:
        if not val or not isinstance(val, str):
            return val
        try:
            parsed = urlparse(val.strip())
            # Lowercase scheme & host, strip trailing slash in path if empty
            path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
            clean_url = urlunparse((
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                parsed.params,
                parsed.query,
                ""  # Strip fragment anchor
            ))
            return clean_url
        except Exception:
            return val

    @classmethod
    def apply_rule(cls, val: Any, action: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        if val is None:
            return None

        if isinstance(val, list):
            return [cls.apply_rule(item, action, params) for item in val]

        if action == "trim":
            return cls.clean_text_trim(val)
        elif action == "strip_html":
            return cls.clean_strip_html(val)
        elif action == "to_lower":
            return cls.clean_to_lower(val)
        elif action == "to_upper":
            return cls.clean_to_upper(val)
        elif action == "to_int":
            return cls.clean_to_int(val)
        elif action == "to_float":
            return cls.clean_to_float(val)
        elif action == "to_date":
            return cls.clean_to_date(val)
        elif action == "normalize_url":
            return cls.clean_normalize_url(val)
        elif action == "regex_replace":
            pattern = params.get("pattern", "")
            replacement = params.get("replacement", "")
            if pattern and isinstance(val, str):
                return re.sub(pattern, replacement, val)
            return val
        return val

    @classmethod
    def clean_record(cls, record_data: Dict[str, Any], rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Applies configured cleaning rules across a single record dictionary."""
        cleaned = dict(record_data)
        if not rules:
            # Default auto-clean: trim all strings
            for k, v in cleaned.items():
                cleaned[k] = cls.clean_text_trim(v)
            return cleaned

        for r in rules:
            field_name = r.get("field_name")
            action = r.get("action")
            params = r.get("params", {})
            if field_name in cleaned and action:
                cleaned[field_name] = cls.apply_rule(cleaned[field_name], action, params)

        return cleaned

    @classmethod
    def compute_content_hash(cls, data: Dict[str, Any], keys: Optional[List[str]] = None) -> str:
        """Computes deterministic SHA-256 hash of record values or specific key subset."""
        if keys:
            subset = {k: data.get(k) for k in keys if k in data}
        else:
            subset = data
        raw_json = json.dumps(subset, sort_keys=True, default=str)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    @classmethod
    def deduplicate_records(
        cls,
        records: List[Dict[str, Any]],
        dedup_keys: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Deduplicates a list of records based on key fields or full content hash.
        Returns (unique_records, duplicate_count).
        """
        seen_hashes = set()
        unique = []
        dup_count = 0

        for r in records:
            h = cls.compute_content_hash(r, dedup_keys)
            if h in seen_hashes:
                dup_count += 1
            else:
                seen_hashes.add(h)
                unique.append(r)

        return unique, dup_count
