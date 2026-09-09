import re


def parse_value(text):
    """
    Convert a specification value from text
    into a structured representation.
    """

    text = text.strip()

    # --------------------------------
    # 1. Boolean / categorical values
    # --------------------------------

    if text.lower() in ["supported", "yes", "available"]:
        return {
            "type": "boolean",
            "value": True
        }

    if text.lower() in ["not supported", "no", "unavailable"]:
        return {
            "type": "boolean",
            "value": False
        }

    # --------------------------------
    # 2. Numeric ranges
    # --------------------------------

    range_pattern = (
        r"(-?\d+(?:\.\d+)?)\s*"
        r"(?:–|-|to)\s*"
        r"(-?\d+(?:\.\d+)?)\s*"
        r"([a-zA-Z%°/]+)?"
    )

    range_match = re.search(range_pattern, text)

    if range_match:
        minimum = float(range_match.group(1))
        maximum = float(range_match.group(2))
        unit = range_match.group(3)

        if unit:
            unit = normalize_unit(unit)

        return {
            "type": "range",
            "min": minimum,
            "max": maximum,
            "unit": unit
        }

    # --------------------------------
    # 3. Single numeric value
    # --------------------------------

    scalar_pattern = (
        r"(-?\d+(?:\.\d+)?)\s*"
        r"(?:-|\s*)?"
        r"([a-zA-Z%°/]+)?"
    )

    scalar_match = re.search(scalar_pattern, text)

    if scalar_match:
        value = float(scalar_match.group(1))
        unit = scalar_match.group(2)

        if unit:
            unit = normalize_unit(unit)

        return {
            "type": "scalar",
            "value": value,
            "unit": unit
        }

    # --------------------------------
    # 4. Unknown value
    # --------------------------------

    return {
        "type": "unknown",
        "raw": text
    }


def normalize_unit(unit):
    """
    Convert different representations
    of the same unit into one standard form.
    """

    unit = unit.lower()

    if unit in ["hour", "hours", "hr", "hrs"]:
        return "hours"

    if unit in ["kg", "kgs"]:
        return "kg"

    if unit in ["inch", "inches"]:
        return "inch"

    if unit in ["bpm"]:
        return "bpm"

    if unit in ["%", "percent"]:
        return "%"

    if unit in ["samples/sec", "sample/sec"]:
        return "samples/sec"

    if unit in ["°c", "c"]:
        return "°C"

    return unit


if __name__ == "__main__":

    test_values = [
        "5 hours",
        "4.5 kg",
        "70–100%",
        "12.1-inch",
        "Supported",
        "10–40°C"
    ]

    print("\n--- Value Parser Test ---\n")

    for value in test_values:

        result = parse_value(value)

        print(f"Original: {value}")
        print(f"Parsed  : {result}")
        print("-" * 50)