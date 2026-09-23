"""Website adapter: extract NAP and schema from website HTML.

Uses trafilatura for text extraction, BeautifulSoup for structured parsing,
and extruct for JSON-LD extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_JSON_LD_GRAPH = "@graph"

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebsiteNAPData:
    """Extracted NAP data from a website page."""

    url: str = ""
    name: str = ""
    address_raw: str = ""
    phone_raw: str = ""
    email: str = ""
    schema_blocks: list[dict[str, Any]] = field(default_factory=list)
    schema_entities: list[dict[str, Any]] = field(default_factory=list)
    page_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "address_raw": self.address_raw,
            "phone_raw": self.phone_raw,
            "email": self.email,
            "schema_entities": self.schema_entities,
        }


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------


def extract_nap_from_html(html: str, url: str = "") -> dict[str, Any]:
    """Extract NAP and schema from website HTML.

    Returns dict with name, address, phones, email, page_text, and schema.
    Compatible with the pipeline's expected output format.
    """
    import trafilatura
    from bs4 import BeautifulSoup

    # Text extraction via trafilatura
    page_text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""

    soup = BeautifulSoup(html, "html.parser")

    # Name extraction
    name = _extract_name(soup)

    # Address extraction
    address_raw = _extract_address(soup, page_text)

    # Phone extraction
    phone_raw = _extract_phone(soup, page_text)

    # Email extraction
    email = _extract_email(soup, page_text)

    # Schema extraction
    schema_blocks = _extract_schema_blocks(soup)
    schema_entities = _extract_localbusiness_entities(schema_blocks)

    # Normalize with project utilities
    from ..address import normalize_address
    from ..phone import normalize_phone

    phones = []
    if phone_raw:
        phones.append(normalize_phone(phone_raw, source="visible_page"))

    address = normalize_address(address_raw) if address_raw else None

    return {
        "url": url,
        "source_url": url,
        "name": name,
        "address": address,
        "address_raw": address_raw,
        "address_normalized": address.normalized if address else "",
        "phones": phones,
        "phone_e164": phones[0].e164 if phones else "",
        "phone_raw": phone_raw,
        "email": email,
        "page_text": page_text,
        "schema_blocks": schema_blocks,
        "schema_entities": schema_entities,
    }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _extract_name(soup: Any) -> str:
    """Extract business name from page."""
    return (
        _name_from_schema(soup)
        or _name_from_open_graph(soup)
        or _name_from_title(soup)
        or _name_from_heading(soup)
    )


def _name_from_schema(soup: Any) -> str:
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("name"):
                return data["name"]
            if isinstance(data, dict) and data.get(_JSON_LD_GRAPH):
                for item in data[_JSON_LD_GRAPH]:
                    if isinstance(item, dict) and item.get("name"):
                        return item["name"]
        except (json.JSONDecodeError, KeyError):
            pass
    return ""


def _name_from_open_graph(soup: Any) -> str:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    return ""


def _name_from_title(soup: Any) -> str:
    title_tag = soup.find("title")
    if not title_tag or not title_tag.string:
        return ""
    title = title_tag.string.strip()
    for sep in ("|", "-", "—", "–", ":"):
        if sep in title:
            return title.split(sep)[0].strip()
    return title


def _name_from_heading(soup: Any) -> str:
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _extract_address(soup: Any, page_text: str) -> str:
    """Extract address from page HTML and text."""
    # Check <address> tag
    addr_tag = soup.find("address")
    if addr_tag:
        text = addr_tag.get_text(separator=" ", strip=True)
        if text and len(text) > 5:
            return text

    # Look for address-like patterns in structured content
    for selector in ('[class*="address"]', '[class*="location"]',
                     '[class*="contact"]', '[itemprop="address"]'):
        for tag in soup.select(selector):
            text = tag.get_text(separator=" ", strip=True)
            if _looks_like_address(text):
                return text

    # Fallback: scan page text for address-like patterns
    import re
    # NZ address pattern: number + street + locality + postal code
    patterns = [
        r"\d+[\w\s-]+(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Crt|Ct|Place|Pl|Terrace|Tce|Parade|Pde)[\w\s,]+(?:\d{4})",
        r"\d+[\w\s-]+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Dr)[\w\s,]+(?:Auckland|Wellington|Christchurch|Hamilton|Tauranga|Dunedin|Napier|Nelson|Rotorua|Invercargill)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, re.I)
        if match:
            return match.group(0).strip()

    return ""


def _looks_like_address(text: str) -> bool:
    """Heuristic check if text looks like a postal address."""
    indicators = (
        "street", "st ", "rd ", "road", "avenue", "ave ", "boulevard",
        "lane", "drive", "court", "place", "terrace", "parade",
        "new zealand", "nz ", "auckland", "wellington", "christchurch",
    )
    lower = text.lower()
    count = sum(1 for kw in indicators if kw in lower)
    return count >= 2


def _extract_phone(soup: Any, page_text: str) -> str:
    """Extract phone number from page."""
    # Check tel: links
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").lower()
        if href.startswith("tel:"):
            phone = href[4:].strip()
            if phone:
                return phone

    # Check common phone patterns in text
    import re
    # NZ mobile: 02X XXX XXXX or +64 2X XXX XXXX
    # NZ landline: 0X XXX XXXX or +64 X XXX XXXX
    patterns = [
        r"\+64\s?\d[\s-]?\d{3}[\s-]?\d{3,4}",
        r"0\d[\s-]?\d{3}[\s-]?\d{3,4}",
        r"\(\d{2}\)\s?\d{3,4}[\s-]?\d{3,4}",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return match.group(0).strip()

    # Check common phone-containing elements
    for selector in ('[class*="phone"]', '[class*="tel"]', '[itemprop="telephone"]'):
        for tag in soup.select(selector):
            text = tag.get_text(strip=True)
            if re.search(r"\d{7,}", text):
                return text.strip()

    return ""


def _extract_email(soup: Any, page_text: str) -> str:
    """Extract email from page."""
    # Check mailto: links
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").lower()
        if href.startswith("mailto:"):
            email = href[7:].strip()
            if "@" in email:
                return email

    # Check email patterns in text
    import re
    match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
        page_text,
    )
    if match:
        return match.group(0)

    return ""


def _extract_schema_blocks(soup: Any) -> list[dict[str, Any]]:
    """Extract all JSON-LD script blocks."""
    import json

    blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                blocks.append(data)
            elif isinstance(data, list):
                blocks.extend(data)
        except json.JSONDecodeError:
            pass
    return blocks


def _extract_localbusiness_entities(
    schema_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter schema blocks to only LocalBusiness/Organization types."""
    from ..local_schema import _to_list

    local_types = frozenset({
        "LocalBusiness", "Organization", "Restaurant", "Dentist",
        "Physician", "Store", "ProfessionalService",
    })

    entities: list[dict[str, Any]] = []
    for block in schema_blocks:
        types = _to_list(block.get("@type", []))
        if any(t in local_types for t in types):
            entities.append(block)
        elif _JSON_LD_GRAPH in block:
            for item in block[_JSON_LD_GRAPH]:
                item_types = _to_list(item.get("@type", []))
                if any(t in local_types for t in item_types):
                    entities.append(item)
    return entities
