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

        # Existing plain text extraction
        text = page.get_text()

        # Layout-aware block extraction
        blocks = page.get_text("blocks")

        page_blocks = []

        for block in blocks:
            x0, y0, x1, y1, block_text = block[:5]

            page_blocks.append({
                "bbox": [x0, y0, x1, y1],
                "text": block_text.strip(),
                "block": block[5] if len(block) > 5 else None,
            })

        words = []
        for word in page.get_text("words"):
            x0, y0, x1, y1, word_text = word[:5]
            words.append({
                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                "text": word_text,
                "block": word[5] if len(word) > 5 else None,
                "line": word[6] if len(word) > 6 else None,
                "word": word[7] if len(word) > 7 else None
            })

        pages.append({
            "page": page_number,
            "text": text,
            "blocks": page_blocks,
            "words": words
        })

    document.close()

    # Create JSON filename from PDF filename
    output_filename = pdf_path.stem + ".json"
    output_path = PROCESSED_DIR / output_filename

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(pages, file, indent=4, ensure_ascii=False)

    print(f"Saved: {output_path}")

print("\nPDF extraction completed.")