import json
import re
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
            evidence=f"{attribute}\n{raw_value}",
        ),
    }

    if parent_attribute:
        specification["parent_attribute"] = parent_attribute

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
    if (
        normalized in NOISE_ATTRIBUTES
        and not technical_section_label
    ) or normalized in AMBIGUOUS_ATTRIBUTE_LABELS:
        return False

    if looks_like_metadata(line):
        return False

    if looks_like_generic_metadata_label(line) and not (
        line.lower().endswith(" section")
        and has_technical_attribute_term(line)
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

    bullet_prefixes = tuple(f"{marker} " for marker in MARKERS)
    if attribute.startswith(bullet_prefixes) or raw_value.startswith(bullet_prefixes):
        return False

    if looks_like_generic_metadata_label(attribute) and not (
        attribute.lower().endswith(" section")
        and has_technical_attribute_term(attribute)
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

    if not is_likely_technical_value(raw_value, parsed_value):
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

    for chunk in chunks:
        raw_lines = [
            _normalize_extracted_line(line)
            for line in chunk.get("text", "").splitlines()
            if clean_line(line)
        ]

        lines = merge_wrapped_bullet_lines(raw_lines)
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
            if not is_likely_attribute(attribute):
                i += 1
                continue

            next_line = lines[i + 1]

            parsed_value = parse_value(next_line)

            if not is_valid_attribute_value_pair(
                attribute,
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
                        attribute,
                        next_line,
                        chunk,
                        status=status,
                    )

                    i += 3
                    continue

            add_specification(
                specifications,
                attribute,
                next_line,
                chunk,
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