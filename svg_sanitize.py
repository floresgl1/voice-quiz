"""Whitelist-based sanitizer for model-generated SVG circuit diagrams.

Claude returns inline SVG in the `diagram` field of a question. That markup is
untrusted, so it is parsed and rebuilt from a whitelist before it ever reaches
the browser: anything not on the list (scripts, event handlers, foreignObject,
external references) is dropped. Malformed SVG is rejected outright rather than
handed to the frontend half-broken.
"""

import re
import xml.etree.ElementTree as ET

MAX_SVG_BYTES = 60_000

SVG_NS = "http://www.w3.org/2000/svg"

ALLOWED_TAGS = {
    "svg", "g", "defs", "title", "desc", "use", "symbol", "marker",
    "path", "line", "polyline", "polygon", "rect", "circle", "ellipse",
    "text", "tspan",
}

ALLOWED_ATTRS = {
    "viewbox", "width", "height", "preserveaspectratio",
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "d", "points", "transform", "class", "id",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset",
    "opacity", "vector-effect",
    "font-size", "font-family", "font-weight", "font-style",
    "text-anchor", "dominant-baseline", "letter-spacing",
    "marker-start", "marker-mid", "marker-end",
    "markerwidth", "markerheight", "refx", "refy", "orient", "markerunits",
    "overflow", "href",
}

# Attribute values may reference other nodes in the same document, nothing else.
_LOCAL_REF = re.compile(r"^(#[\w:.-]+|url\(\s*#[\w:.-]+\s*\))$")
_REF_ATTRS = {"href", "marker-start", "marker-mid", "marker-end", "fill", "stroke"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


_CANONICAL = {
    "viewbox": "viewBox",
    "preserveaspectratio": "preserveAspectRatio",
    "markerwidth": "markerWidth",
    "markerheight": "markerHeight",
    "refx": "refX",
    "refy": "refY",
    "markerunits": "markerUnits",
}


def _clean_attrs(elem: ET.Element) -> dict:
    out = {}
    for name, value in elem.attrib.items():
        local = _local_name(name).lower()
        if local not in ALLOWED_ATTRS:
            continue
        value = value.strip()
        lowered = value.lower()
        if "javascript:" in lowered or "data:" in lowered or "<" in value:
            continue
        if local in _REF_ATTRS and ("#" in value or "url(" in lowered):
            if not _LOCAL_REF.match(value):
                continue
        # Re-emit with the canonical camelCase spelling SVG expects.
        out[_CANONICAL.get(local, local)] = value
    return out


def _rebuild(elem: ET.Element) -> ET.Element | None:
    tag = _local_name(elem.tag).lower()
    if tag not in ALLOWED_TAGS:
        return None

    clean = ET.Element(tag, _clean_attrs(elem))
    clean.text = elem.text
    clean.tail = elem.tail
    for child in elem:
        rebuilt = _rebuild(child)
        if rebuilt is not None:
            clean.append(rebuilt)
    return clean


def sanitize_svg(raw: str | None) -> str | None:
    """Return safe inline SVG markup, or None if the input is unusable."""
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip()
    # Models sometimes wrap the SVG in a code fence.
    fence = re.match(r"^```(?:svg|xml|html)?\s*\n([\s\S]*?)\n?```$", raw)
    if fence:
        raw = fence.group(1).strip()

    start = raw.find("<svg")
    end = raw.rfind("</svg>")
    if start == -1 or end == -1:
        return None
    raw = raw[start:end + len("</svg>")]

    if len(raw.encode("utf-8")) > MAX_SVG_BYTES:
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    if _local_name(root.tag).lower() != "svg":
        return None

    clean = _rebuild(root)
    if clean is None:
        return None

    clean.set("xmlns", SVG_NS)
    if "viewBox" not in clean.attrib:
        return None
    # Let CSS own the on-screen size; the viewBox carries the aspect ratio.
    clean.attrib.pop("width", None)
    clean.attrib.pop("height", None)
    clean.tail = None

    return ET.tostring(clean, encoding="unicode")
