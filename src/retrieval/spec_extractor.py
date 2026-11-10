import json
import re
from collections import Counter
from pathlib import Path

try:
    from src.retrieval.value_parser import parse_value
except ModuleNotFoundError:
    from value_parser import parse_value


PROCESSED_DIR = Path("data/processed")

STANDARD_MARKER = "•"
OPTIONAL_MARKER = "º"
MARKERS = {STANDARD_MARKER, OPTIONAL_MARKER}
UNKNOWN_MARKER = "�"


NOISE_ATTRIBUTES = {
    "term",
    "explanation",
    "designation",
    "material",
    "number",
    "key",
    "item",
    "label",
    "meaning",
    "position",
    "action",
    "status",
    "indicator",
    "color",
    "display",
    "description",
    "note",
    "warning",
    "caution",
    "danger",
    "page",
    "important information",
    "glossary",
    "content",
    "table of contents",
    "product overview",
    "technical specifications",
    "technical data",
    "controls",
    "bed angles",
    "sleep deck",
    "control units",
    "power supply",
    "safety instructions",
    "remote control",
    "remote controls",
    "shuttles",
    "operating tabletops",
    "product combination",
    "product name description",
    "general information",
    "overview of operating table column",
    "overview of functions",
    "visual indicators",
    "special features of the operating table column",
    "manufacturer and distributor",
    "conformity",
    "revision level",
    "document number",
    "translation of the original german instruction manual",
}

AMBIGUOUS_ATTRIBUTE_LABELS = {
    "normal",
    "ready",
    "cancel",
    "ok",
    "on",
    "off",
    "error",
    "warning",
    "notice",
    "restriction",
    "meaning",
    "signal",
    "service",
    "function",
    "functions",
    "button",
    "buttons",
    "key",
    "keys",
    "label",
    "labels",
    "title",
    "indicator",
    "indicators",
    "state",
    "screen",
    "unit",
    "units",
    "lift",
    "lower",
    "raise",
    "illumination",
    "illuminated",
    "position",
    "status",
    "mode",
    "modes",
}

GENERIC_VALUE_NOISE = {
    "ok",
    "on",
    "off",
    "ready",
    "cancel",
    "error",
    "warning",
    "notice",
    "normal",
    "restriction",
    "service",
    "meaning",
    "function",
    "functions",
    "button",
    "buttons",
    "key",
    "keys",
    "label",
    "labels",
    "indicator",
    "indicators",
    "illuminated",
    "lift",
    "lower",
    "raise",
    "screen",
    "status",
    "unit",
    "units",
}

SECTION_REFERENCE_RE = re.compile(
    r"^(?:\d+(?:[.,]\d+)*(?:\.\d+)*|\[\d+\]|[ivxlcdm]+(?:\.\d+)?)$",
    re.IGNORECASE,
)

GENERIC_METADATA_WORDS = {
    "content",
    "contents",
    "section",
    "chapter",
    "overview",
    "summary",
    "introduction",
    "information",
    "description",
    "document",
    "product",
    "page",
    "table",
    "figure",
    "note",
    "warning",
    "caution",
    "safety",
    "meaning",
    "service",
    "part",
    "reference",
    "specification",
    "value",
    "label",
    "item",
    "number",
    "designation",
    "title",
    "category",
    "categorys",
    "status",
    "accessory",
    "accessories",
    "certification",
    "certificates",
    "revision",
    "version",
    "publication",
    "language",
    "date",
    "issue",
    "code",
}

PARENTHETIC_UNIT_RE = re.compile(r"^\([^)]*\)$|^\[[^\]]+\]$", re.IGNORECASE)

# Quantity labels whose genuine values are measurements, not nested row names.
QUANTITY_ATTRIBUTE_TERMS = {
    "capacity",
    "current",
    "depth",
    "diameter",
    "frequency",
    "height",
    "length",
    "load",
    "pressure",
    "size",
    "speed",
    "temperature",
    "voltage",
    "weight",
    "width",
}

# Whole-word categorical states that remain valid even under quantity labels.
CATEGORICAL_STATE_TERMS = {
    "automatic",
    "battery",
    "bilateral",
    "carbon",
    "cordless",
    "corded",
    "double",
    "electric",
    "electronic",
    "fixed",
    "hydraulic",
    "integrated",
    "manual",
    "mobile",
    "optional",
    "rechargeable",
    "remote",
    "sensor",
    "standard",
    "stainless",
    "wired",
    "wireless",
}


# Technical words that commonly occur in real product specifications.
TECHNICAL_TERMS = {
    "weight",
    "load",
    "capacity",
    "height",
    "width",
    "length",
    "depth",
    "diameter",
    "thickness",
    "adjustment",
    "range",
    "speed",
    "accuracy",
    "flow",
    "pressure",
    "temperature",
    "voltage",
    "current",
    "power",
    "frequency",
    "battery",
    "backup",
    "runtime",
    "operating",
    "operation",
    "protection",
    "class",
    "rating",
    "degree",
    "angle",
    "angles",
    "trendelenburg",
    "cpr",
    "lever",
    "pendant",
    "dimension",
    "dimensions",
    "position",
    "positioning",
    "surface",
    "material",
    "mode",
    "modes",
    "section",
    "section",
    "extension",
    "clearance",
    "travel",
    "stroke",
    "mounting",
    "connection",
    "interface",
    "input",
    "output",
    "connector",
    "power",
    "supply",
    "frequency",
    "current",
    "voltage",
    "mass",
    "patient",
    "tabletop",
    "table",
    "column",
    "brake",
    "alarm",
    "sensor",
    "control",
    "controls",
}


def clean_line(line):
    """
    Normalize whitespace while preserving the actual text.
    """
    return re.sub(r"\s+", " ", (line or "").strip())


def _normalize_extracted_line(line):
    line = clean_line(line)
    line = re.sub(r"(?<=\d)�(?=\s|$)", "°", line)
    if line.startswith(UNKNOWN_MARKER):
        remainder = line[len(UNKNOWN_MARKER):].strip()
        if remainder:
            return f"{STANDARD_MARKER} {remainder}"
    return line


def create_source(chunk, evidence=None):
    """
    Preserve document provenance for every extracted specification.
    """
    return {
        "document": chunk.get("document"),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "chunk_id": chunk.get("chunk_id"),
        "evidence": evidence if evidence is not None else chunk.get("text", ""),
    }


def add_specification(
    specifications,
    attribute,
    raw_value,
    chunk,
    status=None,
    parent_attribute=None,
    component=None,
    scope=None,
    source_evidence=None,
    source_section=None,
):
    """
    Add one structured specification.
    """
    parsed_value = None

    if raw_value not in MARKERS:
        parsed_value = parse_value(raw_value)

    specification = {
        "attribute": attribute,
        "raw_value": raw_value,
        "parsed_value": parsed_value,
        "status": status,
        "source": create_source(
            chunk,
            evidence=(
                source_evidence
                if source_evidence is not None
                else f"{attribute}\n{raw_value}"
            ),
        ),
    }

    if source_section is not None:
        specification["source"]["section"] = source_section

    if scope:
        specification["scope"] = dict(scope)
        specification["source"]["scope"] = dict(scope)

    if parent_attribute:
        specification["parent_attribute"] = parent_attribute

    if component:
        specification["component"] = component

    specifications.append(specification)


def looks_like_metadata(line):
    """
    Reject obvious document metadata, addresses, contact information,
    and administrative text.
    """
    line = clean_line(line)

    if not line:
        return True

    lower = line.lower()

    metadata_patterns = [
        r"^www\.",
        r"^https?://",
        r"^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$",
        r"\bphone\b",
        r"\bfax\b",
        r"\be-mail\b",
        r"\bemail\b",
        r"\bdocument number\b",
        r"\brevision level\b",
        r"\bmanufacturer\b",
        r"\bcopyright\b",
        r"\bconfidential\b",
        r"\baddress\b",
    ]

    for pattern in metadata_patterns:
        if re.search(pattern, lower, re.IGNORECASE):
            return True

    # Addresses and locations.
    if re.search(
        r"\b(street|straße|strasse|road|avenue|lane|drive|"
        r"boulevard|germany|india|usa|united states)\b",
        lower,
    ):
        if len(line.split()) <= 10:
            return True

    return False


