import re


def normalize_unit(unit):
    """
    Convert different representations of the same unit
    into one standard form.
    """

    if not unit:
        return None

    unit = unit.strip().lower()

    unit_aliases = {
        # Time
        "hour": "hours",
        "hours": "hours",
        "hr": "hours",
        "hrs": "hours",

        "minute": "minutes",
        "minutes": "minutes",
        "min": "minutes",
        "mins": "minutes",

        "second": "seconds",
        "seconds": "seconds",
        "sec": "seconds",
        "secs": "seconds",

        # Weight
        "kg": "kg",
        "kgs": "kg",
        "kilogram": "kg",
        "kilograms": "kg",

        "g": "g",
        "gram": "g",
        "grams": "g",

        # Length
        "mm": "mm",
        "cm": "cm",
        "m": "m",

        "inch": "inch",
        "inches": "inch",
        "in": "inch",

        # Medical / technical
        "bpm": "bpm",

        "ml/hr": "ml/hr",
        "ml/h": "ml/hr",

        "l/min": "L/min",
        "l/m": "L/min",

        "samples/sec": "samples/sec",
        "sample/sec": "samples/sec",

        # Percentage
        "%": "%",
        "percent": "%",

        # Temperature
        "°c": "°C",
        "c": "°C"
    }

    return unit_aliases.get(unit, unit)


def parse_boolean(text):
    """
    Detect boolean specification values.
    """

    normalized = text.strip().lower()

    true_values = [
        "supported",
        "yes",
        "available",
        "included",
        "present"
    ]

    false_values = [
        "not supported",
        "no",
        "unavailable",
        "not included",
        "absent"
    ]

    if normalized in true_values:
        return {
            "type": "boolean",
            "value": True
        }

    if normalized in false_values:
        return {
            "type": "boolean",
            "value": False
        }

    return None


def parse_tolerance(text):
    """
    Parse tolerance values such as:

        ±3%
        ± 3%
        +/-3%
        +/- 3%
    """

    pattern = (
        r"(?:±|\+/-)\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"([a-zA-Z%°]+)?"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    value = float(match.group(1))
    unit = normalize_unit(match.group(2))

    return {
        "type": "tolerance",
        "value": value,
        "unit": unit
    }


def parse_multiple(text):
    """
    Parse multiple discrete numerical values.

    Example:

        25/50 mm/sec

    This means the supported values are 25 and 50.
    It is different from a range such as 25-50 mm/sec.
    """

    pattern = (
        r"(\d[\d,]*(?:\.\d+)?)\s*/\s*"
        r"(\d[\d,]*(?:\.\d+)?)\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    first_value = float(match.group(1).replace(",", ""))
    second_value = float(match.group(2).replace(",", ""))

    unit = normalize_unit(match.group(3))

    return {
        "type": "multiple",
        "values": [first_value, second_value],
        "unit": unit
    }


def parse_range(text):
    """
    Parse ranges such as:

        1–1000 ml/hr
        1-1000 ml/hr
        1 to 1000 ml/hr
        70–100%
        10 to 40°C
    """

    pattern = (
        r"(-?\d[\d,]*(?:\.\d+)?)\s*"
        r"(?:–|-|to)\s*"
        r"(-?\d[\d,]*(?:\.\d+)?)\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    minimum = float(match.group(1).replace(",", ""))
    maximum = float(match.group(2).replace(",", ""))

    unit = normalize_unit(match.group(3))

    return {
        "type": "range",
        "min": minimum,
        "max": maximum,
        "unit": unit
    }


def parse_scalar(text):
    """
    Parse a single numerical value.

    Examples:

        5 hours
        4.5 kg
        12.1-inch
        500 samples/sec
        1,000 ml/hr
    """

    pattern = (
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"(?:-|\s*)?"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    value_text = match.group(1).replace(",", "")
    value = float(value_text)

    unit = normalize_unit(match.group(2))

    return {
        "type": "scalar",
        "value": value,
        "unit": unit
    }


def parse_categorical(text):
    """
    Handle non-numeric specification values.

    Examples:

        Standard
        Optional
        Configurable
    """

    normalized = text.strip().lower()

    categories = [
        "standard",
        "optional",
        "included",
        "configurable"
    ]

    if normalized in categories:
        return {
            "type": "categorical",
            "value": text.strip()
        }

    return None


def parse_value(text):
    """
    Convert a raw specification value into
    a structured representation.

    Possible types:

        scalar
        range
        multiple
        tolerance
        boolean
        categorical
        not_available
        unknown
    """

    # Handle None
    if text is None:
        return {
            "type": "unknown",
            "raw": text
        }

    # Convert to string and remove whitespace
    text = str(text).strip()

    # Empty value
    if not text:
        return {
            "type": "unknown",
            "raw": text
        }

    normalized = text.lower()

    # Explicitly unavailable / not specified
    if normalized in [
        "n/a",
        "na",
        "not available",
        "not specified"
    ]:
        return {
            "type": "not_available",
            "raw": text
        }

    # Boolean
    result = parse_boolean(text)

    if result:
        return result

    # Multiple discrete values
    result = parse_multiple(text)

    if result:
        return result

    # Tolerance
    result = parse_tolerance(text)

    if result:
        return result

    # Range
    result = parse_range(text)

    if result:
        return result

    # Scalar
    result = parse_scalar(text)

    if result:
        return result

    # Categorical
    result = parse_categorical(text)

    if result:
        return result

    # Unknown
    return {
        "type": "unknown",
        "raw": text
    }