from value_parser import parse_value


def evaluate_requirement(requirement, product_value_text):
    """
    Compare a parsed requirement with a product specification value.

    Returns:
        PASS
        FAIL
        UNKNOWN
    """

    # ---------------------------------------------------------
    # 1. Validate requirement
    # ---------------------------------------------------------

    if requirement["value"] is None or requirement["operator"] is None:
        return "UNKNOWN"

    # ---------------------------------------------------------
    # 2. Parse product value
    # ---------------------------------------------------------

    product_value = parse_value(product_value_text)

    if product_value["type"] == "unknown":
        return "UNKNOWN"

    # ---------------------------------------------------------
    # 3. Check units
    # ---------------------------------------------------------

    required_unit = requirement["unit"]
    product_unit = product_value.get("unit")

    if required_unit and product_unit:

        if required_unit != product_unit:
            return "UNKNOWN"

    # ---------------------------------------------------------
    # 4. Scalar value
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
    # 5. Boolean / capability value
    # ---------------------------------------------------------

    if product_value["type"] == "boolean":

        if requirement["operator"] != "=":
            return "UNKNOWN"

        required_value = requirement["value"]

        # Required capability
        if required_value == 1:
            return "PASS" if product_value["value"] is True else "FAIL"

        # Explicitly not required / must not be supported
        elif required_value == 0:
            return "PASS" if product_value["value"] is False else "FAIL"

        return "UNKNOWN"

    # ---------------------------------------------------------
    # 6. Range value
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

    # ---------------------------------------------------------
    # 7. Anything we don't understand
    # ---------------------------------------------------------

    return "UNKNOWN"


if __name__ == "__main__":

    test_requirement = {
        "attribute": "ECG Channels",
        "operator": ">=",
        "value": 5.0,
        "unit": None,
    }

    test_values = [
        "5",
        "12",
        "3"
    ]

    for product_value in test_values:

        result = evaluate_requirement(
            test_requirement,
            product_value
        )

        print("Requirement : >= 5 ECG Channels")
        print(f"Product     : {product_value}")
        print(f"Result      : {result}")
        print("-" * 50)