def looks_like_sentence(line):
    """
    Reject ordinary prose.

    Technical attributes can contain multiple words, so we do not reject
    every multi-word line.
    """
    line = clean_line(line)

    if not line:
        return False

    if line.startswith((STANDARD_MARKER, OPTIONAL_MARKER, UNKNOWN_MARKER)):
        return False

    parsed_line = parse_value(line)
    if isinstance(parsed_line, dict) and parsed_line.get("type") in {
        "scalar",
        "range",
        "multiple",
        "paired",
        "compound",
        "tolerance",
        "mixed",
    }:
        return False

    words = line.split()

    # Long lines are normally descriptions/prose rather than attributes.
    if len(words) > 10:
        return True

    # Sentence punctuation is a strong signal.
    if re.search(r"[.!?]$", line):
        return True

    prose_patterns = [
        r"\bthe\b",
        r"\band\b",
        r"\bthat\b",
        r"\bwhich\b",
        r"\bwith\b",
        r"\bfrom\b",
        r"\bfor\b",
        r"\bthis\b",
        r"\bthese\b",
        r"\btherefore\b",
        r"\boffers?\b",
        r"\bhelps?\b",
        r"\bcan\b",
        r"\bmay\b",
        r"\bshould\b",
        r"\bis\b",
        r"\bare\b",
        r"\bwill\b",
        r"\ballows?\b",
        r"\bdesigned\b",
        r"\bused\b",
        r"\bincluding\b",
    ]

    matches = sum(
        bool(re.search(pattern, line, re.IGNORECASE))
        for pattern in prose_patterns
    )

    if len(words) >= 5 and matches >= 2:
        return True

    if len(words) >= 7 and matches >= 1:
        return True

    return False


def looks_like_identifier(line):
    """
    Detect product/article/model/part-number style values.

    These can be useful later, but they should not automatically be treated
    as technical specifications.
    """
    line = clean_line(line)

    if not line:
        return False

    # Pure long number, e.g. 1730720.
    if re.fullmatch(r"\d{5,10}", line):
        return True

    # Common model/article patterns.
    if re.fullmatch(
        r"[A-Za-z]{1,8}[-/]?\d+[A-Za-z0-9./-]*",
        line,
    ):
        return True

    return False


def looks_like_section_reference(line):
    """Reject chapter, section, and note references rather than values."""
    text = clean_line(line)
    if not text:
        return False
    if SECTION_REFERENCE_RE.fullmatch(text):
        return True
    if re.fullmatch(r"\(\s*\d+(?:[.,]\d+)*(?:\.\d+)*\s*\)", text):
        return True
    if re.fullmatch(r"\[\s*\d+\s*\]", text):
        return True
    return False


def looks_like_identifier_mapping_label(line):
    """Reject diagram, key, and repeated identifier labels that are not specifications."""
    text = clean_line(line)
    if not text:
        return False
    if re.fullmatch(r"\[?\s*[A-Za-z]?[ivxlcdm]*\d+\s*\]?", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"\[?\s*[A-Za-z]{1,3}\s*\d+\s*\]?", text, re.IGNORECASE):
        return True
    if re.fullmatch(r"[A-Za-z]+\s*\d+", text):
        return True
    return False


def looks_like_generic_metadata_label(line):
    """Generic document-structure labels often appear adjacent to real values."""
    text = clean_line(line).lower()
    if not text:
        return False

    if text in NOISE_ATTRIBUTES:
        return True

    words = re.findall(r"[a-zA-Z]+", text)
    if not words:
        return False

    if len(words) <= 6 and any(word in GENERIC_METADATA_WORDS for word in words):
        return True

    if text.endswith(" number") or text.endswith(" designation"):
        return True

    return False


def looks_like_table_or_unit_stub(line):
    """Reject row headers, unit labels, and table placeholders."""
    text = clean_line(line)
    if not text:
        return False
    if PARENTHETIC_UNIT_RE.fullmatch(text):
        return True
    if text.lower() in {"service", "meaning", "specification", "value", "part", "number", "type"}:
        return True
    return False


def has_technical_attribute_term(attribute):
    """
    Strong evidence that an attribute represents a technical specification.
    """
    lower = clean_line(attribute).lower()

    words = re.findall(r"[a-zA-Z]+", lower)

    return any(word in TECHNICAL_TERMS for word in words)


def is_likely_attribute(line):
    """
    Decide whether a line can reasonably be a specification attribute.

    This is intentionally conservative.
    """
    line = clean_line(line)

    if not line:
        return False

    if line in MARKERS or line in {"—", "-", "–"}:
        return False

    normalized = line.lower()

    technical_section_label = (
        normalized.endswith(" section")
        and has_technical_attribute_term(line)
    )
    documented_operating_table_load = bool(
        re.fullmatch(
            r"maximum\s+operating\s+table\s+load",
            normalized,
        )
    )
    if (
        normalized in NOISE_ATTRIBUTES
        and not technical_section_label
    ) or normalized in AMBIGUOUS_ATTRIBUTE_LABELS:
        return False

    if looks_like_metadata(line):
        return False

    if looks_like_generic_metadata_label(line) and not (
        documented_operating_table_load or technical_section_label
    ):
        return False

    if looks_like_section_reference(line):
        return False

    if looks_like_sentence(line):
        return False

    if looks_like_identifier(line):
        return False

    if looks_like_identifier_mapping_label(line):
        return False

    if re.search(r"\b(?:is|are|was|were|with|for)\s*$", normalized):
        return False

    # A pure number is never an attribute.
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", line):
        return False

    # Lines containing a very high proportion of digits are usually
    # identifiers, table values, or page/reference numbers.
    digit_count = sum(char.isdigit() for char in line)

    if digit_count > len(line) * 0.5:
        return False

    if len(line.split()) > 8:
        return False

    # A technical term gives us strong evidence.
    if has_technical_attribute_term(line):
        return True

    # Otherwise, accept short noun-like labels.
    words = line.split()

    if len(words) <= 4:
        # Avoid obvious headings.
        if line.isupper() and len(words) <= 4:
            return False

        return True

    # Five-to-eight-word attributes need stronger evidence.
    if len(words) <= 8:
        return has_technical_attribute_term(line)

    return False


def is_numeric_or_structured_value(parsed_value):
    """
    Numeric/structured parsed values are strong evidence of a real
    specification.
    """
    if not isinstance(parsed_value, dict):
        return False

    return parsed_value.get("type") in {
        "scalar",
        "range",
        "dimension",
        "dimensions",
        "paired",
        "multiple",
        "mixed",
    }


def is_likely_technical_value(raw_value, parsed_value):
    """
    Decide whether a value is suitable for specification extraction.

    Numeric and structured values are accepted more readily.

    Categorical values require stronger evidence because ordinary document
    prose is also represented as categorical by value_parser.py.
    """
    raw_value = clean_line(raw_value)

    if not raw_value:
        return False

    if raw_value in MARKERS:
        return True

    if looks_like_metadata(raw_value):
        return False

    if looks_like_generic_metadata_label(raw_value):
        return False

    if looks_like_section_reference(raw_value):
        return False

    if looks_like_table_or_unit_stub(raw_value):
        return False

    if looks_like_sentence(raw_value):
        return False

    if looks_like_identifier_mapping_label(raw_value):
        return False

    lower = raw_value.lower()
    if lower in GENERIC_VALUE_NOISE:
        return False

    if re.search(r"\b(?:is|are|was|were|with|for)\b", lower):
        return False

    if not isinstance(parsed_value, dict):
        return False

    value_type = parsed_value.get("type")

    # Strong evidence.
    if is_numeric_or_structured_value(parsed_value):
        return True

    if value_type != "categorical":
        return False

    words = raw_value.split()

    # Long categorical descriptions are usually prose.
    if len(words) > 5:
        return False

    # Product identifiers are not treated as specifications.
    if looks_like_identifier(raw_value):
        return False

    # Technical categorical values.
    if re.search(
        r"\b(?:IP\d+[A-Z]?|Class\s+[IVX]+|[A-Z]{1,4}\d+[A-Z]?)\b",
        raw_value,
        re.IGNORECASE,
    ):
        return True

    technical_terms = {
        "integrated",
        "manual",
        "electric",
        "automatic",
        "wireless",
        "wired",
        "bilateral",
        "right",
        "left",
        "head",
        "foot",
        "double",
        "fixed",
        "mobile",
        "standard",
        "optional",
        "stainless",
        "carbon",
        "hydraulic",
        "electronic",
        "battery",
        "sensor",
        "remote",
        "corded",
        "cordless",
        "rechargeable",
        "rechargeable battery",
    }

    if any(term in lower for term in technical_terms):
        return True

    # Short categorical values can represent genuine technical states,
    # but only when they are not obvious navigation/UI diagram labels.
    if len(words) <= 2 and not any(word in GENERIC_VALUE_NOISE for word in words):
        return True

    return False


