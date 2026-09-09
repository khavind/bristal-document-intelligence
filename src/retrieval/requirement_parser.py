import re


# --------------------------------------------------
# Convert natural language operators into symbols
# --------------------------------------------------

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
    (r"<=", "<="),
    (r">", ">"),
    (r"<", ">"),
    (r"=", "=")
]


# --------------------------------------------------
# Attribute aliases
# --------------------------------------------------

ATTRIBUTE_ALIASES = {
    "battery backup": "Battery Backup",
    "battery": "Battery Backup",
    "backup": "Battery Backup",

    "weight": "Weight",

    "ecg channels": "ECG Channels",
    "ecg channel": "ECG Channels",

    "display size": "Display Size",
    "display": "Display Size",

    "temperature channels": "Temperature Channels",
    "temperature channel": "Temperature Channels"
}


# --------------------------------------------------
# Find attribute
# --------------------------------------------------

def find_attribute(query):

    query_lower = query.lower()

    aliases = sorted(
        ATTRIBUTE_ALIASES.keys(),
        key=len,
        reverse=True
    )

    for alias in aliases:

        if alias in query_lower:
            return ATTRIBUTE_ALIASES[alias]

    return None


# --------------------------------------------------
# Find operator
# --------------------------------------------------

def find_operator(query):

    query_lower = query.lower()

    for pattern, operator in OPERATOR_PATTERNS:

        if re.search(pattern, query_lower):
            return operator

    return None


# --------------------------------------------------
# Find numeric value and unit
# --------------------------------------------------

def find_value_and_unit(query):

    pattern = (
        r"(\d+(?:\.\d+)?)\s*"
        r"(hours?|hrs?|kg|inch|inches|bpm|samples/sec)"
    )

    match = re.search(
        pattern,
        query.lower()
    )

    if not match:
        return None, None

    value = float(match.group(1))

    unit = match.group(2)

    # Normalize units

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


# --------------------------------------------------
# Parse complete requirement
# --------------------------------------------------

def parse_requirement(query):

    attribute = find_attribute(query)

    operator = find_operator(query)

    value, unit = find_value_and_unit(query)

    return {
        "original_query": query,
        "attribute": attribute,
        "operator": operator,
        "value": value,
        "unit": unit
    }


# --------------------------------------------------
# Test parser only when this file is run directly
# --------------------------------------------------

if __name__ == "__main__":

    query = input("Enter your requirement: ")

    requirement = parse_requirement(query)

    print("\n--- Parsed Requirement ---\n")

    print(
        f"Original Query : "
        f"{requirement['original_query']}"
    )

    print(
        f"Attribute      : "
        f"{requirement['attribute']}"
    )

    print(
        f"Operator       : "
        f"{requirement['operator']}"
    )

    print(
        f"Value          : "
        f"{requirement['value']}"
    )

    print(
        f"Unit           : "
        f"{requirement['unit']}"
    )