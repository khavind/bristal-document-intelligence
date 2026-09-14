# from value_parser import parse_value
# from unit_converter import convert
from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert

def evaluate_requirement(requirement, product_value_text):
    """
    Compare a parsed requirement with a product specification value.

    Returns:
        PASS
        FAIL
        UNKNOWN
    """

    # Requirement must contain enough information to evaluate
    if requirement["value"] is None or requirement["operator"] is None:
        return "UNKNOWN"

    product_value = parse_value(product_value_text)

    # Cannot evaluate unavailable or unknown values
    if product_value["type"] in ["unknown", "not_available"]:
        return "UNKNOWN"

    required_unit = requirement["unit"]
    product_unit = product_value.get("unit")

    # ---------------------------------------------------------
    # UNIT NORMALIZATION
    # ---------------------------------------------------------

    if required_unit and product_unit:

        try:
            product_number = product_value.get("value")

            if product_value["type"] == "scalar":
                product_number = convert(
                    product_number,
                    product_unit,
                    required_unit
                )

                product_value["value"] = product_number

            elif product_value["type"] == "range":

                product_value["min"] = convert(
                    product_value["min"],
                    product_unit,
                    required_unit
                )

                product_value["max"] = convert(
                    product_value["max"],
                    product_unit,
                    required_unit
                )

        except ValueError:
            # Units are incompatible or unsupported
            return "UNKNOWN"

    elif required_unit and not product_unit:
        # Requirement specifies a unit but product does not
        return "UNKNOWN"

    # ---------------------------------------------------------
    # SCALAR
    # ---------------------------------------------------------

    if product_value["type"] == "scalar":

        product_number = product_value["value"]
        required_number = requirement["value"]
        operator = requirement["operator"]

        if operator == ">=":
            return "PASS" if product_number >= required_number else "FAIL"

        elif operator == "<=":
            return "PASS" if product_number <= required_number else "FAIL"

        elif operator == ">":
            return "PASS" if product_number > required_number else "FAIL"

        elif operator == "<":
            return "PASS" if product_number < required_number else "FAIL"

        elif operator == "=":
            return "PASS" if product_number == required_number else "FAIL"

    # ---------------------------------------------------------
    # BOOLEAN
    # ---------------------------------------------------------

    if product_value["type"] == "boolean":

        if requirement["operator"] != "=":
            return "UNKNOWN"

        required_value = requirement["value"]

        if required_value == 1:
            return "PASS" if product_value["value"] is True else "FAIL"

        elif required_value == 0:
            return "PASS" if product_value["value"] is False else "FAIL"

        return "UNKNOWN"

    # ---------------------------------------------------------
    # RANGE
    # ---------------------------------------------------------

    if product_value["type"] == "range":

        minimum = product_value["min"]
        maximum = product_value["max"]

        required_number = requirement["value"]
        operator = requirement["operator"]

        if operator == ">=":
            return "PASS" if maximum >= required_number else "FAIL"

        elif operator == "<=":
            return "PASS" if minimum <= required_number else "FAIL"

        elif operator == ">":
            return "PASS" if maximum > required_number else "FAIL"

        elif operator == "<":
            return "PASS" if minimum < required_number else "FAIL"

    return "UNKNOWN"