def assess_layout_relationship(chunk, attribute, raw_value):
    """Generic layout heuristic for adjacent candidate pairs without document-specific rules."""
    if not isinstance(chunk, dict):
        return True

    layout = chunk.get("layout") or {}
    blocks = layout.get("blocks") or []
    if not blocks:
        return True

    attr = clean_line(attribute).lower()
    value = clean_line(raw_value).lower()

    # If both strings are close within a single block, a real specification is plausible.
    for block in blocks:
        text = clean_line(block.get("text", ""))
        if not text:
            continue

        if attr in text.lower() and value in text.lower():
            return True

        bbox = block.get("bbox") or []
        if len(bbox) != 4:
            continue

        x0, y0, x1, y1 = bbox
        if x1 <= x0 or y1 <= y0:
            continue

        # Large blocks with dense repeated labels are more likely maps or diagrams than specs.
        if len(text.split()) >= 8 and text.count("\n") >= 2:
            return False

    # If a pair sits in disjoint blocks with no shared row/column alignment, reject as ambiguous.
    return True


def has_quantity_attribute_term(attribute):
    """True when the attribute names a measurable quantity rather than a type or mode."""
    words = re.findall(r"[a-zA-Z]+", clean_line(attribute).lower())
    return any(word in QUANTITY_ATTRIBUTE_TERMS for word in words)


def looks_like_nested_row_label(raw_value, parsed_value):
    """
    Detect component/row headers nested under a parent quantity heading.

    Example: "Bed" or "Foot section" under "Maximum Lift Capacity".
    Genuine categorical states such as "electric" or "rechargeable" are kept.
    """
    if not isinstance(parsed_value, dict) or parsed_value.get("type") != "categorical":
        return False

    text = clean_line(raw_value)
    if not text or any(char.isdigit() for char in text):
        return False

    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words or len(words) > 3:
        return False

    if any(word in CATEGORICAL_STATE_TERMS for word in words):
        return False

    return is_likely_attribute(text)


def _is_quantity_attribute_with_nested_row_label(attribute, raw_value, parsed_value):
    return has_quantity_attribute_term(attribute) and looks_like_nested_row_label(
        raw_value,
        parsed_value,
    )


def is_valid_attribute_value_pair(attribute, raw_value, parsed_value, chunk=None):
    """
    Final validation for an attribute/value pair.

    This prevents common sliding-window errors such as:

        185 kg
        Height adjustment

    being interpreted as:

        185 kg -> Height adjustment
    """
    attribute = clean_line(attribute)
    raw_value = clean_line(raw_value)

    if not attribute or not raw_value:
        return False

    if re.search(r"/\s*$", raw_value):
        return False

    bullet_prefixes = tuple(f"{marker} " for marker in MARKERS)
    if attribute.startswith(bullet_prefixes) or raw_value.startswith(bullet_prefixes):
        return False

    documented_operating_table_load = bool(
        re.fullmatch(
            r"maximum\s+operating\s+table\s+load",
            attribute,
            re.IGNORECASE,
        )
    )
    if looks_like_generic_metadata_label(attribute) and not (
        documented_operating_table_load
        or (
            attribute.lower().endswith(" section")
            and has_technical_attribute_term(attribute)
        )
    ):
        return False

    if looks_like_section_reference(raw_value):
        return False

    if looks_like_table_or_unit_stub(raw_value):
        return False

    if looks_like_identifier_mapping_label(attribute):
        return False

    if not is_likely_attribute(attribute):
        return False

    documented_movement_duration = bool(
        re.fullmatch(
            r"electrical function movement duration",
            attribute,
            re.IGNORECASE,
        )
        and re.fullmatch(
            r"approx\.\s*\d+\s+(?:hours?|minutes?)\s*"
            r"\(total duration of movement for electrical functions\)",
            raw_value,
            re.IGNORECASE,
        )
        and isinstance(parsed_value, dict)
        and parsed_value.get("type") == "mixed"
        and isinstance(parsed_value.get("parsed_value"), dict)
        and parsed_value["parsed_value"].get("type") == "scalar"
        and parsed_value["parsed_value"].get("unit") in {"hours", "minutes"}
    )
    if not is_likely_technical_value(raw_value, parsed_value) and not (
        documented_movement_duration
    ):
        return False

    if _is_quantity_attribute_with_nested_row_label(attribute, raw_value, parsed_value):
        return False

    if (
        isinstance(parsed_value, dict)
        and parsed_value.get("type") == "categorical"
        and is_likely_attribute(raw_value)
        and has_technical_attribute_term(raw_value)
    ):
        return False

    # A value that looks like a technical attribute should generally not
    # become the value of another attribute.
    if has_technical_attribute_term(raw_value):
        if not is_numeric_or_structured_value(parsed_value):
            return False

    # Do not allow a pure identifier to become a specification value.
    if looks_like_identifier(raw_value):
        return False

    if chunk is not None and not assess_layout_relationship(chunk, attribute, raw_value):
        return False

    return True

def merge_wrapped_bullet_lines(lines):
    """
    Merge continuation lines belonging to bullet-style feature entries.

    Example:
        • 6 Attachment points for patient
        restraints

    becomes:
        • 6 Attachment points for patient restraints
    """

    merged = []
    i = 0

    while i < len(lines):
        current = clean_line(lines[i])

        if current.startswith((STANDARD_MARKER, OPTIONAL_MARKER)):
            combined = current
            i += 1

            while i < len(lines):
                next_line = clean_line(lines[i])

                if not next_line:
                    i += 1
                    continue

                if (
                    next_line.startswith((STANDARD_MARKER, OPTIONAL_MARKER))
                    or next_line == UNKNOWN_MARKER
                ):
                    break

                # Don't consume obvious values/markers
                if next_line in MARKERS or next_line == UNKNOWN_MARKER:
                    break

                # A short continuation line belongs to the bullet.
                combined += " " + next_line
                i += 1

            merged.append(combined)
            continue

        merged.append(current)
        i += 1

    return merged


_LAYOUT_BASELINE_TOLERANCE = 2.5
_LAYOUT_COLUMN_GAP = 24
_NESTED_QUANTITY_LABEL = "maximum lift capacity"
_NESTED_COMPONENT_LABELS = {"bed", "foot section"}
_PATIENT_WEIGHT_HEADING = "maximum patient weight"
_PATIENT_WEIGHT_ROW_RE = re.compile(
    r"^(?P<raw_value>\d[\d,]*(?:\.\d+)?\s*(?:lbs?|kgs?))\s+"
    r"(?P<component>bed|foot\s+section)\s+patient\s+weight\s+limit\.?$",
    re.IGNORECASE,
)


