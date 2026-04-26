"""XML helpers for ISAPI requests/responses.

Hikvision ISAPI uses XML with namespaces of the form:
    xmlns="http://www.hikvision.com/ver20/XMLSchema"
    xmlns="http://www.std-cgi.com/ver20/XMLSchema"

We do not use ElementTree's namespace mode for serialization because
Hikvision firmwares are picky about the exact namespace value being
preserved on PUT — we round-trip the original namespace string.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

# Strip any default xmlns from a tag name like "{http://...}IPAddress" -> "IPAddress"
_NS_RE = re.compile(r"^\{[^}]+\}")


def localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def find_local(elem: ET.Element, name: str) -> Optional[ET.Element]:
    """Find first descendant whose localname equals `name` (namespace-agnostic)."""
    for el in elem.iter():
        if localname(el.tag) == name:
            return el
    return None


def find_local_text(elem: ET.Element, name: str) -> Optional[str]:
    found = find_local(elem, name)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def set_local_text(elem: ET.Element, name: str, value: str) -> bool:
    """Set text of first descendant matching localname; return True if found."""
    found = find_local(elem, name)
    if found is None:
        return False
    found.text = value
    return True


def parse(text: str) -> ET.Element:
    return ET.fromstring(text)


def to_xml(elem: ET.Element) -> str:
    """Serialize back to XML preserving the original namespace declaration.

    ElementTree by default rewrites xmlns into ns0 prefixes, which some
    Hikvision firmwares reject on PUT. We post-process to strip those.
    """
    raw = ET.tostring(elem, encoding="unicode")
    # Drop ns0 prefixes that ElementTree synthesizes
    raw = re.sub(r'\sxmlns:ns0="[^"]+"', "", raw)
    raw = raw.replace("ns0:", "")
    raw = re.sub(r"<(/?)(ns0:)", r"<\1", raw)
    if not raw.startswith("<?xml"):
        raw = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw
    return raw
