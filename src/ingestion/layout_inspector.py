import json
from pathlib import Path

import pymupdf


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def extract_page_data(page, page_number):
    """
    Extract text, blocks and word-level positional information
    from a single PDF page.

    The existing `text` and `blocks` fields are preserved for
    backward compatibility.
    """

    # ---------------------------------------------------------
    # 1. Normal page text
    # ---------------------------------------------------------
    text = page.get_text()


    # ---------------------------------------------------------
    # 2. Block-level extraction
    # ---------------------------------------------------------
    blocks = page.get_text("blocks")

    page_blocks = []

    for block in blocks:
        # PyMuPDF block structure:
        # x0, y0, x1, y1, text, block_no, block_type, ...
        x0, y0, x1, y1, block_text = block[:5]

        page_blocks.append({
            "bbox": [
                round(x0, 2),
                round(y0, 2),
                round(x1, 2),
                round(y1, 2)
            ],
            "text": block_text.strip()
        })


    # ---------------------------------------------------------
    # 3. Word-level extraction
    # ---------------------------------------------------------
    #
    # Each word contains its own position on the page.
    #
    # This is important for reconstructing:
    #
    #     rows
    #     columns
    #     table cells
    #
    # without hard-coding a particular document.
    #
    # PyMuPDF word structure:
    #
    # x0, y0, x1, y1, word,
    # block_no, line_no, word_no
    #
    # ---------------------------------------------------------

    words = page.get_text("words")

    page_words = []

    for word in words:
        x0, y0, x1, y1, word_text = word[:5]

        block_number = word[5] if len(word) > 5 else None
        line_number = word[6] if len(word) > 6 else None
        word_number = word[7] if len(word) > 7 else None

        page_words.append({
            "bbox": [
                round(x0, 2),
                round(y0, 2),
                round(x1, 2),
                round(y1, 2)
            ],
            "text": word_text,
            "block": block_number,
            "line": line_number,
            "word": word_number
        })


    # ---------------------------------------------------------
    # 4. Page dimensions
    # ---------------------------------------------------------
    rect = page.rect

    page_size = {
        "width": round(rect.width, 2),
        "height": round(rect.height, 2)
    }


    # ---------------------------------------------------------
    # 5. Return complete page representation
    # ---------------------------------------------------------

    return {
        "page": page_number,
        "width": page_size["width"],
        "height": page_size["height"],
        "text": text,
        "blocks": page_blocks,
        "words": page_words
    }


def extract_pdf(pdf_path):
    """
    Extract all pages from a PDF.
    """

    print(f"\nProcessing: {pdf_path.name}")

    document = pymupdf.open(pdf_path)

    pages = []

    try:
        for page_number, page in enumerate(document, start=1):

            page_data = extract_page_data(
                page,
                page_number
            )

            pages.append(page_data)

    finally:
        document.close()

    return pages


def save_processed_document(pdf_path, pages):
    """
    Save extracted document data as JSON.
    """

    output_filename = pdf_path.stem + ".json"
    output_path = PROCESSED_DIR / output_filename

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            pages,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"Saved: {output_path}")

    return output_path


def process_all_documents():
    """
    Process every PDF inside data/raw/.
    """

    pdf_files = sorted(
        RAW_DIR.glob("*.pdf")
    )

    if not pdf_files:
        print(
            "No PDF files found in data/raw/"
        )
        return

    print(
        f"Found {len(pdf_files)} PDF file(s)."
    )

    for pdf_path in pdf_files:

        pages = extract_pdf(
            pdf_path
        )

        save_processed_document(
            pdf_path,
            pages
        )

        print(
            f"Pages extracted: {len(pages)}"
        )

    print(
        "\nPDF extraction completed."
    )


if __name__ == "__main__":
    process_all_documents()