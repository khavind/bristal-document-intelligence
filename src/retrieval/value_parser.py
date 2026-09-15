import re


# --------------------------------------------------
# Unit Normalization
# --------------------------------------------------

def normalize_unit(unit):
    """
    Convert different representations of the same unit
    into one standard form.
    """

    if unit is None:
        return None

    unit = str(unit).strip()

    if not unit:
        return None

    # Normalize degree symbol variants
    unit = unit.replace("º", "°")

    # Normalize spaces around slash
    unit = re.sub(r"\s*/\s*", "/", unit)

    # Normalize repeated whitespace
    unit = re.sub(r"\s+", " ", unit)

    unit = unit.lower()

    unit_aliases = {

        # --------------------------------------------------
        # Time
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Weight
        # --------------------------------------------------

        "kg": "kg",
        "kgs": "kg",
        "kilogram": "kg",
        "kilograms": "kg",

        "g": "g",
        "gram": "g",
        "grams": "g",

        "lb": "lb",
        "lbs": "lb",

        # --------------------------------------------------
        # Length
        # --------------------------------------------------

        "mm": "mm",

        "cm": "cm",

        "m": "m",

        "inch": "inch",
        "inches": "inch",
        "in": "inch",

        # --------------------------------------------------
        # Medical / Technical
        # --------------------------------------------------

        "bpm": "bpm",

        "ml/hr": "ml/hr",
        "ml/h": "ml/hr",

        "l/min": "L/min",
        "l/m": "L/min",

        "samples/sec": "samples/sec",
        "sample/sec": "samples/sec",
        "sample/s": "samples/sec",

        # --------------------------------------------------
        # Percentage
        # --------------------------------------------------

        "%": "%",
        "percent": "%",

        # --------------------------------------------------
        # Temperature
        # --------------------------------------------------

        "°c": "°C",
        "celsius": "°C",

        # --------------------------------------------------
        # Angle
        # --------------------------------------------------

        "°": "°",

        # --------------------------------------------------
        # Electrical / Technical
        # --------------------------------------------------

        "v": "V",
        "kv": "kV",

        "hz": "Hz",
        "khz": "kHz",
        "mhz": "MHz",
        "ghz": "GHz",

        "va": "VA",
        "ah": "Ah",

        "mbar": "mbar"
    }

    return unit_aliases.get(unit, unit)


# --------------------------------------------------
# Boolean Parser
# --------------------------------------------------

