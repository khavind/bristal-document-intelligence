import json

from requirement_parser import parse_requirement


# --------------------------------------------------
# File paths
# --------------------------------------------------

specifications_path = (
    "data/processed/sample_product_specifications.json"
)


# --------------------------------------------------
# Load structured product specifications
# --------------------------------------------------

with open(specifications_path, "r", encoding="utf-8") as file:
    data = json.load(file)

products = data["products"]

print(f"Total products: {len(products)}")


# --------------------------------------------------
# Compare a product value with a requirement
# --------------------------------------------------

def compare_values(product_value, operator, required_value):

    # Example:
    # "5 hours" → "5" → 5.0

    product_number = float(
        product_value.split()[0]
    )

    if operator == ">=":
        return product_number >= required_value

    elif operator == "<=":
        return product_number <= required_value

    elif operator == ">":
        return product_number > required_value

    elif operator == "<":
        return product_number < required_value

    elif operator == "=":
        return product_number == required_value

    return False


# --------------------------------------------------
# Get user requirement
# --------------------------------------------------

query = input("\nEnter your requirement: ")

requirement = parse_requirement(query)


# --------------------------------------------------
# Display parsed requirement
# --------------------------------------------------

print("\n--- Requirement ---")

print(f"Attribute : {requirement['attribute']}")
print(f"Operator  : {requirement['operator']}")
print(f"Value     : {requirement['value']}")
print(f"Unit      : {requirement['unit']}")


# --------------------------------------------------
# Product matching
# --------------------------------------------------

print("\n--- Product Matching Results ---\n")


for product in products:

    found_specification = False

    for specification in product["specifications"]:

        # Check whether this product has
        # the required specification
        if (
            specification["attribute"]
            == requirement["attribute"]
        ):

            found_specification = True

            product_value = specification["value"]

            try:

                result = compare_values(
                    product_value,
                    requirement["operator"],
                    requirement["value"]
                )

                if result:
                    status = "PASS"
                else:
                    status = "FAIL"

            except (ValueError, IndexError):

                status = "UNKNOWN"


            # --------------------------------------
            # Display result
            # --------------------------------------

            print(
                f"Product : {product['product']}"
            )

            print(
                f"Page    : {product['page']}"
            )

            print(
                f"Value   : {product_value}"
            )

            print(
                f"Result  : {status}"
            )

            print("-" * 50)


    # ------------------------------------------
    # Specification not found
    # ------------------------------------------

    if not found_specification:

        print(
            f"Product : {product['product']}"
        )

        print(
            "Page    : Not available"
        )

        print(
            "Value   : Not specified"
        )

        print(
            "Result  : UNKNOWN"
        )

        print("-" * 50)