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
        "kg": 1,
        "lb": 0.45359237,
        "lbs": 0.45359237
    },

    # Base unit: meters
    "length": {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1,
        "inch": 0.0254,
        "in": 0.0254
    },

    # Base unit: volts
    "electrical": {
        "mv": 0.001,
        "v": 1,
        "kv": 1000
    },

    # Base unit: hertz
    "frequency": {
        "hz": 1,
        "khz": 1000,
        "mhz": 1000000,
        "ghz": 1000000000
    },

    # These units are comparable only to the same measurement kind.
    "angle": {
        "°": 1
    },
    "heart_rate": {
        "bpm": 1
    },
    "sample_rate": {
        "samples/sec": 1
    },

    # Base unit: millilitres per hour
    "volume_flow_rate": {
        "ml/hr": 1,
        "l/hr": 1000
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
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",

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
    "in": "inch",

    # Electrical
    "v": "v",
    "volt": "v",
    "volts": "v",
    "mv": "mv",
    "millivolt": "mv",
    "millivolts": "mv",
    "kv": "kv",
    "kilovolt": "kv",
    "kilovolts": "kv",

    # Frequency
    "hz": "hz",
    "hertz": "hz",
    "khz": "khz",
    "kilohertz": "khz",
    "mhz": "mhz",
    "megahertz": "mhz",
    "ghz": "ghz",
    "gigahertz": "ghz",
    "sample/sec": "samples/sec",
    "sample/s": "samples/sec",
    "samples/s": "samples/sec",
    "ml/hr": "ml/hr",
    "ml/h": "ml/hr",
    "milliliter/hour": "ml/hr",
    "milliliters/hour": "ml/hr",
    "millilitre/hour": "ml/hr",
    "millilitres/hour": "ml/hr",
    "l/hr": "l/hr",
    "l/h": "l/hr",
    "liter/hour": "l/hr",
    "liters/hour": "l/hr",
    "litre/hour": "l/hr",
    "litres/hour": "l/hr",

    # Angle
    "°": "°",
    "deg": "°",
    "degree": "°",
    "degrees": "°"
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