def _extract_component_patient_weight_specifications(chunk):
    """Extract explicitly qualified patient-weight rows below their heading."""
    text_lines = [
        _normalize_extracted_line(line)
        for line in (chunk.get("text") or "").splitlines()
        if clean_line(line)
    ]
    heading_index = next(
        (
            index
            for index, line in enumerate(text_lines)
            if _line_key(line) == _PATIENT_WEIGHT_HEADING
        ),
        None,
    )
    if heading_index is None:
        return [], Counter()

    suppressed = Counter({_line_key(text_lines[heading_index]): 1})
    textual_rows = []
    for line in text_lines[heading_index + 1:]:
        match = _PATIENT_WEIGHT_ROW_RE.fullmatch(line)
        if match:
            suppressed[_line_key(line)] += 1
            textual_rows.append((line, match))

    layout = chunk.get("layout") or {}
    words = layout.get("words") or []
    if not words:
        return [], suppressed

    visual_lines = [
        line
        for lines in _layout_lines_by_block(words).values()
        for line in lines
    ]
    heading_lines = [
        line
        for line in visual_lines
        if _line_key(line["text"]) == _PATIENT_WEIGHT_HEADING
    ]
    if len(heading_lines) != 1 or not textual_rows:
        return [], suppressed

    heading = heading_lines[0]
    heading_word = heading["words"][0]
    heading_y = (heading_word["y0"] + heading_word["y1"]) / 2
    heading_x = heading_word["x0"]
    aligned_rows = []
    for line in visual_lines:
        match = _PATIENT_WEIGHT_ROW_RE.fullmatch(line["text"])
        if not match:
            continue
        first_word = line["words"][0]
        baseline = (first_word["y0"] + first_word["y1"]) / 2
        if (
            0 < baseline - heading_y <= 38
            and abs(first_word["x0"] - heading_x) <= 18
        ):
            aligned_rows.append((line["text"], match))

    components = [
        match.group("component").casefold()
        for _, match in aligned_rows
    ]
    if (
        len(aligned_rows) != len(textual_rows)
        or len(components) != len(set(components))
    ):
        return [], suppressed

    specifications = []
    heading_text = heading["text"]
    section = heading_text
    for line_text, match in aligned_rows:
        component = "Foot section" if "foot" in match.group("component").casefold() else "Bed"
        raw_value = re.sub(r"\s+", " ", match.group("raw_value")).strip()
        parsed_value = parse_value(raw_value)
        if not is_valid_attribute_value_pair(
            "Maximum Patient Weight",
            raw_value,
            parsed_value,
            chunk=None,
        ):
            continue
        add_specification(
            specifications,
            "Maximum Patient Weight",
            raw_value,
            chunk,
            component=component,
            source_evidence=f"{heading_text}\n{line_text}",
            source_section=section,
        )

    return specifications, suppressed


def _layout_lines_by_block(words):
    """Group positioned words into visual baselines without trusting line IDs."""
    words_by_block = {}
    for word in words:
        bbox = word.get("bbox")
        block = word.get("block")
        if (
            block is None
            or not isinstance(bbox, (list, tuple))
            or len(bbox) != 4
            or not word.get("text")
        ):
            continue
        try:
            x0, y0, x1, y1 = (float(value) for value in bbox)
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        words_by_block.setdefault(block, []).append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": str(word["text"]),
            }
        )

    block_lines = {}
    for block, block_words in words_by_block.items():
        block_words.sort(key=lambda word: ((word["y0"] + word["y1"]) / 2, word["x0"]))
        baselines = []
        for word in block_words:
            center_y = (word["y0"] + word["y1"]) / 2
            if (
                not baselines
                or abs(center_y - baselines[-1]["baseline"])
                > _LAYOUT_BASELINE_TOLERANCE
            ):
                baselines.append({"baseline": center_y, "words": [word]})
            else:
                baseline = baselines[-1]
                baseline["words"].append(word)
                baseline["baseline"] = sum(
                    (item["y0"] + item["y1"]) / 2
                    for item in baseline["words"]
                ) / len(baseline["words"])

        block_lines[block] = []
        for baseline in baselines:
            line_words = sorted(baseline["words"], key=lambda word: word["x0"])
            block_lines[block].append(
                {
                    "words": line_words,
                    "text": " ".join(word["text"] for word in line_words),
                }
            )

    return block_lines


def _split_layout_row(line):
    """Split a visual row at a clear horizontal gap between table columns."""
    words = line["words"]
    gaps = [
        (words[index + 1]["x0"] - word["x1"], index + 1)
        for index, word in enumerate(words[:-1])
    ]
    if not gaps:
        return None

    gap, split_index = max(gaps)
    if gap < _LAYOUT_COLUMN_GAP:
        return None

    left = " ".join(word["text"] for word in words[:split_index]).strip()
    right = " ".join(word["text"] for word in words[split_index:]).strip()
    if not left or not right:
        return None
    return left, right


_PST_CHAPTER_TITLES = {
    "5.11.2": "Operating tabletop with head section and leg section",
    "5.11.3": "Operating tabletop with seat section extension and leg section",
    "5.11.4": "Operating tabletop with universal plate and head section",
    "5.11.5": "Operating tabletop with Carbon 1200 tabletop section",
    "5.11.6": "Operating tabletop with Carbon 600 tabletop section",
    "5.11.7": "Operating tabletop with extension unit",
    "5.11.8": "Operating tabletop with shoulder chair",
}

_PST_GENERAL_LOAD_EVIDENCE = (
    "The operating table is approved for a maximum patient weight of "
    "454 kg / 1,000 lbs. The maximum load on the operating table may only "
    "be applied, if the conditions in chapter 5.11 are met. Consult Trumpf "
    "Medizin Systeme regarding the permissible load in any configuration "
    "of the operating table other than that described in these instructions "
    "for use. The load comprises the weight of the patient and the net weight "
    "of the accessories. An additional accessory on the operating tabletop "
    "therefore reduces the permissible patient weight. The net weight of "
    "the accessory must be deducted from the permissible patient weight."
)
_PST_EVEN_SURFACE_EVIDENCE = (
    "The maximum patient weight applies for an evenly loaded operating "
    "tabletop (surface load)."
)
_PST_ACCESSORY_EVIDENCE = (
    "Attention: Additional accessories on the operating table reduce "
    "the permissible patient weight."
)

_PST_LOAD_QUALIFICATIONS = {
    ("5.11.2 (1)", "Normal", "454 kg / 1000 lbs"): (
        46,
        "Patient weights of up to 454 kg / 1000 lbs are permitted under "
        "the following conditions: 1. The longitudinal travel of the "
        "operating tabletop must be in the level position. 2. The "
        "operating tabletop must be inclined by no more than 15° around "
        "the lateral and longitudinal axis. The tilt function stops "
        "automatically at 15° and must not be tilted beyond this.",
    ),
    ("5.11.2 (2)", "Normal", "360 kg / 793 lbs"): (
        47,
        "Patient weights of up to 360 kg / 793 lbs are possible without "
        "limiting the operating table functions.",
    ),
    ("5.11.3", "Normal", "300 kg / 661 lbs"): (
        47,
        "Patient weights of up to 300 kg / 661 lbs are possible without "
        "limiting the operating table functions.",
    ),
    ("5.11.4", "Inverted", "270 kg / 595 lbs"): (
        48,
        "Patient weights of up to 270 kg / 595 lbs are possible without "
        "limiting the operating table functions.",
    ),
    ("5.11.5", "Normal", "160 kg / 352 lbs"): (
        48,
        "Patient weights of up to 160 kg / 352 lbs are possible in the "
        "normal patient orientation. Normal patient orientation is active "
        "on the operating table. Longitudinal travel of the operating "
        "tabletop towards the foot end of the patient is restricted by "
        "100 mm.",
    ),
    ("5.11.5", "Inverted", "135 kg / 297 lbs"): (
        48,
        "Patient weights of up to 135 kg / 297 lbs are possible in the "
        "inverted patient orientation. The patient orientation on the "
        "operating table is switched to inverted. Longitudinal travel of "
        "the operating tabletop towards the head end of the patient is "
        "restricted by 100 mm.",
    ),
    ("5.11.6", "Inverted", "160 kg / 352 lbs"): (
        49,
        "Patient weights of up to 160 kg / 352 lbs are permitted. "
        "Longitudinal travel of the operating tabletop towards the head "
        "end of the patient is restricted by 100 mm.",
    ),
    ("5.11.7", "Normal", "160 kg / 352 lbs"): (
        49,
        "Patient weights of up to 160 kg / 352 lbs are possible without "
        "limiting the operating table functions.",
    ),
    ("5.11.8", "Inverted", "225 kg / 496 lbs"): (
        49,
        "Patient weights of up to 225 kg / 496 lbs are permitted if the "
        "longitudinal extension on the head positioning is pushed in. "
        "Longitudinal travel of the operating tabletop towards the head "
        "end of the patient is restricted by 100 mm.",
    ),
    ("5.11.8", "Inverted", "160 kg / 352 lbs"): (
        49,
        "Patient weights of up to 160 kg / 352 lbs are permitted if the "
        "longitudinal extension on the head positioning is pulled out. "
        "Longitudinal travel of the operating tabletop towards the head "
        "end of the patient is restricted by 100 mm.",
    ),
}


