import re


QUERY_TYPES = {
    "PRODUCT_PRESENCE",
    "PRODUCT_COUNT",
    "FEATURE_EXISTENCE",
    "INVENTORY_COUNT",
    "NUMERIC_SPECIFICATION",
    "UNSUPPORTED_OR_AMBIGUOUS",
}


def normalize_query(query):
    """Normalize whitespace and quotation marks surrounding a complete query."""
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    return text.strip(" \t\r\n\"'“”‘’")


# ---------------------------------------------------------
# Operator patterns
# ---------------------------------------------------------

OPERATOR_PATTERNS = [
    (r"\bat least\b", ">="),
    (r"\bminimum\b", ">="),
    (r"\bor more\b", ">="),
    (r"\bnot less than\b", ">="),
    (r"\bgreater than or equal to\b", ">="),

    (r"\bat most\b", "<="),
    (r"\bmaximum\b", "<="),
    (r"\bor less\b", "<="),
    (r"\bnot more than\b", "<="),
    (r"\bless than or equal to\b", "<="),

    (r"\bmore than\b", ">"),
    (r"\bgreater than\b", ">"),
    (r"\babove\b", ">"),
    (r"\bless than\b", "<"),
    (r"\bfewer than\b", "<"),
    (r"\bbelow\b", "<"),

    (r">=", ">="),
    (r"<=", "<="),
    (r">", ">"),
    (r"<", "<"),
    (r"=", "="),
    (r"\bexactly\b", "="),
    (r"\bequals?\s+to\b", "="),
]

# ---------------------------------------------------------
# Attribute aliases
# ---------------------------------------------------------

ATTRIBUTE_ALIASES = {
    "safe working load": "Safe Working Load",
    "safe work load": "Safe Working Load",
    "working load": "Safe Working Load",
    "load capacity": "Safe Working Load",
    "patient load": "Patient Load",
    "maximum patient weight": "Maximum Patient Weight",
    "patient weight": "Maximum Patient Weight",
    "maximum load": "Maximum Load",
    "operating table load": "Load",
    "load": "Load",
    "battery backup": "Battery Backup",
    "battery duration": "Battery Backup",
    "backup": "Battery Backup",
    "trendelenburg": "Trendelenburg Positioning",
    "trendelenburg positioning": "Trendelenburg Positioning",
    "head-of-bed angle": "Head-of-bed Angle",
    "head of bed angle": "Head-of-bed Angle",
    "height adjustment": "Height Adjustment",
    "bed height": "Height",
    "table height": "Height",
    "height": "Height",
    "width": "Width",
    "bed width": "Width",
    "table width": "Width",
    "length": "Length",
    "bed length": "Length",
    "table length": "Length",
    "siderail height": "Siderail Height",
    "side rail height": "Siderail Height",
    "rotation": "Rotation",
    "360 degree rotation": "Rotation",
    "product weight": "Product Weight",
    "device weight": "Product Weight",
    "weight": "Product Weight",
    "safe weight": "Product Weight",

    "ecg channels": "ECG Channels",
    "ecg channel": "ECG Channels",

    "display size": "Display Size",
    "screen size": "Display Size",

    "temperature channels": "Temperature Channels",
    "temperature channel": "Temperature Channels",

    "nibp measurement": "NIBP Measurement",
    "nibp": "NIBP Measurement",

    "spo2 range": "SpO₂ Range",
    "spo2": "SpO₂ Range",

    "flow rate": "Flow Rate",

    "sampling rate": "Sampling Rate",
}


# ---------------------------------------------------------
# Capability / boolean keywords
# ---------------------------------------------------------

CAPABILITY_PATTERNS = [
    r"\brequired\b",
    r"\bmust be supported\b",
    r"\bshould be supported\b",
    r"\bmust be available\b",
    r"\bshould be available\b",
    r"\bis required\b",
    r"\bis supported\b",
    r"\bis available\b",
]


# ---------------------------------------------------------
# Find attribute
# ---------------------------------------------------------

def _normalize_attribute_text(value):
    text = str(value or "").lower().replace("₂", "2")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_attribute(value):
    """Return the shared canonical form for a recognized or literal attribute."""
    text = _normalize_attribute_text(value)

    aliases = sorted(
        ATTRIBUTE_ALIASES.items(),
        key=lambda item: len(_normalize_attribute_text(item[0])),
        reverse=True,
    )
    for alias, canonical in aliases:
        normalized_alias = _normalize_attribute_text(alias)
        if re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", text):
            return _normalize_attribute_text(canonical)

    context_words = {"bed", "table", "operating", "device", "system"}
    return " ".join(word for word in text.split() if word not in context_words)