def parse_boolean(text):
    """
    Detect boolean specification values.

    Examples:
        Supported
        Yes
        Available
        Not supported
        No
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


# --------------------------------------------------
# Tolerance Parser
# --------------------------------------------------

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

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    value = float(match.group(1))

    unit = normalize_unit(
        match.group(2)
    )

    return {
        "type": "tolerance",
        "value": value,
        "unit": unit
    }


# --------------------------------------------------
# Multiple Value Parser
# --------------------------------------------------
def parse_multiple(text):
    pattern = (
        r"(\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
        r"\s*/\s*"
        r"(\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    first_value = float(match.group(1).replace(",", ""))
    second_value = float(match.group(3).replace(",", ""))

    first_unit = normalize_unit(match.group(2))
    second_unit = normalize_unit(match.group(4)) or first_unit

    if first_unit and second_unit and first_unit != second_unit:
        return None

    return {
        "type": "multiple",
        "values": [
            first_value,
            second_value
        ],
        "unit": second_unit or first_unit
    }
# --------------------------------------------------
# Dimension / Compound Value Parser
# --------------------------------------------------

def parse_dimension(text):
    """
    Parse compound dimensions such as:

        372 mm x 311 mm
        916 mm x 527 mm x 25 mm

    The unit may be written after each value
    or omitted after later values.

    Examples:

        372 mm x 311 mm
        372 mm x 311
        916 mm x 527 mm x 25 mm
    """

    pattern = (
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+)"
        r"\s*x\s*"
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+)?"
        r"(?:"
        r"\s*x\s*"
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+)?"
        r")?"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    # First value
    first_value = float(
        match.group(1).replace(",", "")
    )

    first_unit = normalize_unit(
        match.group(2)
    )

    # Second value
    second_value = float(
        match.group(3).replace(",", "")
    )

    second_unit = (
        normalize_unit(match.group(4))
        if match.group(4)
        else first_unit
    )

    # Units must be compatible/same
    if second_unit != first_unit:
        return None

    values = [
        first_value,
        second_value
    ]

    # Third value, if present
    if match.group(5):

        third_value = float(
            match.group(5).replace(",", "")
        )

        third_unit = (
            normalize_unit(match.group(6))
            if match.group(6)
            else first_unit
        )

        if third_unit != first_unit:
            return None

        values.append(third_value)

    return {
        "type": "compound",
        "values": values,
        "unit": first_unit,
        "separator": "x"
    }


# --------------------------------------------------
# Paired Value Parser
# --------------------------------------------------
def parse_paired(text):
    """
    Parse two related numerical values separated by '/'.

    Examples:

        45°/45°
        30°/30°

    This is different from 'multiple' values such as:

        25/50 mm/sec

    because the two values represent related positions
    or directions rather than interchangeable options.
    """

    pattern = (
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+)?"
        r"\s*/\s*"
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+)?"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    first_value = float(
        match.group(1).replace(",", "")
    )

    first_unit = normalize_unit(
        match.group(2)
    )

    second_value = float(
        match.group(3).replace(",", "")
    )

    second_unit = (
        normalize_unit(match.group(4))
        if match.group(4)
        else first_unit
    )

    # Only degree-based paired values are treated as related pairs.
    # Other slash-separated values such as Hz/Hz are discrete options.
    if first_unit not in (None, "°") or second_unit not in (None, "°"):
        return None

    unit = first_unit or second_unit

    if unit != "°":
        return None

    return {
        "type": "paired",
        "values": [
            first_value,
            second_value
        ],
        "unit": unit,
        "separator": "/"
    }
# --------------------------------------------------
# Range Parser
# --------------------------------------------------
def parse_range(text):
    pattern = (
        r"^\s*"
        r"([+-]?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
        r"\s*(?:–|-|to)\s*"
        r"([+-]?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
        r"\s*$"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    first_value = float(match.group(1).replace(",", ""))
    second_value = float(match.group(3).replace(",", ""))

    first_unit = normalize_unit(match.group(2))
    second_unit = normalize_unit(match.group(4))

    if first_unit and second_unit and first_unit != second_unit:
        return None

    return {
        "type": "range",
        "min": min(first_value, second_value),
        "max": max(first_value, second_value),
        "unit": second_unit or first_unit
    }
# --------------------------------------------------
# Scalar Parser
# --------------------------------------------------
def parse_mixed(text):
    pattern = (
        r"^\s*"
        r"([+-]?\d[\d,]*(?:\.\d+)?)"
        r"\s+"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)"
        r"\s+"
        r"(.+?)"
        r"\s*$"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    numeric_value = match.group(1)
    unit = match.group(2)
    description = match.group(3).strip()

    parsed_measurement = parse_scalar(
        f"{numeric_value} {unit}"
    )

    if not parsed_measurement:
        return None

    return {
        "type": "mixed",
        "raw": text.strip(),
        "parsed_value": parsed_measurement,
        "description": description
    }

def parse_scalar(text):
    pattern = (
        r"^\s*"
        r"(-?\d[\d,]*(?:\.\d+)?)"
        r"\s*"
        r"(?:-|\s*)?"
        r"([a-zA-Z%°]+(?:\s*/\s*[a-zA-Z]+)?)?"
        r"\s*$"
    )

    match = re.fullmatch(
        pattern,
        text.strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    value = float(match.group(1).replace(",", ""))
    unit = normalize_unit(match.group(2))

    return {
        "type": "scalar",
        "value": value,
        "unit": unit
    }


# --------------------------------------------------
# Categorical Parser
# --------------------------------------------------

def parse_categorical(text):
    """
    Handle valid non-numeric specification values.
    """

    normalized = text.strip()

    if not normalized:
        return None

    if normalized in ["—", "-", "–"]:
        return None

    return {
        "type": "categorical",
        "value": normalized
    }

# --------------------------------------------------
# Main Value Parser
# --------------------------------------------------

def parse_value(text):
    """
    Convert a raw specification value into
    a structured representation.

    Possible types:

        scalar
        range
        multiple
        paired
        compound
        tolerance
        boolean
        categorical
        not_available
        unknown
    """

    # --------------------------------------------------
    # Handle None
    # --------------------------------------------------

    if text is None:
        return {
            "type": "unknown",
            "raw": text
        }

    # --------------------------------------------------
    # Convert to string
    # --------------------------------------------------

    text = str(text).strip()

    # --------------------------------------------------
    # Empty value
    # --------------------------------------------------

    if not text:
        return {
            "type": "unknown",
            "raw": text
        }

    normalized = text.lower()

    # --------------------------------------------------
    # Explicitly unavailable / not specified
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Boolean
    # --------------------------------------------------

    result = parse_boolean(text)

    if result:
        return result

    # --------------------------------------------------
    # Compound dimensions
    # --------------------------------------------------

    result = parse_dimension(text)

    if result:
        return result

    # --------------------------------------------------
    # Paired values
    # --------------------------------------------------

    result = parse_paired(text)

    if result:
        return result

    # --------------------------------------------------
    # Multiple discrete values
    # --------------------------------------------------

    result = parse_multiple(text)

    if result:
        return result

    # --------------------------------------------------
    # Tolerance
    # --------------------------------------------------

    result = parse_tolerance(text)

    if result:
        return result

    # --------------------------------------------------
    # Range
    # --------------------------------------------------

    result = parse_range(text)

    if result:
        return result

    result = parse_scalar(text)
    
    if result:
        return result

    
    # Mixed numeric value with description
    result = parse_mixed(text)

    if result:
        return result


    # --------------------------------------------------
    # Categorical
    # --------------------------------------------------

    result = parse_categorical(text)

    if result:
        return result

    # --------------------------------------------------
    # Unknown
    # --------------------------------------------------

    return {
    "type": "unknown",
    "raw": text
}