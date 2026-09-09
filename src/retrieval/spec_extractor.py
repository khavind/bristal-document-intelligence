import json
from pathlib import Path


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

    # Split chunk text into individual lines
    lines = [
        line.strip()
        for line in chunk["text"].splitlines()
        if line.strip()
    ]

    # Remove table headings:
    #
    # Technical Specifications
    # Specification
    # Value
    #
    lines = lines[3:]

    specifications = []

    # Specifications and values appear in pairs:
    #
    # Flow Rate
    # 1–1000 ml/hr
    #
    # Flow Rate Accuracy
    # ±3%
    #
    for i in range(0, len(lines), 2):

        attribute = lines[i]
        value = lines[i + 1]

        specifications.append({
            "attribute": attribute,
            "value": value
        })

    # Store product-level information
    structured_products.append({
        "product": chunk["product"],
        "page": chunk["page"],
        "chunk_id": chunk["chunk_id"],
        "specifications": specifications
    })


# --------------------------------------------------
# Create final output
# --------------------------------------------------

output_data = {
    "products": structured_products
}


# Make sure processed folder exists
Path("data/processed").mkdir(
    parents=True,
    exist_ok=True
)


# Save structured specifications
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

    print(f"Product: {product['product']}")
    print(f"Page: {product['page']}")

    for specification in product["specifications"]:

        print(
            f"{specification['attribute']} "
            f"→ {specification['value']}"
        )

    print("-" * 60)


print(f"\nStructured specifications saved to:")
print(output_path)