def attributes_equivalent(left, right):
    """Use exact canonical identity; related measurements are not interchangeable."""
    left_normalized = normalize_attribute(left)
    right_normalized = normalize_attribute(right)
    return bool(left_normalized and right_normalized and left_normalized == right_normalized)


def find_attribute(query):
    text = _normalize_attribute_text(query)

    for alias, canonical in sorted(
        ATTRIBUTE_ALIASES.items(),
        key=lambda item: len(_normalize_attribute_text(item[0])),
        reverse=True,
    ):
        normalized_alias = _normalize_attribute_text(alias)
        if re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", text):
            return canonical

    return None


# ---------------------------------------------------------
# Find operator
# ---------------------------------------------------------

def _find_operator(query):
    query_lower = query.lower()
    for pattern, operator in OPERATOR_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            return operator, match
    return None, None


def find_operator(query):
    operator, _ = _find_operator(query)
    return operator


# ---------------------------------------------------------
# Find numeric value and unit
# ---------------------------------------------------------

def find_value_and_unit(query):

    pattern = (
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:(hours?|hrs?|minutes?|mins?|seconds?|secs?|"
        r"kilograms?|kgs?|grams?|kg|g|pounds?|lbs?|lb|"
        r"centimeters?|cm|millimeters?|mm|meters?|m|inches|inch|in|"
        r"millivolts?|mv|kilovolts?|kv|volts?|v|"
        r"megahertz|mhz|gigahertz|ghz|kilohertz|khz|hertz|hz|"
        r"ml\s*/\s*(?:hr|h)|l\s*/\s*(?:hr|h)|"
        r"degrees?|deg|°|bpm|samples?/sec)"
        r"(?![a-z0-9]))?"
    )

    match = re.search(pattern, query.lower())

    if not match:
        return None, None

    value = float(match.group(1))
    unit = match.group(2)

    if unit in ["hour", "hours", "hr", "hrs"]:
        unit = "hours"
    elif unit in ["minute", "minutes", "min", "mins"]:
        unit = "minutes"
    elif unit in ["second", "seconds", "sec", "secs"]:
        unit = "seconds"
    elif unit in ["inch", "inches", "in"]:
        unit = "inch"
    elif unit in ["meter", "meters"]:
        unit = "m"
    elif unit in ["centimeter", "centimeters"]:
        unit = "cm"
    elif unit in ["millimeter", "millimeters"]:
        unit = "mm"
    elif unit in ["cm", "mm", "m"]:
        unit = unit
    elif unit in ["kilogram", "kilograms", "kgs"]:
        unit = "kg"
    elif unit in ["gram", "grams"]:
        unit = "g"
    elif unit in ["pound", "pounds"]:
        unit = "lb"
    elif unit in ["kg", "g", "lb", "lbs"]:
        unit = unit
    elif unit in ["v", "mv", "kv"]:
        unit = unit
    elif unit in ["hz", "khz", "mhz", "ghz"]:
        unit = unit
    elif unit in ["degree", "degrees", "deg", "°"]:
        unit = "°"
    elif unit == "bpm":
        unit = "bpm"
    elif unit == "samples/sec":
        unit = "samples/sec"
    elif unit:
        unit = re.sub(r"\s+", "", unit)
        if unit in {"ml/hr", "ml/h"}:
            unit = "ml/hr"
        elif unit in {"l/hr", "l/h"}:
            unit = "l/hr"

    return value, unit


# ---------------------------------------------------------
# Generic query classification
# ---------------------------------------------------------

def extract_search_terms(query):
    """Return useful non-stopword terms from a user query."""
    if not query:
        return []

    stop_words = {
        "a", "an", "and", "are", "at", "be", "by", "does", "for",
        "from", "have", "has", "in", "is", "its", "of", "on", "or",
        "present", "should", "the", "this", "to", "what", "which",
        "with", "yes", "no", "must", "doesn", "isn", "not", "there",
        "than", "more", "less", "support", "supports", "supporting",
        "suitable", "available", "include", "includes", "positioning",
        "product", "products", "document", "documents", "bed", "table"
    }

    terms = re.findall(r"[a-z0-9]+", query.lower())
    return [term for term in terms if term not in stop_words and len(term) > 1]


def classify_query(query):
    """Classify a user query into a generic requirement type."""
    intent = classify_query_intent(query)
    if intent == "NUMERIC_SPECIFICATION":
        return "technical"
    if intent == "FEATURE_EXISTENCE":
        normalized = normalize_query(query).lower()
        if re.search(r"\b(support|supports|supporting|include|includes|required)\b", normalized):
            return "capability"
        return "presence"
    if intent == "PRODUCT_PRESENCE":
        return "presence"
    if intent in {"PRODUCT_COUNT", "INVENTORY_COUNT"}:
        return "unsupported"

    q = normalize_query(query).lower()
    if not q:
        return "unsupported"

    if re.search(r"\b(which|what)\b.*\b(product|model|device|bed|table)\b.*\b(satisfy|satisfies|meets|matches|qualifies)\b", q):
        return "selection"

    if re.search(
        r">=|<=|>|<|=|\b(at least|at most|minimum|maximum|more than|"
        r"greater than|less than|fewer than|or more|or less|exactly|equal to|equals to)\b",
        q,
    ):
        return "technical"

    if re.search(r"\b(is|are|does|has|have|can)\b.*\b(present|available|supported|included)\b", q):
        return "presence"

    if re.search(r"\b(support|supports|supporting|include|includes|available|required)\b", q):
        return "capability"

    if re.search(r"\b(not\s+present|not\s+available|without|absent|lacks|no\s+support)\b", q):
        return "presence"

    return "unsupported"


def classify_query_intent(query):
    """Classify a complete natural-language query before numeric parsing."""
    q = normalize_query(query).lower()
    if not q:
        return "UNSUPPORTED_OR_AMBIGUOUS"

    if re.search(
        r"\b(in stock|inventory|stock quantity|stock level|on hand|"
        r"available for shipment|units? for shipment)\b",
        q,
    ):
        return "INVENTORY_COUNT"

    if re.search(
        r"\b(how many|count|number of)\b",
        q,
    ):
        if re.search(
            r"\b(model|models|product|products|bed|beds|device|devices)\b",
            q,
        ) and re.search(
            r"\b(catalogue|catalog|documented|listed|product|products|our)\b",
            q,
        ):
            return "PRODUCT_COUNT"
        return "UNSUPPORTED_OR_AMBIGUOUS"

    if re.search(
        r"\b(at least|at most|minimum|maximum|more than|greater than|"
        r"above|below|less than|fewer than|or more|or less|exactly|equal to|"
        r"equals to|greater than or equal to|less than or equal to)\b|"
        r">=|<=|(?<![<>=])>(?!=)|(?<![<>=])<(?![=>])|(?<![<>=])=(?!=)",
        q,
    ):
        return "NUMERIC_SPECIFICATION"

    catalogue_context = bool(
        re.search(r"\b(catalogue|catalog|listed|documented|our products)\b", q)
    )
    product_identity = bool(
        re.search(
            r"\b(product|products|model|models|device|devices|bed|beds|"
                r"table|tables|hospital bed|birthing bed)\b",
            q,
        )
    )
    if catalogue_context and product_identity:
        return "PRODUCT_PRESENCE"
    if catalogue_context and re.search(
        r"\b(?:is|are|do we have|does the catalogue contain)\b.*"
        r"\b(?:listed|documented|catalogue|catalog)\b",
        q,
    ):
        return "PRODUCT_PRESENCE"

    if re.search(r"\b(which|does|do|is|are|has|have)\b", q) and re.search(
        r"\b(support|supports|supporting|have|has|include|includes|feature|"
        r"available|present|trendelenburg|height adjustment|battery backup)\b",
        q,
    ):
        return "FEATURE_EXISTENCE"

    return "UNSUPPORTED_OR_AMBIGUOUS"


def is_capability_requirement(query):
    query_lower = normalize_query(query).lower()

    for pattern in CAPABILITY_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


# ---------------------------------------------------------
# Parse complete requirement
# ---------------------------------------------------------

def parse_requirement(query):

    attribute = find_attribute(query)

    operator, operator_match = _find_operator(query)

    value_text = query[operator_match.end():] if operator_match else query
    value, unit = find_value_and_unit(value_text)

    # If this is a capability requirement,
    # interpret it as "must be supported".
    if is_capability_requirement(query):

        operator = "="
        value = 1
        unit = None

    return {
        "original_query": query,
        "attribute": attribute,
        "operator": operator,
        "value": value,
        "unit": unit,
        "query_type": classify_query(query),
        "search_terms": extract_search_terms(query),
    }


# ---------------------------------------------------------
# Testing
# ---------------------------------------------------------

if __name__ == "__main__":

    test_queries = [

        "Battery backup must be at least 4 hours",

        "Weight should be at most 8 kg",

        "ECG channels >= 5",

        "Display size >= 10 inch",

        "Temperature channels more than 4",

        "NIBP measurement must be supported",

        "NIBP is required",

        "NIBP should be available",

    ]

    print("\n--- Requirement Parser Test ---\n")

    for query in test_queries:

        requirement = parse_requirement(query)

        print(f"Original Query : {requirement['original_query']}")
        print(f"Attribute      : {requirement['attribute']}")
        print(f"Operator       : {requirement['operator']}")
        print(f"Value          : {requirement['value']}")
        print(f"Unit           : {requirement['unit']}")
        print("-" * 60)