import pymupdf
from pathlib import Path
import json


# Input and output folders
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

# Create output folder if it doesn't exist
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# Find all PDF files in data/raw
pdf_files = list(RAW_DIR.glob("*.pdf"))

if not pdf_files:
    print("No PDF files found in data/raw/")
    exit()


for pdf_path in pdf_files:

    print(f"\nProcessing: {pdf_path.name}")

    document = pymupdf.open(pdf_path)

    pages = []

    for page_number, page in enumerate(document, start=1):

        text = page.get_text()

        pages.append({
            "page": page_number,
            "text": text
        })

    document.close()

    # Create JSON filename from PDF filename
    output_filename = pdf_path.stem + ".json"
    output_path = PROCESSED_DIR / output_filename

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(pages, file, indent=4, ensure_ascii=False)

    print(f"Saved: {output_path}")

print("\nPDF extraction completed.")