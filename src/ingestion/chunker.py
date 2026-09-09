import json
from pathlib import Path


input_path = "data/processed/sample_product.json"
output_path = "data/processed/sample_product_chunks.json"


# Load extracted document
with open(input_path, "r", encoding="utf-8") as file:
    document_data = json.load(file)


chunks = []

chunk_id = 1

current_product = None
current_section = None
current_page = None
current_text = []


product_headers = [
    "Product 1:",
    "Product 2:",
    "Product 3:",
    "Product 4:"
]


section_headers = [
    "Technical Specifications",
    "Features"
]


global_sections = [
    "Compliance & Documentation",
    "Documentation Available",
    "Example Certifications",
    "Sample Tender Requirement",
    "Evaluation Goal"
]


def save_chunk():
    global chunk_id, current_text

    if not current_text:
        return

    # Remove empty lines
    cleaned_lines = [
        line.strip()
        for line in current_text
        if line.strip()
    ]

    if not cleaned_lines:
        current_text = []
        return

    chunks.append({
        "chunk_id": f"chunk_{chunk_id}",
        "document": document_data["document"],
        "page": current_page,
        "product": current_product,
        "section": current_section,
        "text": "\n".join(cleaned_lines)
    })

    chunk_id += 1
    current_text = []


# Process every page
for page in document_data["pages"]:

    current_page = page["page"]

    lines = page["text"].splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        # -----------------------------
        # Product heading
        # -----------------------------
        if any(line.startswith(header) for header in product_headers):

            save_chunk()

            current_product = line
            current_section = "Product Overview"

            current_text.append(line)

        # -----------------------------
        # Product-specific sections
        # -----------------------------
        elif line in section_headers:

            save_chunk()

            current_section = line

            current_text.append(line)

        # -----------------------------
        # Global document sections
        # -----------------------------
        elif line in global_sections:

            save_chunk()

            current_product = None
            current_section = line

            # Do not immediately create a heading-only chunk.
            # The actual content following the heading will be stored.

        # -----------------------------
        # Normal content
        # -----------------------------
        else:

            current_text.append(line)


# Save final chunk
save_chunk()


# Create output directory if required
Path("data/processed").mkdir(parents=True, exist_ok=True)


# Save chunks
output_data = {
    "chunks": chunks
}


with open(output_path, "w", encoding="utf-8") as file:
    json.dump(
        output_data,
        file,
        indent=4,
        ensure_ascii=False
    )


print(f"Created {len(chunks)} chunks.")
print(f"Chunks saved to: {output_path}")