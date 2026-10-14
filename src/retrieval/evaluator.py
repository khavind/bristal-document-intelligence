# from value_parser import parse_value
# from unit_converter import convert
from src.retrieval.requirement_parser import attributes_equivalent
from src.retrieval.value_parser import parse_value
from src.retrieval.unit_converter import convert

def evaluate_requirement(requirement, product_value_text, candidate_attribute=None, candidate=None):
    """
    Compare a parsed requirement with a product specification value.

    A reported range is treated as the full set of permitted values. PASS
    requires every value in the range to satisfy the requirement; FAIL means
    no value satisfies it; an overlapping range returns UNKNOWN.

    Returns:
        PASS
        FAIL
        UNKNOWN
    """

    if candidate is not None and isinstance(candidate, dict):
        candidate_attribute = candidate.get("attribute", candidate_attribute)
        product_value_text = candidate.get("raw_value", product_value_text)

    # Requirement must contain enough information to evaluate
    if requirement["value"] is None or requirement["operator"] is None:
        return "UNKNOWN"

    required_attribute = requirement.get("attribute")
    if required_attribute and (
        candidate_attribute is not None or candidate is not None
    ) and not attributes_equivalent(required_attribute, candidate_attribute):
        return "UNKNOWN"

    product_value = None
    if isinstance(candidate, dict):
        product_value = candidate.get("parsed_value")
    if not isinstance(product_value, dict):
        product_value = parse_value(product_value_text)

    if product_value.get("type") == "mixed" and isinstance(product_value.get("parsed_value"), dict):
        product_value = product_value["parsed_value"]

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
    elif product_unit and not required_unit:
        # A bare requirement value cannot be assumed to use the product's unit.
        return "UNKNOWN"

    if (
        product_value["type"] in {"scalar", "range"}
        and not required_unit
        and not product_unit
    ):
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
            if minimum >= required_number:
                return "PASS"
            return "FAIL" if maximum < required_number else "UNKNOWN"

        elif operator == "<=":
            if maximum <= required_number:
                return "PASS"
            return "FAIL" if minimum > required_number else "UNKNOWN"

        elif operator == ">":
            if minimum > required_number:
                return "PASS"
            return "FAIL" if maximum <= required_number else "UNKNOWN"

        elif operator == "<":
            if maximum < required_number:
                return "PASS"
            return "FAIL" if minimum >= required_number else "UNKNOWN"

        elif operator == "=":
            if minimum == maximum == required_number:
                return "PASS"
            if required_number < minimum or required_number > maximum:
                return "FAIL"
            return "UNKNOWN"

    return "UNKNOWN"