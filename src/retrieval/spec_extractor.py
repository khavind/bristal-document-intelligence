import json
from pathlib import Path

from value_parser import parse_value


PROCESSED_DIR = Path("data/processed")


# --------------------------------------------------
# Create source information
# --------------------------------------------------

def create_source(chunk):
    return {
        "document": chunk["document"],
        "page": chunk["page"],
        "chunk_id": chunk["chunk_id"]
    }


# --------------------------------------------------
# Add one specification
# --------------------------------------------------

def add_specification(
    specifications,
    attribute,
    raw_value,
    chunk,
    status=None,
    parent_attribute=None
):
    parsed_value = None

    if raw_value not in ["•", "º"]:
        parsed_value = parse_value(raw_value)

    specification = {
        "attribute": attribute,
        "raw_value": raw_value,
        "parsed_value": parsed_value,
        "status": status,
        "source": create_source(chunk)
    }

    if parent_attribute:
        specification["parent_attribute"] = parent_attribute

    specifications.append(specification)


# --------------------------------------------------
# Find production chunk files
# --------------------------------------------------

input_files = [
    path
    for path in PROCESSED_DIR.glob("*_chunks.json")
    if not path.name.startswith("sample_")
]


if not input_files:
    print("No production chunk files found.")
    exit()


# --------------------------------------------------
# Process each document
# --------------------------------------------------

