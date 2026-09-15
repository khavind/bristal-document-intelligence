import json
from pathlib import Path

from value_parser import parse_value


# --------------------------------------------------
# File paths
# --------------------------------------------------

input_path = "data/processed/sample_product_chunks.json"
output_path = "data/processed/sample_product_specifications.json"


# --------------------------------------------------
# Load chunked document
# --------------------------------------------------

with open(input_path, "r", encoding="utf-8") as file:
    data = json.load(file)

chunks = data["chunks"]

print(f"Total chunks: {len(chunks)}")


# --------------------------------------------------
# Select technical specification chunks
# --------------------------------------------------

spec_chunks = [
    chunk
    for chunk in chunks
    if chunk["section"] == "Technical Specifications"
]

print(f"Technical specification chunks: {len(spec_chunks)}")


# --------------------------------------------------
# Extract structured specifications
# --------------------------------------------------

structured_products = []

for chunk in spec_chunks:

    lines = [
        line.strip()
        for line in chunk["text"].splitlines()
        if line.strip()
    ]

    # Current synthetic PDF contains:
    #
    # Technical Specifications
    # Specification
    # Value
    #
    # We still use this assumption for the current dataset.
    lines = lines[3:]

    specifications = []

    for i in range(0, len(lines) - 1, 2):

        attribute = lines[i]
        raw_value = lines[i + 1]

        parsed_value = parse_value(raw_value)

        # Detect standard / optional markers
        status = None

        if raw_value in ["•", "º"]:
            if raw_value == "•":
                status = "standard"
            elif raw_value == "º":
                status = "optional"

        specifications.append({
            "attribute": attribute,
            "raw_value": raw_value,
            "parsed_value": parsed_value,
            "status": status,
            "source": {
                "document": chunk["document"],
                "page": chunk["page"],
                "chunk_id": chunk["chunk_id"]
            }
        })

    # --------------------------------------------------
    # Product identity
    # --------------------------------------------------

    product_name = chunk["product"]

    structured_products.append({
        "product_family": product_name,
        "model": None,
        "variant": None,
        "configuration": None,
        "specifications": specifications,
        "relationships": []
    })


# --------------------------------------------------
# Create final output
# --------------------------------------------------

output_data = {
    "products": structured_products
}


# --------------------------------------------------
# Save structured specifications
# --------------------------------------------------

Path("data/processed").mkdir(
    parents=True,
    exist_ok=True
)

with open(output_path, "w", encoding="utf-8") as file:
    json.dump(
        output_data,
        file,
        indent=4,
        ensure_ascii=False
    )


# --------------------------------------------------
# Display results
# --------------------------------------------------

print("\n--- Structured Specifications ---\n")

for product in structured_products:

    print(f"Product Family: {product['product_family']}")
    print(f"Model: {product['model']}")

    for specification in product["specifications"]:

        print(
            f"{specification['attribute']} "
            f"→ {specification['raw_value']} "
            f"→ {specification['parsed_value']}"
        )

    print("-" * 60)


print("\nStructured specifications saved to:")
print(output_path)