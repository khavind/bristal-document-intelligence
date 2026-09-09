import fitz
import json
from pathlib import Path

from text_normalizer import normalize_text


pdf_path = "data/raw/sample_product.pdf"
output_path = "data/processed/sample_product.json"


document = fitz.open(pdf_path)

pages = []


for page_number, page in enumerate(document, start=1):

    # Extract raw text
    raw_text = page.get_text()

    # Normalize extracted text
    cleaned_text = normalize_text(raw_text)

    pages.append({
        "page": page_number,
        "text": cleaned_text
    })


document.close()


output_data = {
    "document": "sample_product.pdf",
    "pages": pages
}


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


print(f"Extracted and normalized text saved to: {output_path}")