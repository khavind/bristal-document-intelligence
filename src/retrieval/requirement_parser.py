import re


# ---------------------------------------------------------
# Operator patterns
# ---------------------------------------------------------

OPERATOR_PATTERNS = [
    (r"\bat least\b", ">="),
    (r"\bminimum\b", ">="),
    (r"\bor more\b", ">="),
    (r"\bnot less than\b", ">="),

    (r"\bat most\b", "<="),
    (r"\bmaximum\b", "<="),
    (r"\bor less\b", "<="),
    (r"\bnot more than\b", "<="),

    (r"\bmore than\b", ">"),
    (r"\bless than\b", "<"),

    (r">=", ">="),
    (r"<=", "<"),
    (r">", ">"),
    (r"<", "<"),
    (r"=", "="),
]


# ---------------------------------------------------------
# Attribute aliases
# ---------------------------------------------------------

ATTRIBUTE_ALIASES = {
    "battery backup": "Battery Backup",
    "battery": "Battery Backup",
    "backup": "Battery Backup",

    "weight": "Weight",

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

def find_attribute(query):
    query_lower = query.lower()

    # Longer aliases first
    aliases = sorted(
        ATTRIBUTE_ALIASES.keys(),
        key=len,
        reverse=True
    )

    for alias in aliases:
        if alias in query_lower:
            return ATTRIBUTE_ALIASES[alias]

    return None


# ---------------------------------------------------------
# Find operator
# ---------------------------------------------------------

def find_operator(query):
    query_lower = query.lower()

    for pattern, operator in OPERATOR_PATTERNS:
        if re.search(pattern, query_lower):
            return operator

    return None


# ---------------------------------------------------------
# Find numeric value and unit
# ---------------------------------------------------------

def find_value_and_unit(query):

    pattern = (
        r"(\d+(?:\.\d+)?)\s*"
        r"(hours?|hrs?|kg|inch|inches|bpm|samples/sec)?"
    )

    match = re.search(pattern, query.lower())

    if not match:
        return None, None

    value = float(match.group(1))
    unit = match.group(2)

    if unit in ["hour", "hours", "hr", "hrs"]:
        unit = "hours"

    elif unit in ["inch", "inches"]:
        unit = "inch"

    elif unit == "kg":
        unit = "kg"

    elif unit == "bpm":
        unit = "bpm"

    elif unit == "samples/sec":
        unit = "samples/sec"

    return value, unit


# ---------------------------------------------------------
# Detect capability requirement
# ---------------------------------------------------------

def is_capability_requirement(query):
    query_lower = query.lower()

    for pattern in CAPABILITY_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


# ---------------------------------------------------------
# Parse complete requirement
# ---------------------------------------------------------

def parse_requirement(query):

    attribute = find_attribute(query)

    operator = find_operator(query)

    value, unit = find_value_and_unit(query)

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
        "unit": unit
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