import re


def normalize_text(text):
    """
    Clean common PDF extraction artifacts
    without changing the meaning of the document.
    """

    # Normalize different types of whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n\s*\n+", "\n", text)

    # Fix common PDF extraction issue:
    # SpOI -> SpO₂
    text = text.replace("SpOI", "SpO₂")

    # Remove spaces before common punctuation
    text = re.sub(r"\s+([,:;])", r"\1", text)

    # Normalize bullet characters
    text = text.replace("●", "•")
    text = text.replace("▪", "•")

    return text.strip()