import json
import re
from pathlib import Path


PROCESSED_DIR = Path("data/processed")

# Target size for a normal chunk.
# This is not a hard limit; we split at natural line boundaries.
TARGET_CHUNK_CHARS = 1500

# Absolute maximum size before we force a split.
MAX_CHUNK_CHARS = 2200


def looks_like_heading(line):
    """
    Conservatively identify lines that may represent headings.

    We do NOT treat every short/title-case line as a heading.
    """

    line = line.strip()

    if not line:
        return False

    # Very short lines are usually labels, values, addresses, etc.
    if len(line) < 8:
        return False

    # Avoid treating long sentences as headings.
    if len(line) > 100:
        return False

    # Avoid obvious address/contact lines.
    if re.search(r"\d{3,}", line):
        return False

    # Strong signal: uppercase heading.
    letters = [c for c in line if c.isalpha()]

    if letters:
        uppercase_ratio = sum(c.isupper() for c in letters) / len(letters)

        if uppercase_ratio > 0.75 and len(line.split()) <= 12:
            return True

    # Another useful signal: title-style heading.
    words = line.split()

    if 1 <= len(words) <= 8:
        capitalized_words = sum(
            1 for word in words
            if word[:1].isupper()
        )

        if capitalized_words / len(words) >= 0.75:
            return True

    return False


def save_chunk(chunks, chunk_id, document, page, section, lines):
    """
    Save one chunk if it contains meaningful text.
    """

    cleaned_lines = [
        line.strip()
        for line in lines
        if line.strip()
    ]

    if not cleaned_lines:
        return chunk_id

    chunks.append({
        "chunk_id": f"chunk_{chunk_id}",
        "document": document,
        "page": page,
        "product": None,
        "section": section,
        "text": "\n".join(cleaned_lines)
    })

    return chunk_id + 1


def chunk_page(page_number, page_text, document, chunk_id):
    """
    Chunk one PDF page.

    Important:
    - Chunks never cross page boundaries.
    - We accumulate lines instead of creating a chunk for every heading.
    - Large pages are split by character size.
    """

    chunks = []

    lines = [
        line.strip()
        for line in page_text.splitlines()
        if line.strip()
    ]

    if not lines:
        return chunks, chunk_id

    current_lines = []
    current_section = None

    for line in lines:

        # If this looks like a heading, remember it as metadata.
        # We do NOT immediately create a new chunk.
        if looks_like_heading(line):
            current_section = line

        current_lines.append(line)

        current_text = "\n".join(current_lines)

        # Normal split point.
        if len(current_text) >= TARGET_CHUNK_CHARS:

            chunk_id = save_chunk(
                chunks,
                chunk_id,
                document,
                page_number,
                current_section,
                current_lines
            )

            current_lines = []

        # Safety split.
        elif len(current_text) >= MAX_CHUNK_CHARS:

            chunk_id = save_chunk(
                chunks,
                chunk_id,
                document,
                page_number,
                current_section,
                current_lines
            )

            current_lines = []

    # Save remaining text from the page.
    if current_lines:

        chunk_id = save_chunk(
            chunks,
            chunk_id,
            document,
            page_number,
            current_section,
            current_lines
        )

    return chunks, chunk_id


def chunk_document(pages, document_name):
    """
    Convert normalized PDF pages into manageable chunks.

    Generic design:
    - Works page by page.
    - Does not depend on specific PDF names.
    - Does not hard-code document-specific headings.
    - Preserves page provenance.
    """

    chunks = []
    chunk_id = 1

    for page in pages:

        page_number = page["page"]
        page_text = page.get("text", "")

        page_chunks, chunk_id = chunk_page(
            page_number,
            page_text,
            document_name,
            chunk_id
        )

        chunks.extend(page_chunks)

    return {
        "chunks": chunks
    }


def process_all_documents():
    """
    Process every normalized JSON document in data/processed/.
    """

    input_files = list(
        PROCESSED_DIR.glob("*_normalized.json")
    )

    if not input_files:
        print("No normalized JSON files found.")
        return

    for input_path in input_files:

        print(f"\nChunking: {input_path.name}")

        with open(
            input_path,
            "r",
            encoding="utf-8"
        ) as file:

            pages = json.load(file)

        document_name = input_path.stem.replace(
            "_normalized",
            ""
        )

        result = chunk_document(
            pages,
            document_name
        )

        output_path = (
            PROCESSED_DIR /
            f"{document_name}_chunks.json"
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=4,
                ensure_ascii=False
            )

        print(
            f"Created {len(result['chunks'])} chunks."
        )

        print(
            f"Chunks saved to: {output_path}"
        )

    print("\nChunking completed.")


if __name__ == "__main__":
    process_all_documents()