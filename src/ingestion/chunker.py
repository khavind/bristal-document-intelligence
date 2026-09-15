import json
from pathlib import Path


# --------------------------------------------------
# Directories
# --------------------------------------------------

PROCESSED_DIR = Path("data/processed")


# --------------------------------------------------
# Find normalized documents
# --------------------------------------------------

input_files = list(PROCESSED_DIR.glob("*_normalized.json"))

if not input_files:
    print("No normalized JSON files found.")
    exit()


# --------------------------------------------------
# Process each normalized document
# --------------------------------------------------

for input_path in input_files:

    print(f"\nChunking: {input_path.name}")

    # Load normalized document
    with open(input_path, "r", encoding="utf-8") as file:
        pages = json.load(file)

    chunks = []

    chunk_id = 1

    current_product = None
    current_section = None
    current_page = None
    current_text = []


    # --------------------------------------------------
    # Save current chunk
    # --------------------------------------------------

    def save_chunk():

        nonlocal_values = None

        if not current_text:
            return

        cleaned_lines = [
            line.strip()
            for line in current_text
            if line.strip()
        ]

        if not cleaned_lines:
            return

        chunks.append({
            "chunk_id": f"chunk_{chunk_id}",
            "document": input_path.stem.replace("_normalized", ""),
            "page": current_page,
            "product": current_product,
            "section": current_section,
            "text": "\n".join(cleaned_lines)
        })


    # --------------------------------------------------
    # Process every page
    # --------------------------------------------------

    for page in pages:

        current_page = page["page"]

        lines = page["text"].splitlines()

        for line in lines:

            line = line.strip()

            if not line:
                continue


            # --------------------------------------------------
            # Product identification
            # --------------------------------------------------

            if "HILLROM 900 ACCELLA BED" in line.upper():

                if current_text:
                    save_chunk()
                    chunk_id += 1
                    current_text = []

                current_product = "Hillrom 900 Accella Bed"
                current_section = "Product Overview"

                current_text.append(line)

                continue


            # --------------------------------------------------
            # Major section headings
            # --------------------------------------------------

            if line in [
                "TECHNICAL SPECIFICATIONS",
                "Technical Specifications",
                "ADDITIONAL STANDARD FEATURES FOR ALL CONFIGURATIONS"
            ]:

                if current_text:
                    save_chunk()
                    chunk_id += 1
                    current_text = []

                current_section = line

                current_text.append(line)

                continue


            # --------------------------------------------------
            # Nested specification section
            # --------------------------------------------------

            if line in [
                "Bed angles",
                "Sleep deck",
                "Controls"
            ]:

                if current_text:
                    save_chunk()
                    chunk_id += 1
                    current_text = []

                current_section = line

                current_text.append(line)

                continue


            # --------------------------------------------------
            # Normal content
            # --------------------------------------------------

            current_text.append(line)


    # --------------------------------------------------
    # Save final chunk
    # --------------------------------------------------

    if current_text:
        save_chunk()


    # --------------------------------------------------
    # Output path
    # --------------------------------------------------

    output_path = (
        PROCESSED_DIR /
        f"{input_path.stem.replace('_normalized', '')}_chunks.json"
    )


    # --------------------------------------------------
    # Save chunks
    # --------------------------------------------------

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


print("\nChunking completed.")