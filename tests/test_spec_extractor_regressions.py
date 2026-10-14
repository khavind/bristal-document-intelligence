from src.ingestion.chunker import chunk_page
from src.retrieval.spec_extractor import (
    create_source,
    extract_specifications_from_chunks,
    is_valid_attribute_value_pair,
)
from src.retrieval.value_parser import parse_value


def test_rejects_section_number_value():
    assert not is_valid_attribute_value_pair("Safety", "2.1", parse_value("2.1"))
    assert not is_valid_attribute_value_pair("Contents", "8", parse_value("8"))


def test_rejects_document_metadata_labels():
    assert not is_valid_attribute_value_pair("Product designation", "Part number", parse_value("Part number"))
    assert not is_valid_attribute_value_pair("Document number", "13", parse_value("13"))


def test_rejects_table_headers_and_reference_values():
    assert not is_valid_attribute_value_pair("Band (MHz)", "Service", parse_value("Service"))
    assert not is_valid_attribute_value_pair("Distance", "(m)", parse_value("(m)"))
    assert not is_valid_attribute_value_pair("Product certification", "13", parse_value("13"))


def test_accepts_measurement_ranges():
    assert is_valid_attribute_value_pair("Air humidity", "20 % to 80 %", parse_value("20 % to 80 %"))
    assert is_valid_attribute_value_pair("Atmospheric pressure", "540 mbar to 1060 mbar", parse_value("540 mbar to 1060 mbar"))
    assert is_valid_attribute_value_pair("Temperature", "-20 °C to +60 °C", parse_value("-20 °C to +60 °C"))


def test_accepts_categorical_technical_value():
    assert is_valid_attribute_value_pair("Foot control", "Footswitch PST 500", parse_value("Footswitch PST 500"))


def test_rejects_prose_like_values():
    assert not is_valid_attribute_value_pair("Safety instructions", "This table is intended for use with the following accessories.", parse_value("This table is intended for use with the following accessories."))


def test_rejects_reference_like_attributes():
    assert not is_valid_attribute_value_pair("1.1", "Basic information", parse_value("Basic information"))


def test_accepts_genuine_numeric_specification():
    assert is_valid_attribute_value_pair("Height", "510 mm to 1,060 mm", parse_value("510 mm to 1,060 mm"))


def test_accepts_genuine_scalar_specification():
    assert is_valid_attribute_value_pair("Weight", "170 kg", parse_value("170 kg"))


def test_accepts_genuine_categorical_specification():
    assert is_valid_attribute_value_pair("Battery type", "rechargeable", parse_value("rechargeable"))


def test_rejects_diagram_key_mapping():
    assert not is_valid_attribute_value_pair("[i5]", "Lift", parse_value("Lift"))
    assert not is_valid_attribute_value_pair("[i6]", "Lower", parse_value("Lower"))


def test_rejects_ui_mapping():
    assert not is_valid_attribute_value_pair("Cancel", "OK", parse_value("OK"))
    assert not is_valid_attribute_value_pair("Ready", "Illuminated", parse_value("Illuminated"))


def test_rejects_table_header_mapping():
    assert not is_valid_attribute_value_pair("Weight", "Restriction", parse_value("Restriction"))


def test_rejects_ambiguous_table_cell():
    assert not is_valid_attribute_value_pair("Normal", "454 kg", parse_value("454 kg"))


def test_rejects_prose_fragment():
    assert not is_valid_attribute_value_pair("Mains power supply is", "connected to the mobile", parse_value("connected to the mobile"))


def test_rejects_bullet_prefixed_feature_lines_as_attribute_value_pairs():
    assert not is_valid_attribute_value_pair(
        "• Wired connection for bed exit alarm",
        "• Wireless connectivity",
        parse_value("• Wireless connectivity"),
    )


def test_provenance_remains_correct():
    chunk = {
        "document": "doc-1",
        "page": 9,
        "section": "Dimensions",
        "chunk_id": "chunk_42",
        "text": "Height\n510 mm to 1,060 mm",
    }
    source = create_source(chunk)
    assert source == {
        "document": "doc-1",
        "page": 9,
        "section": "Dimensions",
        "chunk_id": "chunk_42",
        "evidence": "Height\n510 mm to 1,060 mm",
    }


def test_corrupted_bullet_feature_lines_are_not_paired_as_specifications():
    chunk = {
        "document": "fixture",
        "page": 3,
        "section": "Features",
        "chunk_id": "chunk_3",
        "text": (
            "Safe working load\n250 kg\n"
            "� \t Battery backup\n"
            "� \t Bilateral mechanical CPR lever\n"
            "� \t Low height indicator\n"
            "� \t Electric CPR\n"
        ),
    }

    specifications = extract_specifications_from_chunks([chunk])

    assert [(item["attribute"], item["raw_value"]) for item in specifications] == [
        ("Safe working load", "250 kg")
    ]
    assert specifications[0]["source"]["evidence"] == "Safe working load\n250 kg"


def test_replacement_glyph_degrees_preserve_ranges_and_prevent_reversed_pairs():
    chunk = {
        "document": "fixture",
        "page": 3,
        "section": "Bed angles",
        "chunk_id": "chunk_3",
        "text": (
            "Foot section\n"
            "-3� to -22�\n"
            "Trendelenburg/reverse Trendelenburg\n"
            "+17� to -17�"
        ),
    }

    specifications = extract_specifications_from_chunks([chunk])

    assert [(item["attribute"], item["raw_value"]) for item in specifications] == [
        ("Foot section", "-3° to -22°"),
        ("Trendelenburg/reverse Trendelenburg", "+17° to -17°"),
    ]


def test_chunker_starts_new_chunks_at_heading_boundaries():
    chunks, _ = chunk_page(
        3,
        (
            "TECHNICAL SPECIFICATIONS\n"
            "Safe working load\n250 kg\n"
            "ADDITIONAL STANDARD FEATURES\n"
            "Central brake at foot end\n"
        ),
        "fixture",
        1,
    )

    assert [(chunk["section"], chunk["text"]) for chunk in chunks] == [
        ("TECHNICAL SPECIFICATIONS", "TECHNICAL SPECIFICATIONS\nSafe working load\n250 kg"),
        ("ADDITIONAL STANDARD FEATURES", "ADDITIONAL STANDARD FEATURES\nCentral brake at foot end"),
    ]


def test_chunker_preserves_numbered_technical_title_and_sentence_case_section():
    chunks, _ = chunk_page(
        3,
        (
            "MODEL 900 TECHNICAL SPECIFICATIONS\n"
            "Safe working load\n250 kg\n"
            "Bed angles\n"
            "Head section\n0 to 65°"
        ),
        "fixture",
        1,
    )

    assert [chunk["section"] for chunk in chunks] == [
        "MODEL 900 TECHNICAL SPECIFICATIONS",
        "Bed angles",
    ]
