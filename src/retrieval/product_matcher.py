import json

from requirement_parser import parse_requirement
from evaluator import evaluate_requirement

specifications_path = "data/processed/sample_product_specifications.json"


with open(specifications_path, "r", encoding="utf-8") as file:
    data = json.load(file)


products = data["products"]


print(f"Total products: {len(products)}")


# --------------------------------
# Get user requirement
# --------------------------------

query = input("\nEnter your requirement: ")


requirement = parse_requirement(query)


print("\n--- Parsed Requirement ---")
print(f"Attribute : {requirement['attribute']}")
print(f"Operator  : {requirement['operator']}")
print(f"Value     : {requirement['value']}")
print(f"Unit      : {requirement['unit']}")


# --------------------------------
# Match products
# --------------------------------

print("\n--- Product Matching Results ---\n")


for product in products:

    found_specification = False

    for specification in product["specifications"]:

        if specification["attribute"] == requirement["attribute"]:

            found_specification = True

            product_value = specification["value"]

            result = evaluate_requirement(requirement, product_value)

            print(f"Product : {product['product']}")
            print(f"Page    : {product['page']}")
            print(f"Value   : {product_value}")
            print(f"Result  : {result}")

            print("-" * 50)

    # --------------------------------
    # Specification not found
    # --------------------------------

    if not found_specification:

        print(f"Product : {product['product']}")
        print("Page    : Not available")
        print("Value   : Not specified")
        print("Result  : UNKNOWN")

        print("-" * 50)
