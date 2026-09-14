"""
Unit conversion utilities for product specification evaluation.

Supported categories:
    - Time
    - Weight
    - Length
"""


UNIT_CONVERSIONS = {

    # Base unit: hours
    "time": {
        "seconds": 1 / 3600,
        "minutes": 1 / 60,
        "hours": 1
    },

    # Base unit: kilograms
    "weight": {
        "g": 0.001,
        "kg": 1
    },

    # Base unit: meters
    "length": {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1,
        "inch": 0.0254
    }
}


UNIT_ALIASES = {

    # Time
    "second": "seconds",
    "seconds": "seconds",
    "sec": "seconds",
    "secs": "seconds",

    "minute": "minutes",
    "minutes": "minutes",
    "min": "minutes",
    "mins": "minutes",

    "hour": "hours",
    "hours": "hours",
    "hr": "hours",
    "hrs": "hours",

    # Weight
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",

    # Length
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",

    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",

    "m": "m",
    "meter": "m",
    "meters": "m",

    "inch": "inch",
    "inches": "inch",
    "in": "inch"
}


UNIT_CATEGORIES = {}

for category, units in UNIT_CONVERSIONS.items():

    for unit in units:
        UNIT_CATEGORIES[unit] = category


def normalize_unit(unit):
    """
    Normalize different representations of a unit.

    Example:
        "KG"       -> "kg"
        "kilogram" -> "kg"
        "hrs"      -> "hours"
    """

    if unit is None:
        return None

    unit = unit.strip().lower()

    return UNIT_ALIASES.get(unit, unit)


def convert(value, from_unit, to_unit):
    """
    Convert a numerical value from one unit to another.

    Example:
        convert(4000, "g", "kg")
        -> 4.0
    """

    from_unit = normalize_unit(from_unit)
    to_unit = normalize_unit(to_unit)

    # Check whether source unit exists
    if from_unit not in UNIT_CATEGORIES:
        raise ValueError(f"Unsupported unit: {from_unit}")

    # Check whether target unit exists
    if to_unit not in UNIT_CATEGORIES:
        raise ValueError(f"Unsupported unit: {to_unit}")

    # Find categories
    from_category = UNIT_CATEGORIES[from_unit]
    to_category = UNIT_CATEGORIES[to_unit]

    # Prevent invalid conversions such as kg -> hours
    if from_category != to_category:
        raise ValueError(
            f"Cannot convert {from_unit} to {to_unit}"
        )

    # Convert source value to base unit
    base_value = (
        value
        * UNIT_CONVERSIONS[from_category][from_unit]
    )

    # Convert base unit to target unit
    converted_value = (
        base_value
        / UNIT_CONVERSIONS[to_category][to_unit]
    )

    return converted_value