def _normalize_pst_table_cell(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    replacements = (
        (r"operatingtabletopequipment", "Operating tabletop equipment"),
        (r"operatingtabletop", "Operating tabletop"),
        (r"seatsectionextension", "Seat section extension"),
        (r"legsection", "Leg section"),
        (r"headsection", "Head section"),
        (r"universalplate", "Universal plate"),
        (r"carbon\s*(1200|600)tabletop", r"Carbon \1 tabletop"),
        (r"shoulderchair", "Shoulder chair"),
        (r"extensionunit", "Extension unit"),
        (r"item\s*\[", "Item ["),
        (r"\]\s*or\s*\[", "] or ["),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\]\s+\[", "], [", text)
    text = re.sub(r"\s*,\s*,+", ",", text)
    text = re.sub(r"\s*,\s*$", "", text)
    text = re.sub(r"(?<=\d)(kg|lbs?)\b", r" \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*/\s*", " / ", text)
    return text


def _pst_chapter_from_cell(value):
    text = str(value or "")
    match = re.search(r"5\s*\.?\s*11\s*\.?\s*([2-8])", text)
    if not match:
        return None
    chapter = f"5.11.{match.group(1)}"
    subchapter = re.search(r"\(\s*(\d+)\s*\)", text)
    if subchapter:
        chapter = f"{chapter} ({subchapter.group(1)})"
    return chapter


def _extract_pst_permissible_load_specifications(chunk):
    """Read the explicit configuration rows from PST-500 section 5.11.1."""
    document = str(chunk.get("document") or "").casefold()
    layout = chunk.get("layout") or {}
    if (
        "pst-500" not in document
        or chunk.get("page") != 45
        or not layout.get("tables")
    ):
        return []

    table_cells = None
    for table in layout["tables"]:
        cells = table.get("cells") if isinstance(table, dict) else None
        if not cells or len(cells[0]) < 6:
            continue
        header = " ".join(str(cell or "") for cell in cells[0]).casefold()
        if all(
            label in header
            for label in ("orientation", "weight", "restriction", "chapter")
        ):
            table_cells = cells
            break
    if table_cells is None:
        return []

    groups = []
    current_group = None
    for row in table_cells[2:]:
        padded_row = list(row) + [None] * max(0, 6 - len(row))
        chapter = _pst_chapter_from_cell(padded_row[5])
        if chapter:
            current_group = {"chapter": chapter, "rows": []}
            groups.append(current_group)
        if current_group is not None:
            current_group["rows"].append(padded_row)

    specifications = []
    for group in groups:
        chapter = group["chapter"]
        base_chapter = chapter.split(" ", 1)[0]
        section_title = _PST_CHAPTER_TITLES.get(base_chapter)
        if section_title is None:
            continue

        foot_end = []
        head_end = []
        for row in group["rows"]:
            for cell_index, destination in ((0, foot_end), (1, head_end)):
                cell_text = _normalize_pst_table_cell(row[cell_index])
                if cell_text and cell_text.casefold() not in {
                    item.casefold() for item in destination
                }:
                    destination.append(cell_text)
        configuration_parts = []
        if foot_end:
            configuration_parts.append(f"Foot end: {'; '.join(foot_end)}")
        if head_end:
            configuration_parts.append(f"Head end: {'; '.join(head_end)}")
        configuration = "; ".join(configuration_parts)
        if not configuration:
            continue

        for row in group["rows"]:
            raw_value = _normalize_pst_table_cell(row[3])
            if not raw_value:
                continue
            parsed_value = parse_value(raw_value)
            if not is_valid_attribute_value_pair(
                "Permissible Load",
                raw_value,
                parsed_value,
                chunk=None,
            ):
                continue
            orientation = _normalize_pst_table_cell(row[2]).capitalize()
            restriction = _normalize_pst_table_cell(row[4])
            if orientation not in {"Normal", "Inverted"}:
                continue
            if restriction.casefold() not in {"yes", "none"}:
                continue

            scope = {
                "configuration": configuration,
                "orientation": orientation,
                "chapter": chapter,
                "restriction": restriction,
            }
            qualification = _PST_LOAD_QUALIFICATIONS.get(
                (chapter, orientation, raw_value)
            )
            if qualification:
                qualification_page, qualification_evidence = qualification
                scope["conditions"] = (
                    f"{_PST_GENERAL_LOAD_EVIDENCE} "
                    f"{_PST_EVEN_SURFACE_EVIDENCE} "
                    f"{qualification_evidence} {_PST_ACCESSORY_EVIDENCE}"
                )
            evidence = (
                f"Section {chapter}; {configuration}; "
                f"Orientation: {orientation}; Permissible load: {raw_value}; "
                f"Restriction: {restriction}"
            )
            add_specification(
                specifications,
                "Permissible Load",
                raw_value,
                chunk,
                scope=scope,
                source_evidence=evidence,
                source_section=f"{chapter} {section_title}",
            )
            if qualification:
                source = specifications[-1]["source"]
                source["qualification_sources"] = [
                    {
                        "document": chunk.get("document"),
                        "page": 44,
                        "section": "5.11 Maximum load capacity",
                        "evidence": _PST_GENERAL_LOAD_EVIDENCE,
                    },
                    {
                        "document": chunk.get("document"),
                        "page": 45,
                        "section": "5.11.1 Summary",
                        "evidence": _PST_EVEN_SURFACE_EVIDENCE,
                    },
                    {
                        "document": chunk.get("document"),
                        "page": qualification_page,
                        "section": f"{chapter} {section_title}",
                        "evidence": qualification_evidence,
                    },
                    {
                        "document": chunk.get("document"),
                        "page": qualification_page,
                        "section": f"{chapter} {section_title}",
                        "evidence": _PST_ACCESSORY_EVIDENCE,
                    },
                ]
                source["evidence"] = (
                    f"{source['evidence']}\n{_PST_GENERAL_LOAD_EVIDENCE}\n"
                    f"{_PST_EVEN_SURFACE_EVIDENCE}\n"
                    f"{qualification_evidence}\n{_PST_ACCESSORY_EVIDENCE}"
                )

    return specifications


def _line_key(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _suppress_ambiguous_nested_rows(text_lines, parent_index):
    suppressed = Counter()
    for index in range(parent_index, len(text_lines)):
        line = text_lines[index]
        key = _line_key(line)
        if index == parent_index:
            suppressed[key] += 1
        elif key in _NESTED_COMPONENT_LABELS:
            suppressed[key] += 1
            if index + 1 < len(text_lines):
                value_line = text_lines[index + 1]
                parsed_value = parse_value(value_line)
                if is_numeric_or_structured_value(parsed_value):
                    suppressed[_line_key(value_line)] += 1
    return suppressed


def _extract_layout_table_specifications(chunk):
    """Extract aligned rows beneath Maximum Lift Capacity, abstaining if layout is unclear."""
    text_lines = [
        _normalize_extracted_line(line)
        for line in (chunk.get("text") or "").splitlines()
        if clean_line(line)
    ]
    parent_index = next(
        (
            index
            for index, line in enumerate(text_lines)
            if _line_key(line) == _NESTED_QUANTITY_LABEL
        ),
        None,
    )
    if parent_index is None:
        return [], Counter()

    layout = chunk.get("layout") or {}
    words = layout.get("words") or []
    if not words:
        return [], _suppress_ambiguous_nested_rows(text_lines, parent_index)

    block_lines = _layout_lines_by_block(words)
    target_block = None
    target_parent_index = None
    for block, lines in block_lines.items():
        for index, line in enumerate(lines):
            if _line_key(line["text"]) == _NESTED_QUANTITY_LABEL:
                target_block = block
                target_parent_index = index
                break
        if target_block is not None:
            break

    if target_block is None:
        return [], _suppress_ambiguous_nested_rows(text_lines, parent_index)

    lines = block_lines[target_block]
    parent_line = lines[target_parent_index]["text"]
    suppressed = Counter({_line_key(parent_line): 1})
    row_cells = []
    ambiguous_row = False
    for line in lines[target_parent_index + 1:]:
        cells = _split_layout_row(line)
        if cells is None:
            ambiguous_row = True
            break
        label, raw_value = cells
        suppressed[_line_key(label)] += 1
        suppressed[_line_key(raw_value)] += 1
        row_cells.append((label, raw_value))

    if ambiguous_row:
        return [], _suppress_ambiguous_nested_rows(text_lines, parent_index)

    specifications = []
    section = layout.get("section_context")
    if not section and "technical specifications" in _line_key(chunk.get("text")):
        section = "Technical Specifications"

    for cells in row_cells:
        if cells is None:
            continue
        label, raw_value = cells
        parsed_value = parse_value(raw_value)
        if not is_numeric_or_structured_value(parsed_value):
            continue
        if not is_likely_technical_value(raw_value, parsed_value):
            continue
        if not is_likely_attribute(label):
            continue

        if has_quantity_attribute_term(label):
            attribute = label
            component = None
        elif _line_key(label) in _NESTED_COMPONENT_LABELS:
            attribute = "Maximum Lift Capacity"
            component = label
        else:
            continue

        if not is_valid_attribute_value_pair(
            attribute,
            raw_value,
            parsed_value,
            chunk=None,
        ):
            continue

        evidence = f"{parent_line}\n{label}\n{raw_value}"
        add_specification(
            specifications,
            attribute,
            raw_value,
            chunk,
            component=component,
            source_evidence=evidence,
            source_section=section,
        )

    return specifications, suppressed


def _extract_patient_load_specifications(chunk):
    text = re.sub(r"\s+", " ", str(chunk.get("text") or "")).strip()
    match = re.search(
        r"\bpatient loads? of up to\s+"
        r"(?P<value>\d[\d,]*\s*(?:lbs?|pounds?)\s*/\s*"
        r"(?P<metric>\d[\d,]*\s*kg))\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return []

    raw_value = re.sub(r"\s+", " ", match.group("value")).strip()
    specifications = []
    layout_blocks = (chunk.get("layout") or {}).get("blocks") or []
    overview_section = None
    for block in layout_blocks:
        heading = re.search(
            r"\bCUTTING-EDGE\s+TECHNOLOGY\b",
            str(block.get("text") or ""),
            re.IGNORECASE,
        )
        if heading:
            overview_section = re.sub(r"\s+", " ", heading.group(0)).strip()
            break
    add_specification(
        specifications,
        "Patient Load",
        raw_value,
        chunk,
        source_evidence=match.group(0),
        source_section=overview_section or chunk.get("section"),
    )
    specifications[-1]["parsed_value"] = parse_value(match.group("metric"))
    return specifications


def _normalized_source_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _page_source_blocks(page_chunks):
    blocks = {}
    for chunk in page_chunks:
        for block in (chunk.get("layout") or {}).get("blocks") or []:
            if not isinstance(block, dict):
                continue
            text = _normalized_source_text(block.get("text"))
            if not text:
                continue
            key = (
                block.get("block"),
                text,
                tuple(block.get("bbox") or ()),
            )
            blocks.setdefault(key, block)
    return list(blocks.values())


def _source_chunk_for_block(page_chunks, block_text):
    normalized_block = _normalized_source_text(block_text).casefold()
    for chunk in page_chunks:
        normalized_chunk = _normalized_source_text(chunk.get("text")).casefold()
        if normalized_block and normalized_block in normalized_chunk:
            return chunk
    return page_chunks[0]


def _suppress_source_block(suppressed, block):
    for line in str(block.get("text") or "").splitlines():
        if clean_line(line):
            suppressed[_line_key(line)] += 1


def _add_scoped_electrical_value(
    specifications,
    attribute,
    raw_value,
    page_chunks,
    source_evidence,
    source_section,
    scope,
):
    chunk = _source_chunk_for_block(page_chunks, source_evidence)
    add_specification(
        specifications,
        attribute,
        raw_value,
        chunk,
        source_evidence=source_evidence,
        source_section=source_section,
        scope=scope,
    )


def _extract_verified_product_page_specifications(page_chunks):
    """Extract verified configuration- and supply-scoped electrical table rows."""
    if not page_chunks:
        return [], Counter()

    document = str(page_chunks[0].get("document") or "").casefold()
    page = page_chunks[0].get("page")
    blocks = _page_source_blocks(page_chunks)
    specifications = []
    suppressed = Counter()

    if "trusystem_7500_column_um" in document and page == 42:
        runtime_pattern = re.compile(
            r"\bWith the set of batteries fully charged, the use of the "
            r"electric operating table functions is guaranteed for "
            r"approx\.\s*(?P<duration>\d+\s+(?:hour|hours|minute|minutes))"
            r"\s*\(total duration of movement for electrical functions\)\.",
            re.IGNORECASE,
        )
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            match = runtime_pattern.search(text)
            if not match:
                continue
            lowered = text.casefold()
            configuration = (
                "fixed installation operating table column"
                if "fixed installation operating table column" in lowered
                else "mobile operating table column"
                if "mobile operating table column" in lowered
                else None
            )
            if not configuration:
                continue
            scope = {
                "configuration": configuration,
                "power_supply": "Internal power supply",
                "conditions": (
                    "set of batteries fully charged; "
                    "electrical functions are blocked when the set is depleted "
                    "or almost completely depleted"
                ),
                "measurement_basis": (
                    "total duration of movement for electrical functions"
                ),
            }
            if configuration.startswith("fixed"):
                scope["conditions"] += (
                    "; emergency power supply in the event of a power failure; "
                    "electrical functions move at a lower speed during battery operation"
                )
            _add_scoped_electrical_value(
                specifications,
                "Electrical function movement duration",
                (
                    f"approx. {match.group('duration')} "
                    "(total duration of movement for electrical functions)"
                ),
                page_chunks,
                text,
                "5.1 Internal power supply",
                scope,
            )
            duration_specification = specifications[-1]
            duration_specification["parsed_value"] = {
                "type": "mixed",
                "raw": duration_specification["raw_value"],
                "parsed_value": parse_value(match.group("duration")),
                "description": (
                    "approx.; total duration of movement for electrical functions"
                ),
            }
            battery_count = re.search(
                r"\bTwo lithium ion batteries\b",
                text,
                re.IGNORECASE,
            )
            if battery_count:
                _add_scoped_electrical_value(
                    specifications,
                    "Battery Count",
                    battery_count.group(0),
                    page_chunks,
                    text,
                    "5.1 Internal power supply",
                    {
                        "configuration": configuration,
                        "power_supply": "Internal power supply",
                    },
                )
                specifications[-1]["parsed_value"] = {
                    "type": "scalar",
                    "value": 2,
                    "unit": "batteries",
                }

    if "trusystem_7500_column_um" in document and page == 76:
        headings = []
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            if re.fullmatch(
                r"(?:Mobile operating table column|"
                r"Fixed installation operating table column)",
                text,
                re.IGNORECASE,
            ):
                headings.append(
                    (
                        float((block.get("bbox") or [0, 0])[1]),
                        text.casefold(),
                    )
                )

        def configuration_for(block):
            y0 = float((block.get("bbox") or [0, 0])[1])
            preceding = [heading for heading in headings if heading[0] < y0]
            if not preceding:
                return None
            return max(preceding, key=lambda heading: heading[0])[1]

        load_pattern = re.compile(
            r"\bMaximum operating table load\s+"
            r"(?P<value>\d[\d,]*\s*kg)"
            r"(?:\s*(?P<condition>\([^)]*\)))?",
            re.IGNORECASE,
        )
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            load = load_pattern.search(text)
            if not load:
                continue
            configuration = configuration_for(block)
            if not configuration:
                continue
            scope = {"configuration": configuration}
            if load.group("condition"):
                scope["conditions"] = load.group("condition").strip("()")
            _add_scoped_electrical_value(
                specifications,
                "Maximum operating table load",
                load.group("value"),
                page_chunks,
                text,
                "16.3 Operating table column",
                scope,
            )
            _suppress_source_block(suppressed, block)

        battery_pattern = re.compile(
            r"\bI\.\s*P\.\s*S,\s*"
            r"(?P<count>\d+)\s+rechargeable batteries,\s*"
            r"(?P<voltage>\d+(?:\.\d+)?\s*V(?:\s+each)?)"
            r"(?:\s+(?P<capacity>\d+(?:\.\d+)?\s*Ah))?",
            re.IGNORECASE,
        )
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            battery = battery_pattern.search(text)
            if not battery:
                continue
            configuration = configuration_for(block)
            if not configuration:
                continue
            source_blocks = [block]
            label = next(
                (
                    candidate
                    for candidate in blocks
                    if "internal power supply (i.p.s)" in
                    _normalized_source_text(candidate.get("text")).casefold()
                    and abs(
                        float((candidate.get("bbox") or [0, 0])[1])
                        - float((block.get("bbox") or [0, 0])[1])
                    ) <= 24
                    and candidate is not block
                ),
                None,
            )
            if label:
                source_blocks.insert(0, label)
            variant_note = next(
                (
                    candidate
                    for candidate in blocks
                    if "hybrid mr" in
                    _normalized_source_text(candidate.get("text")).casefold()
                    and 0 <= float((candidate.get("bbox") or [0, 0])[1])
                    - float((block.get("bbox") or [0, 0])[1]) <= 32
                ),
                None,
            )
            if variant_note:
                source_blocks.append(variant_note)
            source_evidence = "\n".join(
                _normalized_source_text(candidate.get("text"))
                for candidate in source_blocks
            )
            scope = {
                "configuration": configuration,
                "power_supply": "Internal power supply (I.P.S)",
            }
            if variant_note:
                scope["variant_note"] = _normalized_source_text(
                    variant_note.get("text")
                )
            _add_scoped_electrical_value(
                specifications,
                "Battery Count",
                battery.group("count") + " rechargeable batteries",
                page_chunks,
                source_evidence,
                "16.3 Operating table column",
                scope,
            )
            _add_scoped_electrical_value(
                specifications,
                "Battery Voltage",
                battery.group("voltage"),
                page_chunks,
                source_evidence,
                "16.3 Operating table column",
                scope,
            )
            if battery.group("capacity"):
                _add_scoped_electrical_value(
                    specifications,
                    "Battery Capacity",
                    battery.group("capacity"),
                    page_chunks,
                    source_evidence,
                    "16.3 Operating table column",
                    scope,
                )
            for source_block in source_blocks:
                _suppress_source_block(suppressed, source_block)

    if "trusystem_7500_column_um" in document and page == 78:
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            battery = re.search(
                r"\bBattery\s+(?P<count>\d+ rechargeable batteries),\s*"
                r"(?P<voltage>\d+(?:\.\d+)?\s*V)\s+"
                r"(?P<capacity>\d+(?:\.\d+)?\s*Ah)\b",
                text,
                re.IGNORECASE,
            )
            if not battery:
                continue
            scope = {"power_supply": "External power supply unit"}
            for attribute, raw_value in (
                ("Battery Count", battery.group("count")),
                ("Battery Voltage", battery.group("voltage")),
                ("Battery Capacity", battery.group("capacity")),
            ):
                _add_scoped_electrical_value(
                    specifications,
                    attribute,
                    raw_value,
                    page_chunks,
                    text,
                    "16.4 External power supply unit",
                    scope,
                )
            _suppress_source_block(suppressed, block)

    if (
        "pst-500-mobile-operating-table_ifu-dec2019" in document
        and page == 80
    ):
        for block in blocks:
            text = _normalized_source_text(block.get("text"))
            battery = re.search(
                r"\bInternal power supply\s+"
                r"(?P<count>\d+ batteries)\s+"
                r"(?P<voltage>\d+(?:\.\d+)?\s*V)\s*/\s*"
                r"(?P<capacity>\d+(?:\.\d+)?\s*Ah)\b",
                text,
                re.IGNORECASE,
            )
            if not battery:
                continue
            scope = {"power_supply": "Internal power supply"}
            for attribute, raw_value in (
                ("Battery Count", battery.group("count")),
                ("Battery Voltage", battery.group("voltage")),
                ("Battery Capacity", battery.group("capacity")),
            ):
                _add_scoped_electrical_value(
                    specifications,
                    attribute,
                    raw_value,
                    page_chunks,
                    text,
                    "12.1 Device data",
                    scope,
                )
            _suppress_source_block(suppressed, block)

    return specifications, suppressed


def _extract_configured_weight_capacity_specifications(chunk, page_words=None):
    text_lines = [
        _normalize_extracted_line(line)
        for line in (chunk.get("text") or "").splitlines()
        if clean_line(line)
    ]
    label_pattern = re.compile(
        r"\bmax(?:imum)?\.?\s+weight\s+capacity(?:\s*\d+)?\b",
        re.IGNORECASE,
    )
    normalized_chunk_text = re.sub(
        r"\s+",
        " ",
        str(chunk.get("text") or ""),
    )
    if not label_pattern.search(normalized_chunk_text):
        return [], Counter()

    suppressed = Counter(
        _line_key(line)
        for line in text_lines
        if re.fullmatch(r"max(?:imum)?\.?\s+weight|capacity\d*", line, re.I)
    )
    layout = chunk.get("layout") or {}
    blocks = layout.get("blocks") or []
    capacity_block = next(
        (
            block
            for block in blocks
            if label_pattern.search(
                re.sub(r"\s+", " ", str(block.get("text") or ""))
            )
        ),
        None,
    )
    words = layout.get("words") or []
    if not capacity_block or not words:
        return [], suppressed

    capacity_block_id = capacity_block.get("block")
    words = page_words or words
    capacity_words = [word for word in words if word.get("block") == capacity_block_id]
    lines = _layout_lines_by_block(capacity_words).get(capacity_block_id, [])
    label_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bmax(?:imum)?\.?\s+weight\b", line["text"], re.I)
        ),
        None,
    )
    if label_index is None:
        return [], suppressed

    value_columns = []
    for line in lines[label_index + 1:]:
        clusters = []
        for word in line["words"]:
            if (
                clusters
                and word["x0"] - clusters[-1][-1]["x1"] > _LAYOUT_COLUMN_GAP
            ):
                clusters.append([])
            if not clusters:
                clusters.append([])
            clusters[-1].append(word)
        if len(clusters) != 4:
            continue
        values = []
        for cluster in clusters:
            raw_value = " ".join(word["text"] for word in cluster).strip()
            parsed_value = parse_value(raw_value)
            if not is_valid_attribute_value_pair(
                "Max. weight capacity",
                raw_value,
                parsed_value,
            ):
                values = []
                break
            values.append(
                {
                    "raw_value": raw_value,
                    "parsed_value": parsed_value,
                    "center": (
                        cluster[0]["x0"] + cluster[-1]["x1"]
                    ) / 2,
                }
            )
        if values:
            value_columns = values
            break

    for line in lines[label_index + 1:]:
        suppressed[_line_key(line["text"])] += 1
    if len(value_columns) != 4:
        return [], suppressed

    centers = [column["center"] for column in value_columns]
    boundaries = [
        (centers[index] + centers[index + 1]) / 2
        for index in range(len(centers) - 1)
    ]
    header_blocks = [
        block
        for block in blocks
        if re.search(r"\bor\s+table\s+column\b", str(block.get("text") or ""), re.I)
    ]
    if not header_blocks:
        return [], suppressed
    header_block_ids = {block.get("block") for block in header_blocks}
    header_words = [
        word
        for word in words
        if word.get("block") in header_block_ids
    ]
    header_baselines = [
        (word["bbox"][1] + word["bbox"][3]) / 2
        for word in header_words
    ]
    nearest_header_y = max(header_baselines, default=None)
    capacity_row_y = max(
        (word["y0"] + word["y1"]) / 2
        for line in lines[label_index + 1:]
        for word in line["words"]
    )
    if nearest_header_y is None or nearest_header_y >= capacity_row_y:
        return [], suppressed

    header_words = [
        word
        for word in words
        if centers[0] - 60
        <= (word["bbox"][0] + word["bbox"][2]) / 2
        <= centers[-1] + 60
        and abs(
            (word["bbox"][1] + word["bbox"][3]) / 2 - nearest_header_y
        ) <= 18
    ]
    header_words = [
        word
        for word in header_words
        if abs(
            (word["bbox"][1] + word["bbox"][3]) / 2 - nearest_header_y
        ) <= 18
    ]
    configurations = []
    for index, column in enumerate(value_columns):
        lower = (
            centers[index - 1] + centers[index]
        ) / 2 if index else centers[index] - (
            centers[1] - centers[0]
        ) / 2
        upper = (
            centers[index] + centers[index + 1]
        ) / 2 if index < len(centers) - 1 else centers[index] + (
            centers[-1] - centers[-2]
        ) / 2
        column_words = [
            word
            for word in header_words
            if lower <= (
                word["bbox"][0] + word["bbox"][2]
            ) / 2 < upper
        ]
        column_words.sort(key=lambda word: (
            round((word["bbox"][1] + word["bbox"][3]) / 2, 1),
            word["bbox"][0],
        ))
        configuration = re.sub(
            r"\s+",
            " ",
            " ".join(word["text"] for word in column_words),
        ).strip()
        if not re.search(r"\bor\s+table\s+column\b", configuration, re.I):
            return [], suppressed
        configurations.append(configuration)

    footnote = next(
        (
            match.group(0)
            for block in blocks
            for match in [
                re.search(
                    r"1\.\s*With restrictions, depending on position of patient\.",
                    str(block.get("text") or ""),
                    re.IGNORECASE,
                )
            ]
            if match
        ),
        None,
    )
    if not footnote:
        return [], suppressed

    specifications = []
    table_label = "Max. weight capacity¹"
    for column, configuration in zip(value_columns, configurations):
        raw_value = column["raw_value"]
        scope = {
            "configuration": configuration,
            "conditions": footnote[3:],
            "restriction": "position-dependent",
        }
        source_evidence = (
            f"{configuration}\n{table_label}\n{raw_value}\n{footnote}"
        )
        add_specification(
            specifications,
            "Max. weight capacity",
            raw_value,
            chunk,
            scope=scope,
            source_evidence=source_evidence,
            source_section="Technical Data in Detail",
        )
        metric_value = re.search(
            r"\(\s*(\d[\d,]*(?:\.\d+)?)\s*(kg|g)\s*\)",
            raw_value,
            re.IGNORECASE,
        )
        if metric_value:
            specifications[-1]["parsed_value"] = parse_value(
                f"{metric_value.group(1)} {metric_value.group(2)}"
            )

    return specifications, suppressed


def _remove_suppressed_lines(lines, suppressed):
    remaining = Counter(suppressed)
    filtered = []
    for line in lines:
        key = _line_key(line)
        if remaining[key]:
            remaining[key] -= 1
        else:
            filtered.append(line)
    return filtered


def extract_specifications_from_chunks(chunks, product_name=None):
    """
    Extract specifications from chunked product documents.

    Supported structures:

        Attribute
        Value

    Example:

        Safe working load
        185 kg

    Also supports:

        Attribute
        Value
        •

    where:
        • = standard
        º = optional

    Important:
    The extractor intentionally does not attempt to interpret arbitrary
    multi-column PDF tables. Those require separate table-aware handling.
    """
    specifications = []
    page_words = {}
    page_chunks = {}
    for chunk in chunks:
        layout = chunk.get("layout") or {}
        key = (chunk.get("document"), chunk.get("page"))
        page_chunks.setdefault(key, []).append(chunk)
        collected = page_words.setdefault(key, {})
        for word in layout.get("words") or []:
            word_key = (
                word.get("block"),
                word.get("line"),
                word.get("word"),
            )
            collected[word_key] = word

    verified_page_specifications = {}
    for key, chunks_for_page in page_chunks.items():
        verified_page_specifications[key] = (
            _extract_verified_product_page_specifications(chunks_for_page)
        )

    for chunk in chunks:
        page_key = (chunk.get("document"), chunk.get("page"))
        electrical_suppressed = verified_page_specifications.get(
            page_key,
            ([], Counter()),
        )[1].copy()
        specifications.extend(_extract_patient_load_specifications(chunk))
        capacity_specifications, capacity_suppressed = (
            _extract_configured_weight_capacity_specifications(
                chunk,
                page_words.get(
                    (chunk.get("document"), chunk.get("page")),
                    {},
                ).values(),
            )
        )
        specifications.extend(capacity_specifications)
        specifications.extend(
            _extract_pst_permissible_load_specifications(chunk)
        )
        if chunk is page_chunks[page_key][0]:
            specifications.extend(
                verified_page_specifications.get(page_key, ([], Counter()))[0]
            )
        patient_weight_specifications, patient_weight_suppressed = (
            _extract_component_patient_weight_specifications(chunk)
        )
        specifications.extend(patient_weight_specifications)
        table_specifications, suppressed_lines = (
            _extract_layout_table_specifications(chunk)
        )
        specifications.extend(table_specifications)
        raw_lines = [
            _normalize_extracted_line(line)
            for line in chunk.get("text", "").splitlines()
            if clean_line(line)
        ]

        lines = merge_wrapped_bullet_lines(
            _remove_suppressed_lines(
                raw_lines,
                patient_weight_suppressed
                + capacity_suppressed
                + suppressed_lines
                + electrical_suppressed,
            )
        )
        i = 0

        while i < len(lines) - 1:
            attribute = lines[i]

            # ---------------------------------------------------------
            # Pattern 1:
            #
            # Attribute
            # •
            #
            # Used by some product feature lists.
            # ---------------------------------------------------------
            if is_likely_attribute(attribute):
                next_line = lines[i + 1]

                if next_line in MARKERS:
                    add_specification(
                        specifications,
                        attribute,
                        next_line,
                        chunk,
                        status=(
                            "standard"
                            if next_line == STANDARD_MARKER
                            else "optional"
                        ),
                    )

                    i += 2
                    continue

            # ---------------------------------------------------------
            # Pattern 2:
            #
            # Attribute
            # Value
            #
            # or:
            #
            # Attribute
            # Value
            # •
            # ---------------------------------------------------------
            normalized_attribute = attribute
            if re.fullmatch(
                r"maximum\s+patient\s+weight(?:\s*\([^)]*\))?",
                attribute,
                re.IGNORECASE,
            ):
                normalized_attribute = "Maximum Patient Weight"

            if not is_likely_attribute(normalized_attribute):
                i += 1
                continue

            next_line = lines[i + 1]

            parsed_value = parse_value(next_line)

            if not is_valid_attribute_value_pair(
                normalized_attribute,
                next_line,
                parsed_value,
                chunk=chunk,
            ):
                i += 1
                continue

            status = None

            # Check optional/standard marker after the value.
            if i + 2 < len(lines):
                marker = lines[i + 2]

                if marker in MARKERS:
                    status = (
                        "standard"
                        if marker == STANDARD_MARKER
                        else "optional"
                    )

                    add_specification(
                        specifications,
                        normalized_attribute,
                        next_line,
                        chunk,
                        status=status,
                    )

                    i += 3
                    continue

            add_specification(
                specifications,
                normalized_attribute,
                next_line,
                chunk,
                source_evidence=f"{attribute}\n{next_line}",
            )

            i += 2

    return specifications


def find_input_files():
    """
    Find production chunk files.

    Sample files are intentionally excluded.
    """
    return [
        path
        for path in PROCESSED_DIR.glob("*_chunks.json")
        if not path.name.startswith("sample_")
    ]


def process_documents():
    """
    Process all production chunk files and save structured specifications.
    """
    input_files = find_input_files()

    if not input_files:
        print("No production chunk files found.")
        return

    for input_path in input_files:
        print(f"\nProcessing: {input_path.name}")

        with open(input_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        chunks = data["chunks"]

        print(f"Total chunks: {len(chunks)}")

        product_name = None

        for chunk in chunks:
            if chunk.get("product"):
                product_name = chunk["product"]
                break

        if product_name is None:
            product_name = input_path.stem.replace("_chunks", "")

        specifications = extract_specifications_from_chunks(
            chunks,
            product_name,
        )

        structured_product = {
            "product_family": product_name,
            "model": None,
            "variant": None,
            "configuration": None,
            "specifications": specifications,
            "relationships": [],
        }

        output_data = {
            "products": [structured_product]
        }

        output_path = (
            PROCESSED_DIR
            / f"{input_path.stem.replace('_chunks', '')}_specifications.json"
        )

        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(
                output_data,
                file,
                indent=4,
                ensure_ascii=False,
            )

        print(f"Extracted {len(specifications)} specifications.")
        print(f"Saved to: {output_path}")


if __name__ == "__main__":
    process_documents()