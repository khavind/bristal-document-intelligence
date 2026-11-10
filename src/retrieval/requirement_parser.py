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
    "maximum lift capacity": "Maximum Lift Capacity",
    "safe working load": "Safe Working Load",
    "safe work load": "Safe Working Load",
    "working load": "Safe Working Load",
    "load capacity": "Safe Working Load",
    "patient load": "Patient Load",
    "maximum patient weight": "Maximum Patient Weight",
    "patient weight": "Maximum Patient Weight",
    "permissible patient weight": "Permissible Load",
    "permissible patient load": "Permissible Load",
    "permissible load": "Permissible Load",
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


def normalize_component(value):
    """Normalize whitespace and case without inferring component synonyms."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def find_component(query):
    """Find an explicitly named component adjacent to a supported load attribute."""
    text = normalize_query(query)
    quantity = r"(?:maximum\s+lift\s+capacity|maximum\s+patient\s+weight)"
    patterns = (
        rf"\b{quantity}\s+(?:for|of)\s+(?:the\s+)?"
        r"(bed|foot\s+section)\b",
        rf"\b{quantity}\s*[-:]\s*"
        r"(bed|foot\s+section)\b",
        rf"\b(bed|foot\s+section)\s+{quantity}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            component = match.group(1)
            return "Foot section" if normalize_component(component) == "foot section" else "Bed"
    return None


def find_configuration_scope(query):
    """Return only explicit PST-style configuration qualifiers in a requirement."""
    text = normalize_query(query)
    configuration_terms = []
    for pattern, label in (
        (r"\bcarbon\s*1200\b", "Carbon 1200"),
        (r"\bcarbon\s*600\b", "Carbon 600"),
        (r"\bseat\s+section\s+extension\b", "Seat section extension"),
        (r"\buniversal\s+plate\b", "Universal plate"),
        (r"\bextension\s+unit\b", "Extension unit"),
        (r"\bshoulder\s+chair\b", "Shoulder chair"),
        (r"\bleg\s+section\b", "Leg section"),
        (r"\bhead\s+section\b", "Head section"),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            configuration_terms.append(label)

    orientation_match = re.search(
        r"\b(normal|inverted)(?:\s+patient)?(?:\s+orientation)?\b",
        text,
        re.IGNORECASE,
    )
    orientation = (
        orientation_match.group(1).capitalize()
        if orientation_match
        else None
    )
    chapter_match = re.search(
        r"\b(5\s*\.\s*11\s*\.\s*\d+)(?:\s*\(\s*(\d+)\s*\))?",
        text,
        re.IGNORECASE,
    )
    chapter = None
    if chapter_match:
        chapter = re.sub(r"\s+", "", chapter_match.group(1))
        if chapter_match.group(2):
            chapter = f"{chapter} ({chapter_match.group(2)})"
    item_numbers = [
        int(match.group(1))
        for match in re.finditer(
            r"\b(?:item\s*)?\[\s*(\d+)\s*\]",
            text,
            re.IGNORECASE,
        )
    ]
    position_match = re.search(r"\b(pushed in|pulled out)\b", text, re.IGNORECASE)
    position_terms = [position_match.group(1).casefold()] if position_match else []

    if not any(
        (configuration_terms, orientation, chapter, item_numbers, position_terms)
    ):
        return None

    return {
        "configuration_terms": configuration_terms,
        "orientation": orientation,
        "chapter": chapter,
        "item_numbers": item_numbers,
        "position_terms": position_terms,
    }


def _inclination_operator(modifier):
    for symbol, operator in (
        (">=", ">="),
        ("<=", "<="),
        ("≥", ">="),
        ("≤", "<="),
        (">", ">"),
        ("<", "<"),
        ("=", "="),
    ):
        if symbol in modifier:
            return operator

    patterns = (
        (r"(?:greater than or equal to|at least|not less than|above)", ">="),
        (r"(?:less than or equal to|no greater than|not greater than|"
         r"no more than|not more than|at most|up to)", "<="),
        (r"(?:greater than|more than|exceeds)", ">"),
        (r"(?:less than|below|under)", "<"),
        (r"(?:equal to|equals?|exactly)", "="),
    )
    for pattern, operator in patterns:
        if re.search(rf"(?<!\w){pattern}(?!\w)", modifier, re.IGNORECASE):
            return operator
    return "="


def _inclination_condition(query):
    pattern = re.compile(
        r"\b(?:inclination|tilt(?:ed|ing)?|inclined|angle)\b"
        r"(?P<modifier>[^.;,]{0,60}?)"
        r"(?P<value>\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|�)(?![a-z])",
        re.IGNORECASE,
    )
    match = pattern.search(query)
    if not match:
        pattern = re.compile(
            r"(?P<modifier>(?:>=|<=|>|<|=|≥|≤|"
            r"at\s+least|at\s+most|no\s+more\s+than|"
            r"no\s+less\s+than|at)?\s*)"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:degrees?|deg|°|�)(?![a-z])",
            re.IGNORECASE,
        )
        match = pattern.search(query)
    if not match:
        return None
    return {
        "operator": _inclination_operator(match.group("modifier")),
        "value": float(match.group("value")),
        "unit": "degrees",
    }


def find_condition_scope(query):
    """Return explicit operating conditions, marking unrecognized conditions."""
    text = normalize_query(query)
    conditions = {}
    lower = text.casefold()

    unrestricted_functions = bool(
        re.search(
            r"\b(?:without\s+(?:limiting|restricting)\s+"
            r"(?:the\s+)?(?:operating\s+table\s+)?functions?|"
            r"no\s+(?:limits?|restrictions?)\s+(?:on|to)\s+"
            r"(?:the\s+)?(?:operating\s+table\s+)?functions?|"
            r"unrestricted\s+(?:operating\s+table\s+)?functions?|"
            r"all\s+(?:operating\s+table\s+)?functions?\s+available)\b",
            lower,
        )
    )
    unrestricted_operation = bool(
        re.search(
            r"\b(?:unrestricted|unlimited)\s+operation\b|"
            r"\bwithout\s+(?:limiting|restricting)\s+(?:the\s+)?operation\b|"
            r"\bno\s+(?:limits?|restrictions?)\s+(?:on|to)\s+operation\b",
            lower,
        )
    )
    if unrestricted_functions or unrestricted_operation:
        conditions["function_restriction"] = "none"
        conditions["restriction"] = "none"
    elif re.search(
        r"\b(?:without\s+(?:any\s+)?restrictions?|no\s+restrictions?|"
        r"unrestricted|without\s+limits?)\b",
        lower,
    ):
        conditions["restriction"] = "none"
    elif re.search(
        r"\b(?:without\s+(?:any\s+)?travel\s+restrictions?|"
        r"no\s+travel\s+restrictions?)\b",
        lower,
    ):
        conditions["travel_restriction"] = "none"

    if re.search(r"\b(?:reverse\s+)?trendelenburg(?:\s+position)?\b", lower):
        conditions["position"] = (
            "reverse_trendelenburg"
            if re.search(r"\breverse\s+trendelenburg\b", lower)
            else "trendelenburg"
        )

    if re.search(r"\b(?:unevenly|uneven|non[- ]uniformly)\s+loaded\b", lower):
        conditions["load_distribution"] = "uneven"
    elif re.search(r"\bevenly\s+loaded\b", lower):
        conditions["load_distribution"] = "even"

    inclination = _inclination_condition(lower)
    if inclination:
        conditions["inclination"] = inclination

    travel_or_tabletop = (
        r"\b(?:(?:longitudinal\s+)?travel|"
        r"(?:operating\s+)?tabletop|operating\s+table)\b"
    )
    negative_level_travel = re.search(
        r"\b(?:non[\s-]*level|not[\s-]+level)\b.{0,35}"
        + travel_or_tabletop
        + r"|"
        + travel_or_tabletop
        + r".{0,50}\b(?:not|never|cannot|can't)\b"
        r".{0,20}\blevel\b|"
        + travel_or_tabletop
        + r".{0,50}\b(?:must|shall|should)\s+not\b"
        r".{0,20}\blevel\b|"
        + travel_or_tabletop
        + r".{0,30}\bnon[\s-]*level\b",
        lower,
    )
    positive_level_travel = re.search(
        r"\blevel\b.{0,35}"
        + travel_or_tabletop
        + r"|"
        + travel_or_tabletop
        + r".{0,50}\blevel\b",
        lower,
    )
    inclined_travel = re.search(
        r"\binclined\s+(?:(?:longitudinal\s+)?travel|tabletop)\b|"
        + travel_or_tabletop
        + r".{0,35}\binclined\b",
        lower,
    )
    if negative_level_travel:
        conditions["longitudinal_travel"] = "not_level"
    elif positive_level_travel:
        conditions["longitudinal_travel"] = "level"
    elif inclined_travel:
        conditions["longitudinal_travel"] = "not_level"

    unsupported_condition = bool(
        re.search(r"\baccessor(?:y|ies)\b", lower)
        or (
            re.search(
                r"\b(?:supine|prone|side[\s-]*lying|lateral\s+decubitus|"
                r"lithotomy|fowler(?:'s)?|jackknife|beach\s+chair)\b",
                lower,
            )
            and "position" not in conditions
        )
        or (
            re.search(r"\b(?:incline|slope|sloped)\b", lower)
            and not inclination
            and not inclined_travel
        )
        or (
            re.search(r"\b(?:tilt\w*|inclination|angle)\b", lower)
            and not inclination
        )
        or (
            re.search(r"\binclined\b", lower)
            and not inclination
            and not inclined_travel
        )
        or (
            re.search(r"\btravel\b", lower)
            and not any(
                key in conditions
                for key in ("travel_restriction", "longitudinal_travel")
            )
        )
        or (
            re.search(
                r"\b(?:restriction\w*|restricted|unrestricted|limiting|limited)\b",
                lower,
            )
            and not any(
                key in conditions
                for key in (
                    "restriction",
                    "travel_restriction",
                    "function_restriction",
                )
            )
        )
        or (
            re.search(r"\bfunction\w*|\boperation\b", lower)
            and "function_restriction" not in conditions
        )
        or (
            re.search(r"\bloaded\b|\bload distribution\b", lower)
            and "load_distribution" not in conditions
        )
        or (
            re.search(
                r"\b(?:tabletop|operating table)\b.{0,35}"
                r"\b(?:flat|horizontal|inclined|level|sloped|tilted|vertical)\b|"
                r"\b(?:flat|horizontal|inclined|level|non[- ]level|sloped|"
                r"tilted|vertical)\b.{0,35}\b(?:tabletop|operating table)\b",
                lower,
            )
            and "longitudinal_travel" not in conditions
        )
        or (
            re.search(r"\bposition\b", lower)
            and "position" not in conditions
            and not re.search(
                r"\bhead\s+positioning\s+extension\b.{0,30}\b(?:pushed in|pulled out)\b",
                lower,
            )
        )
        or re.search(
            r"\b(?:only if|subject to|provided that|under the condition|"
            r"head[- ]down|foot[- ]down)\b",
            lower,
        )
    )
    if unsupported_condition:
        conditions["unsupported"] = True

    return conditions or None


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


def _find_requirement_operator(query, attribute):
    if normalize_attribute(attribute) != "permissible load":
        return _find_operator(query)

    matches = {}
    query_lower = query.lower()
    for pattern, operator in OPERATOR_PATTERNS:
        for match in re.finditer(pattern, query_lower):
            matches.setdefault(match.span(), (operator, match))

    weight_units = {"kg", "g", "lb", "lbs"}
    weight_matches = []
    for operator, match in matches.values():
        _, unit = find_value_and_unit(query[match.end():])
        if unit and unit.casefold() in weight_units:
            weight_matches.append((operator, match))

    if not weight_matches:
        return None, None
    return max(weight_matches, key=lambda item: item[1].start())


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
    component = find_component(query)
    configuration_scope = find_configuration_scope(query)
    condition_scope = find_condition_scope(query)

    operator, operator_match = _find_requirement_operator(query, attribute)

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
        "component": component,
        "configuration_scope": configuration_scope,
        "condition_scope": condition_scope,
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