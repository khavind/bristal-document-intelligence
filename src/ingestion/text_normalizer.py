import re
import json
from pathlib import Path


def normalize_text(text):
    """
    Clean common PDF extraction artifacts
    without changing the meaning of the document.
    """

    # Normalize spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n\s*\n+", "\n", text)

    # Fix common PDF extraction issue
    text = text.replace("SpOI", "SpO₂")

    # Remove spaces before common punctuation
    text = re.sub(r"\s+([,:;])", r"\1", text)

    # Normalize bullet characters
    text = text.replace("●", "•")
    text = text.replace("▪", "•")

    return text.strip()


PROCESSED_DIR = Path("data/processed")


def process_documents(processed_dir=PROCESSED_DIR):
    """Normalize extracted page JSON files in the configured processed directory."""
    json_files = []

    for file in processed_dir.glob("*.json"):
        if (
            file.name.endswith("_normalized.json")
            or file.name.endswith("_chunks.json")
            or file.name.endswith("_specifications.json")
        ):
            continue

        try:
            with open(file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (
                isinstance(data, list)
                and data
                and isinstance(data[0], dict)
                and "page" in data[0]
                and "text" in data[0]
            ):
                json_files.append(file)
        except (json.JSONDecodeError, OSError):
            continue

    if not json_files:
        print(f"No extracted PDF JSON files found in {processed_dir}/")
        return

    for json_path in json_files:
        print(f"\nNormalizing: {json_path.name}")
        with open(json_path, "r", encoding="utf-8") as handle:
            pages = json.load(handle)

        for page in pages:
            page["text"] = normalize_text(page["text"])

        output_path = processed_dir / f"{json_path.stem}_normalized.json"
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(
                pages,
                handle,
                indent=4,
                ensure_ascii=False,
            )
        print(f"Saved: {output_path}")

    print("\nText normalization completed.")


if __name__ == "__main__":
    process_documents()