for input_path in input_files:

    print(f"\nProcessing: {input_path.name}")

    with open(input_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    chunks = data["chunks"]

    print(f"Total chunks: {len(chunks)}")

    # --------------------------------------------------
    # Find product name
    # --------------------------------------------------

    product_name = None

    for chunk in chunks:

        if chunk.get("product"):
            product_name = chunk["product"]
            break

    if product_name is None:
        product_name = input_path.stem.replace("_chunks", "")

    specifications = []

    # ==================================================
    # Process chunks
    # ==================================================
    def reconstruct_wrapped_bullets(lines):
        """Combine wrapped continuation lines into a single bullet item."""
        reconstructed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.startswith(("• ", "º ")):
                marker = line[0]
                feature = line[2:].strip()
                i += 1

                while (
                    i < len(lines)
                    and not lines[i].startswith(("• ", "º "))
                    and lines[i] not in ["•", "º"]
                ):
                    feature = f"{feature} {lines[i]}".strip()
                    i += 1

                reconstructed_lines.append(f"{marker} {feature}")
            else:
                reconstructed_lines.append(line)
                i += 1

        return reconstructed_lines

    for chunk in chunks:

        section = chunk.get("section")
        text = chunk.get("text", "")

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        lines = reconstruct_wrapped_bullets(lines)

        # ==================================================
        # PRODUCT OVERVIEW
        # ==================================================

        if section == "Product Overview":

            i = 0

            while i < len(lines) - 1:

                attribute = lines[i]
                raw_value = lines[i + 1]

                if attribute.lower() == product_name.lower():
                    i += 1
                    continue

                if "TECHNICAL SPECIFICATIONS" in attribute.upper():
                    i += 1
                    continue

                if attribute in ["•", "º"]:
                    i += 1
                    continue

                parsed_value = parse_value(raw_value)

                if (
                    isinstance(parsed_value, dict)
                    and parsed_value.get("type") != "unknown"
                ):
                    add_specification(
                        specifications,
                        attribute,
                        raw_value,
                        chunk
                    )

                    i += 2

                else:
                    i += 1

        # ==================================================
        # BED ANGLES
        # ==================================================

        elif section == "Bed angles":

            parent_attribute = "Bed angles"
            i = 0

            while i < len(lines) - 1:

                attribute = lines[i]

                if attribute == parent_attribute:
                    i += 1
                    continue

                raw_value = lines[i + 1]

                parsed_value = parse_value(raw_value)

                if (
                    isinstance(parsed_value, dict)
                    and parsed_value.get("type") != "unknown"
                ):
                    add_specification(
                        specifications,
                        attribute,
                        raw_value,
                        chunk,
                        parent_attribute=parent_attribute
                    )

                    i += 2

                else:
                    i += 1

        # ==================================================
        # SLEEP DECK
        # ==================================================

        elif section == "Sleep deck":

            i = 0

            while i < len(lines) - 1:

                attribute = lines[i]

                if attribute == "Sleep deck":
                    i += 1
                    continue

                if attribute in ["•", "º"]:
                    i += 1
                    continue

                raw_value = lines[i + 1]

                parsed_value = parse_value(raw_value)

                if (
                    isinstance(parsed_value, dict)
                    and parsed_value.get("type") != "unknown"
                ):
                    add_specification(
                        specifications,
                        attribute,
                        raw_value,
                        chunk
                    )

                    i += 2

                else:
                    i += 1

        # ==================================================
        # CONTROLS
        # ==================================================

        elif section == "Controls":
            lines = reconstruct_wrapped_bullets(lines)
            i = 0

            while i < len(lines):

                line = lines[i]

                # ------------------------------------------
                # Ignore heading
                # ------------------------------------------

                if line == "Controls":
                    i += 1
                    continue

                # ------------------------------------------
                # CASE 1
                #
                # Embedded marker at beginning
                #
                # • Feature
                #
                # These are standard features.
                # ------------------------------------------

                if line.startswith("• "):

                    feature = line[2:].strip()

                    if feature:
                        add_specification(
                            specifications,
                            feature,
                            "•",
                            chunk,
                            status="standard"
                        )

                    i += 1
                    continue

                if line.startswith("º "):

                    feature = line[2:].strip()

                    if feature:
                        add_specification(
                            specifications,
                            feature,
                            "º",
                            chunk,
                            status="optional"
                        )

                    i += 1
                    continue

                # ------------------------------------------
                # CASE 2
                #
                # Feature
                # Marker
                #
                # Pendant
                # º
                #
                # ------------------------------------------

                if i + 1 < len(lines):

                    next_line = lines[i + 1]

                    if next_line in ["•", "º"]:

                        status = (
                            "standard"
                            if next_line == "•"
                            else "optional"
                        )

                        add_specification(
                            specifications,
                            line,
                            next_line,
                            chunk,
                            status=status
                        )

                        i += 2
                        continue

                # ------------------------------------------
                # CASE 3
                #
                # Attribute
                # Value
                # Marker
                #
                # Steering castor
                # At head end
                # •
                #
                # ------------------------------------------

                if i + 2 < len(lines):

                    value_line = lines[i + 1]
                    status_marker = lines[i + 2]

                    if status_marker in ["•", "º"]:

                        status = (
                            "standard"
                            if status_marker == "•"
                            else "optional"
                        )

                        add_specification(
                            specifications,
                            line,
                            value_line,
                            chunk,
                            status=status
                        )

                        i += 3
                        continue

                # ------------------------------------------
                # CASE 4
                #
                # Attribute
                # Value
                #
                # Graphical Caregiver Interface
                # Integrated in right siderail
                #
                # ------------------------------------------

                if i + 1 < len(lines):

                    value_line = lines[i + 1]

                    if value_line not in ["•", "º"]:

                        parsed_value = parse_value(value_line)

                        if (
                            isinstance(parsed_value, dict)
                            and parsed_value.get("type") != "unknown"
                        ):
                            add_specification(
                                specifications,
                                line,
                                value_line,
                                chunk
                            )

                            i += 2
                            continue

                # ------------------------------------------
                # Nothing matched
                # ------------------------------------------

                i += 1

        # ==================================================
        # Ignore all other sections
        # ==================================================

        else:
            continue

    # ==================================================
    # Create structured product
    # ==================================================

    structured_product = {
        "product_family": product_name,
        "model": None,
        "variant": None,
        "configuration": None,
        "specifications": specifications,
        "relationships": []
    }

    # ==================================================
    # Output
    # ==================================================

    output_data = {
        "products": [
            structured_product
        ]
    }

    output_path = (
        PROCESSED_DIR
        / f"{input_path.stem.replace('_chunks', '')}_specifications.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output_data,
            file,
            indent=4,
            ensure_ascii=False
        )

    # ==================================================
    # Display
    # ==================================================

    print("\n--- Structured Specifications ---\n")

    print(
        f"Product Family: {product_name}"
    )

    print(
        f"Total specifications: {len(specifications)}"
    )

    for specification in specifications:

        print(
            f"{specification['attribute']} "
            f"→ {specification['raw_value']} "
            f"→ {specification['parsed_value']} "
            f"[{specification['status']}]"
        )

    print("\n" + "-" * 60)

    print(
        "Structured specifications saved to:"
    )

    print(output_path)


print("\nSpecification extraction completed.")