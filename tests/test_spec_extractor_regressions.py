import json
import re
from pathlib import Path

import pymupdf
import pytest

from src.ingestion.chunker import chunk_page
from src.ingestion.layout_inspector import extract_page_data
from src.retrieval import product_matcher
from src.retrieval.requirement_parser import parse_requirement
from src.retrieval.spec_extractor import (
    create_source,
    extract_specifications_from_chunks,
    is_valid_attribute_value_pair,
)
from src.retrieval.unit_converter import convert
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


def test_title_case_measurement_label_keeps_parent_section_provenance():
    chunks, _ = chunk_page(
        3,
        (
            "TECHNICAL SPECIFICATIONS\n"
            "Safe Working Load\n250 kg\n"
            "ADDITIONAL STANDARD FEATURES\n"
            "Central brake at foot end\n"
        ),
        "fixture",
        1,
    )

    assert [(chunk["section"], chunk["page"]) for chunk in chunks] == [
        ("TECHNICAL SPECIFICATIONS", 3),
        ("ADDITIONAL STANDARD FEATURES", 3),
    ]
    assert chunks[0]["text"] == (
        "TECHNICAL SPECIFICATIONS\nSafe Working Load\n250 kg"
    )

    specifications = extract_specifications_from_chunks(chunks)
    working_load = [
        item
        for item in specifications
        if item["attribute"].lower() == "safe working load"
    ]

    assert len(working_load) == 1
    assert working_load[0]["raw_value"] == "250 kg"
    assert working_load[0]["source"]["page"] == 3
    assert working_load[0]["source"]["section"] == "TECHNICAL SPECIFICATIONS"
    assert working_load[0]["source"]["evidence"] == "Safe Working Load\n250 kg"


def test_rejects_quantity_parent_paired_with_nested_row_label():
    parsed_bed = parse_value("Bed")
    assert not is_valid_attribute_value_pair(
        "Maximum Lift Capacity",
        "Bed",
        parsed_bed,
    )

    chunk = {
        "document": "affinity",
        "page": 4,
        "section": "Specifications",
        "chunk_id": "chunk_4",
        "text": "Maximum Lift Capacity\nBed\nFoot section\n",
    }
    specifications = extract_specifications_from_chunks([chunk])

    assert ("Maximum Lift Capacity", "Bed") not in [
        (item["attribute"], item["raw_value"]) for item in specifications
    ]
    assert all(
        item["attribute"] != "Maximum Lift Capacity" for item in specifications
    )


def test_quantity_attributes_keep_numeric_and_categorical_states():
    assert is_valid_attribute_value_pair(
        "Safe Working Load",
        "250 kg",
        parse_value("250 kg"),
    )
    assert is_valid_attribute_value_pair(
        "Maximum Lift Capacity",
        "500 lb",
        parse_value("500 lb"),
    )
    assert is_valid_attribute_value_pair(
        "Battery type",
        "rechargeable",
        parse_value("rechargeable"),
    )
    assert is_valid_attribute_value_pair(
        "Height adjustment",
        "electric",
        parse_value("electric"),
    )


def _extract_pdf_page_chunks(filename, page_number):
    pdf_path = (
        Path(__file__).parents[1]
        / "data"
        / "raw"
        / filename
    )
    document = pymupdf.open(pdf_path)
    try:
        page = document[page_number - 1]
        page_data = extract_page_data(page, page_number)
    finally:
        document.close()

    chunks, _ = chunk_page(
        page_data["page"],
        page_data["text"],
        pdf_path.stem,
        1,
        page_data,
    )
    return chunks


def _extract_ts7500_capacity_pages():
    pdf_path = (
        Path(__file__).parents[1]
        / "data"
        / "raw"
        / "TS_7500_Surgical_Table.pdf"
    )
    document = pymupdf.open(pdf_path)
    chunks = []
    next_chunk_id = 1
    try:
        for page_number in (2, 6):
            page_data = extract_page_data(
                document[page_number - 1],
                page_number,
            )
            page_chunks, next_chunk_id = chunk_page(
                page_number,
                page_data["text"],
                pdf_path.stem,
                next_chunk_id,
                page_data,
            )
            chunks.extend(page_chunks)
    finally:
        document.close()
    return chunks, extract_specifications_from_chunks(chunks)


def test_ts7500_original_pdf_preserves_patient_load_and_four_capacity_columns():
    chunks, specifications = _extract_ts7500_capacity_pages()
    patient_loads = [
        item for item in specifications if item["attribute"] == "Patient Load"
    ]
    capacities = [
        item for item in specifications
        if item["attribute"] == "Max. weight capacity"
    ]

    assert len(patient_loads) == 1
    assert patient_loads[0]["raw_value"] == "880 lb / 400 kg"
    assert patient_loads[0]["parsed_value"] == {
        "type": "scalar",
        "value": 400.0,
        "unit": "kg",
    }
    assert patient_loads[0]["source"]["document"] == "TS_7500_Surgical_Table"
    assert patient_loads[0]["source"]["page"] == 2
    assert patient_loads[0]["source"]["section"] == "CUTTING-EDGE TECHNOLOGY"
    assert patient_loads[0]["source"]["evidence"] == (
        "patient loads of up to 880 lb / 400 kg"
    )

    assert len(capacities) == 4
    assert {
        item["scope"]["configuration"] for item in capacities
    } == {
        "OR table column SF",
        "OR table column SB",
        "OR table column SM, hybrid MC2",
        "OR table column hybrid SC, FC",
    }
    assert all(item["raw_value"] == "880 lbs (400 kg)" for item in capacities)
    assert all(
        item["parsed_value"] == {
            "type": "scalar",
            "value": 400.0,
            "unit": "kg",
        }
        for item in capacities
    )
    assert all(item["source"]["page"] == 6 for item in capacities)
    assert all(
        item["source"]["section"] == "Technical Data in Detail"
        for item in capacities
    )
    assert all(
        item["scope"]["conditions"]
        == "With restrictions, depending on position of patient."
        for item in capacities
    )
    assert all(
        item["scope"]["restriction"] == "position-dependent"
        for item in capacities
    )
    assert all(
        item["scope"]["configuration"] in item["source"]["evidence"]
        and "Max. weight capacity" in item["source"]["evidence"]
        and "880 lbs (400 kg)" in item["source"]["evidence"]
        and "With restrictions, depending on position of patient."
        in item["source"]["evidence"]
        for item in capacities
    )
    assert abs(convert(880, "lb", "kg") - 400) / 400 < 0.01
    assert len(chunks) > 0


def test_ts7500_original_pdf_records_flow_through_processed_loader_and_matcher(
    monkeypatch,
    tmp_path,
):
    chunks, specifications = _extract_ts7500_capacity_pages()
    document_name = "TS_7500_Surgical_Table"
    specification_file = tmp_path / f"{document_name}_specifications.json"
    chunk_file = tmp_path / f"{document_name}_chunks.json"
    specification_file.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "product": "TS 7500 OR System Table",
                        "specifications": specifications,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chunk_file.write_text(
        json.dumps({"chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)

    loaded_specs = product_matcher._load_processed_specifications()
    capacity_specs = [
        item for item in loaded_specs
        if item["attribute"] == "Max. weight capacity"
    ]
    assert len(capacity_specs) == 4
    assert all(item["source"]["page"] == 6 for item in capacity_specs)

    catalogue = [
        {
            "product": "TS 7500 OR System Table",
            "document": document_name,
            "product_kind": "surgical_equipment",
            "identity_reliable": True,
        }
    ]
    query_statuses = {
        "Maximum weight capacity for OR table column SF at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SB at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SM, hybrid MC2 at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for MC2 column at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column hybrid SC, FC at least 880 lb": "UNKNOWN",
        "Maximum weight capacity for FC column at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SF or OR table column SB "
        "at least 400 kg": "UNKNOWN",
        "Maximum weight capacity at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SF in Trendelenburg position "
        "at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SB in Trendelenburg position "
        "at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column SM, hybrid MC2 in Trendelenburg "
        "position at least 400 kg": "UNKNOWN",
        "Maximum weight capacity for OR table column hybrid SC, FC in Trendelenburg "
        "position at least 880 lb": "UNKNOWN",
        "Patient Load at least 400 kg": "PASS",
        "Patient Load for OR table column SF at least 400 kg": "UNKNOWN",
        "Safe Working Load at least 400 kg": "UNKNOWN",
        "Maximum Patient Weight at least 400 kg": "UNKNOWN",
        "Maximum Lift Capacity at least 400 kg": "UNKNOWN",
    }

    for query, expected_status in query_statuses.items():
        requirement = parse_requirement(query)
        if " SF or " in query:
            assert requirement["configuration_scope"]["configuration_ambiguous"] is True
        assert requirement["value"] == (880 if "880 lb" in query else 400)
        assert requirement["unit"] == ("lb" if "880 lb" in query else "kg")
        result = next(
            item
            for item in product_matcher._match_technical_requirement(
                query,
                catalogue_records=catalogue,
            )
            if item["product"] == "TS 7500 OR System Table"
        )
        assert result["status"] == expected_status, query
        if expected_status == "PASS":
            assert result["source"]["document"] == document_name
            assert result["source"]["page"] in {2, 6}
            assert result["source"]["evidence"]
        if "Maximum weight capacity" in query and "for OR table column" in query:
            assert result["source"]["page"] == 6
            assert result["source"]["scope"]["configuration"]
            assert "With restrictions, depending on position of patient." in (
                result["source"]["evidence"]
            )


def test_ts7500_position_specific_capacity_pass_requires_direct_source_support(
    monkeypatch,
    tmp_path,
):
    chunks, specifications = _extract_ts7500_capacity_pages()
    position_qualified = [
        {
            **item,
            "scope": dict(item.get("scope") or {}),
            "source": dict(item.get("source") or {}),
        }
        for item in specifications
    ]
    sf_capacity = next(
        item
        for item in position_qualified
        if item["attribute"] == "Max. weight capacity"
        and item["scope"]["configuration"] == "OR table column SF"
    )
    specific_qualification = (
        "Maximum weight capacity of 400 kg is permitted in Trendelenburg position."
    )
    sf_capacity["scope"]["conditions"] += f" {specific_qualification}"
    sf_capacity["source"]["scope"] = sf_capacity["scope"]
    sf_capacity["source"]["qualification_sources"] = [
        {
            "document": "TS_7500_Surgical_Table",
            "page": 6,
            "section": "Technical Data in Detail",
            "evidence": specific_qualification,
        }
    ]
    document_name = "TS_7500_Surgical_Table"
    (tmp_path / f"{document_name}_specifications.json").write_text(
        json.dumps(
            {
                "products": [
                    {
                        "product": "TS 7500 OR System Table",
                        "specifications": position_qualified,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{document_name}_chunks.json").write_text(
        json.dumps({"chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)
    catalogue = [
        {
            "product": "TS 7500 OR System Table",
            "document": document_name,
            "product_kind": "surgical_equipment",
            "identity_reliable": True,
        }
    ]

    result = next(
        item
        for item in product_matcher._match_technical_requirement(
            "Maximum weight capacity for OR table column SF in Trendelenburg "
            "position at least 400 kg",
            catalogue_records=catalogue,
        )
        if item["product"] == "TS 7500 OR System Table"
    )

    assert result["status"] == "PASS"
    assert result["source"]["page"] == 6
    assert result["scope"]["configuration"] == "OR table column SF"
    assert any(
        item["page"] == 6 and item["evidence"] == specific_qualification
        for item in result["source"]["qualification_sources"]
    )


@pytest.mark.parametrize(
    ("retained_attribute", "query", "expected_status"),
    [
        (
            "Patient Load",
            "Maximum weight capacity for OR table column SF at least 400 kg",
            "UNKNOWN",
        ),
        (
            "Max. weight capacity",
            "Patient Load at least 400 kg",
            "UNKNOWN",
        ),
    ],
)
def test_ts7500_page_two_and_page_six_load_concepts_are_not_interchangeable(
    monkeypatch,
    tmp_path,
    retained_attribute,
    query,
    expected_status,
):
    chunks, specifications = _extract_ts7500_capacity_pages()
    only_one_concept = [
        item for item in specifications if item["attribute"] == retained_attribute
    ]
    document_name = "TS_7500_Surgical_Table"
    (tmp_path / f"{document_name}_specifications.json").write_text(
        json.dumps(
            {
                "products": [
                    {
                        "product": "TS 7500 OR System Table",
                        "specifications": only_one_concept,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{document_name}_chunks.json").write_text(
        json.dumps({"chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)
    catalogue = [
        {
            "product": "TS 7500 OR System Table",
            "document": document_name,
            "product_kind": "surgical_equipment",
            "identity_reliable": True,
        }
    ]

    result = next(
        item
        for item in product_matcher._match_technical_requirement(
            query,
            catalogue_records=catalogue,
        )
        if item["product"] == "TS 7500 OR System Table"
    )

    assert result["status"] == expected_status


def _extract_affinity_page_three():
    return _extract_pdf_page_chunks(
        "207598-EN-r1_Affinity_SpecSheet-LR.pdf",
        3,
    )


def test_pst500_permissible_load_table_retains_configuration_and_provenance():
    chunks = _extract_pdf_page_chunks(
        "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
        45,
    )
    specifications = extract_specifications_from_chunks(chunks)
    loads = [
        item
        for item in specifications
        if item["attribute"] == "Permissible Load"
    ]

    assert len(loads) == 10
    assert {
        (
            item["scope"]["chapter"],
            item["scope"]["orientation"],
            item["raw_value"],
        )
        for item in loads
    } == {
        ("5.11.2 (1)", "Normal", "454 kg / 1000 lbs"),
        ("5.11.2 (2)", "Normal", "360 kg / 793 lbs"),
        ("5.11.3", "Normal", "300 kg / 661 lbs"),
        ("5.11.4", "Inverted", "270 kg / 595 lbs"),
        ("5.11.5", "Normal", "160 kg / 352 lbs"),
        ("5.11.5", "Inverted", "135 kg / 297 lbs"),
        ("5.11.6", "Inverted", "160 kg / 352 lbs"),
        ("5.11.7", "Normal", "160 kg / 352 lbs"),
        ("5.11.8", "Inverted", "225 kg / 496 lbs"),
        ("5.11.8", "Inverted", "160 kg / 352 lbs"),
    }
    by_chapter_and_orientation = {
        (
            item["scope"]["chapter"],
            item["scope"]["orientation"],
        ): item
        for item in loads
    }

    carbon_normal = by_chapter_and_orientation[("5.11.5", "Normal")]
    assert carbon_normal["raw_value"] == "160 kg / 352 lbs"
    assert "Carbon 1200" in carbon_normal["scope"]["configuration"]
    assert carbon_normal["scope"]["restriction"] == "Yes"
    assert carbon_normal["source"]["page"] == 45
    assert carbon_normal["source"]["section"] == (
        "5.11.5 Operating tabletop with Carbon 1200 tabletop section"
    )
    assert "160 kg / 352 lbs" in carbon_normal["source"]["evidence"]
    assert "Normal" in carbon_normal["source"]["evidence"]
    assert any(
        item["page"] == 48
        for item in carbon_normal["source"]["qualification_sources"]
    )
    assert "foot end of the patient" in carbon_normal["scope"]["conditions"]

    carbon_inverted = by_chapter_and_orientation[("5.11.5", "Inverted")]
    assert carbon_inverted["raw_value"] == "135 kg / 297 lbs"
    assert "Carbon 1200" in carbon_inverted["scope"]["configuration"]
    assert "head end of the patient" in carbon_inverted["scope"]["conditions"]

    bed_and_leg_rows = [
        item for item in loads if item["scope"]["chapter"] == "5.11.2 (1)"
    ]
    assert len(bed_and_leg_rows) == 1
    assert bed_and_leg_rows[0]["raw_value"] == "454 kg / 1000 lbs"
    assert "Leg section Item [58] or [62]" in bed_and_leg_rows[0]["scope"]["configuration"]
    assert "Head section Item [59] or [60]" in bed_and_leg_rows[0]["scope"]["configuration"]

    seat_extension = next(
        item for item in loads if item["scope"]["chapter"] == "5.11.3"
    )
    assert seat_extension["raw_value"] == "300 kg / 661 lbs"
    assert "Leg section" in seat_extension["scope"]["configuration"]

    shoulder_values = [
        item for item in loads if item["scope"]["chapter"] == "5.11.8"
    ]
    assert {item["raw_value"] for item in shoulder_values} == {
        "225 kg / 496 lbs",
        "160 kg / 352 lbs",
    }
    assert all(
        any(
            qualification["page"] == 49
            for qualification in item["source"]["qualification_sources"]
        )
        for item in shoulder_values
    )
    assert all(
        "Shoulder chair" in item["scope"]["configuration"]
        and item["scope"]["orientation"] == "Inverted"
        for item in shoulder_values
    )


def test_pst500_page_twelve_qualified_weights_are_not_flattened():
    chunks = _extract_pdf_page_chunks(
        "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
        12,
    )
    specifications = extract_specifications_from_chunks(chunks)

    assert not [
        item
        for item in specifications
        if item["attribute"] in {
            "Permissible Load",
            "Maximum Patient Weight",
        }
        and any(value in item["raw_value"] for value in ("454", "135"))
    ]


def test_pst500_qualification_evidence_matches_original_pages():
    filename = "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf"
    chunks = _extract_pdf_page_chunks(filename, 45)
    specifications = extract_specifications_from_chunks(chunks)
    pdf_path = Path(__file__).parents[1] / "data" / "raw" / filename
    document = pymupdf.open(pdf_path)
    try:
        for specification in specifications:
            for qualification in specification.get("source", {}).get(
                "qualification_sources", []
            ):
                page_text = document[qualification["page"] - 1].get_text()
                page_text = page_text.replace("�", "°")
                page_text = re.sub(r"\s+", " ", page_text).casefold()
                evidence = re.sub(
                    r"\s+",
                    " ",
                    qualification["evidence"],
                ).casefold()
                assert evidence in page_text
    finally:
        document.close()


def test_pst500_real_table_records_flow_to_scoped_matching(monkeypatch):
    chunks = _extract_pdf_page_chunks(
        "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
        45,
    )
    extracted = extract_specifications_from_chunks(chunks)
    document_name = "PST-500-Mobile-Operating-Table_IFU-DEC2019"
    specifications = [
        {
            "product": "PST 500 Operating Table",
            "document": document_name,
            "page": item["source"]["page"],
            "section": item["source"]["section"],
            "attribute": item["attribute"],
            "scope": item["scope"],
            "raw_value": item["raw_value"],
            "parsed_value": item["parsed_value"],
            "source": item["source"],
        }
        for item in extracted
        if item["attribute"] == "Permissible Load"
    ]
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    catalogue = [
        {
            "product": "PST 500 Operating Table",
            "document": document_name,
            "product_kind": "surgical_equipment",
            "identity_reliable": True,
        }
    ]

    normal_results = product_matcher._match_technical_requirement(
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg",
        catalogue_records=catalogue,
    )
    inverted_results = product_matcher._match_technical_requirement(
        "Permissible load for Carbon 1200 in inverted patient orientation "
        "at least 150 kg",
        catalogue_records=catalogue,
    )
    generic_results = product_matcher._match_technical_requirement(
        "Permissible load at least 150 kg",
        catalogue_records=catalogue,
    )

    normal = next(item for item in normal_results if item["product"])
    inverted = next(item for item in inverted_results if item["product"])
    generic = next(item for item in generic_results if item["product"])
    assert normal["status"] == "PASS"
    assert normal["raw_value"] == "160 kg / 352 lbs"
    assert normal["page"] == 45
    assert "5.11.5" in normal["section"]
    assert "Carbon 1200" in normal["source_evidence"]
    assert inverted["status"] == "FAIL"
    assert inverted["raw_value"] == "135 kg / 297 lbs"
    assert generic["status"] == "UNKNOWN"
    assert "configuration is unspecified" in generic["reason"]


def test_pst500_several_days_battery_statement_is_not_converted_to_hours():
    chunks = _extract_pdf_page_chunks(
        "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
        51,
    )
    specifications = extract_specifications_from_chunks(chunks)

    assert not [
        item
        for item in specifications
        if item["attribute"] == "Battery Backup"
    ]


def test_trusystem_original_pages_preserve_load_and_power_supply_scope():
    chunks = []
    for page in (42, 76, 78):
        chunks.extend(
            _extract_pdf_page_chunks(
                "TruSystem_7500_Column_UM.pdf",
                page,
            )
        )
    specifications = extract_specifications_from_chunks(chunks)

    durations = [
        item
        for item in specifications
        if item["attribute"] == "Electrical function movement duration"
    ]
    assert {
        item["scope"]["configuration"]: item["raw_value"]
        for item in durations
    } == {
        "mobile operating table column":
            "approx. 1 hour (total duration of movement for electrical functions)",
        "fixed installation operating table column":
            "approx. 30 minutes (total duration of movement for electrical functions)",
    }
    assert all(
        item["source"]["document"] == "TruSystem_7500_Column_UM"
        and item["source"]["page"] == 42
        and item["source"]["section"] == "5.1 Internal power supply"
        and "fully charged" in item["source"]["evidence"]
        and "total duration of movement for electrical functions"
        in item["source"]["evidence"]
        for item in durations
    )
    assert "lower speed" in next(
        item["scope"]["conditions"]
        for item in durations
        if item["scope"]["configuration"].startswith("fixed")
    )

    loads = [
        item
        for item in specifications
        if item["attribute"] == "Maximum operating table load"
    ]
    assert {
        item["scope"]["configuration"]: item["raw_value"]
        for item in loads
    } == {
        "mobile operating table column": "400 kg",
        "fixed installation operating table column": "400 kg",
    }
    assert all(
        item["source"]["page"] == 76
        and "depending on the operating table equipment and patient weight"
        in item["scope"]["conditions"]
        and item["raw_value"] in item["source"]["evidence"]
        for item in loads
    )

    batteries = [
        item
        for item in specifications
        if item["attribute"] in {
            "Battery Count",
            "Battery Voltage",
            "Battery Capacity",
        }
    ]
    assert any(
        item["attribute"] == "Battery Voltage"
        and item["raw_value"] == "40.7 V each"
        and item["source"]["page"] == 76
        and item["scope"]["configuration"] == "mobile operating table column"
        for item in batteries
    )
    assert any(
        item["attribute"] == "Battery Capacity"
        and item["raw_value"] == "4.7 Ah"
        and item["source"]["page"] == 76
        and item["scope"]["configuration"] == "mobile operating table column"
        for item in batteries
    )
    assert any(
        item["attribute"] == "Battery Count"
        and item["raw_value"] == "1 rechargeable batteries"
        and item["source"]["page"] == 76
        and item["scope"]["configuration"]
        == "fixed installation operating table column"
        and "Hybrid MR" in item["source"]["evidence"]
        for item in batteries
    )
    assert any(
        item["attribute"] == "Battery Voltage"
        and item["raw_value"] == "40.7 V"
        and item["source"]["page"] == 78
        and item["scope"]["power_supply"] == "External power supply unit"
        for item in batteries
    )
    assert not any(
        item["attribute"] == "Battery Backup"
        for item in specifications
    )


def test_pst500_original_page_electrical_values_remain_separate():
    chunks = _extract_pdf_page_chunks(
        "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
        80,
    )
    specifications = extract_specifications_from_chunks(chunks)
    electrical = [
        item
        for item in specifications
        if item["attribute"] in {
            "Battery Count",
            "Battery Voltage",
            "Battery Capacity",
        }
    ]

    assert {
        item["attribute"]: item["raw_value"]
        for item in electrical
    } == {
        "Battery Count": "3 batteries",
        "Battery Voltage": "12 V",
        "Battery Capacity": "12 Ah",
    }
    assert all(
        item["source"]["document"]
        == "PST-500-Mobile-Operating-Table_IFU-DEC2019"
        and item["source"]["page"] == 80
        and item["source"]["section"] == "12.1 Device data"
        and item["scope"]["power_supply"] == "Internal power supply"
        and "Internal power supply 3 batteries 12 V / 12 Ah"
        in item["source"]["evidence"]
        for item in electrical
    )
    assert not any(
        item["attribute"] == "Battery Backup"
        for item in specifications
    )


@pytest.mark.parametrize(
    ("filename", "pages", "product", "document", "query"),
    [
        (
            "TruSystem_7500_Column_UM.pdf",
            (42, 76, 78),
            "TruSystem 7500 Column UM",
            "TruSystem_7500_Column_UM",
            "Battery backup at least 1 hour",
        ),
        (
            "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf",
            (80,),
            "PST-500 Mobile Operating Table",
            "PST-500-Mobile-Operating-Table_IFU-DEC2019",
            "Battery backup at least 1 hour",
        ),
    ],
)
def test_electrical_values_do_not_satisfy_generic_battery_runtime_queries(
    monkeypatch,
    tmp_path,
    filename,
    pages,
    product,
    document,
    query,
):
    chunks = []
    for page in pages:
        chunks.extend(_extract_pdf_page_chunks(filename, page))
    specifications = extract_specifications_from_chunks(chunks)
    (tmp_path / f"{document}_chunks.json").write_text(
        json.dumps({"chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / f"{document}_specifications.json").write_text(
        json.dumps(
            {"products": [{"product": product, "specifications": specifications}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(
        product_matcher,
        "_catalogue_records",
        lambda: [
            {
                "product": product,
                "document": document,
                "product_kind": "surgical_equipment",
                "identity_reliable": True,
            }
        ],
    )

    loaded_specifications = product_matcher._load_processed_specifications()
    if "TruSystem" in filename:
        assert any(
            item["attribute"] == "Electrical function movement duration"
            and item["source"]["page"] == 42
            for item in loaded_specifications
        )
        assert {
            item["scope"]["configuration"]
            for item in loaded_specifications
            if item["attribute"] == "Maximum operating table load"
        } == {
            "mobile operating table column",
            "fixed installation operating table column",
        }
        assert any(
            item["attribute"] == "Battery Voltage"
            and item["source"]["page"] == 78
            and item["scope"]["power_supply"] == "External power supply unit"
            for item in loaded_specifications
        )
    else:
        assert {
            item["attribute"]
            for item in loaded_specifications
            if item["source"]["page"] == 80
        } >= {"Battery Count", "Battery Voltage", "Battery Capacity"}

    result = product_matcher.match_requirement(query)[0]

    assert result["status"] == "UNKNOWN"


def test_pst500_incomplete_permissible_load_is_rejected():
    assert not is_valid_attribute_value_pair(
        "Permissible Load",
        "160 kg /",
        parse_value("160 kg /"),
    )


def test_affinity_page_two_patient_weight_rows_keep_components_and_provenance():
    chunks = _extract_pdf_page_chunks(
        "207598-EN-r1_Affinity_SpecSheet-LR.pdf",
        2,
    )
    specifications = extract_specifications_from_chunks(chunks)
    patient_weights = [
        item
        for item in specifications
        if item["attribute"] == "Maximum Patient Weight"
    ]

    assert {
        item.get("component"): item["raw_value"]
        for item in patient_weights
    } == {
        "Bed": "500 lb",
        "Foot section": "400 lb",
    }
    for item in patient_weights:
        assert item["source"]["document"] == (
            "207598-EN-r1_Affinity_SpecSheet-LR"
        )
        assert item["source"]["page"] == 2
        assert item["source"]["section"] == "MAXIMUM PATIENT WEIGHT"
        assert item["raw_value"] in item["source"]["evidence"]
        assert item["component"].casefold() in item["source"]["evidence"].casefold()
        assert "patient weight limit" in item["source"]["evidence"].casefold()
        assert item["parsed_value"]["type"] == "scalar"
        assert item["parsed_value"]["unit"] == "lb"
    assert not any(
        item["attribute"] == "Maximum Lift Capacity"
        for item in patient_weights
    )


def test_hillrom_page_three_keeps_patient_weight_separate_from_swl():
    chunks = _extract_pdf_page_chunks(
        "AU_Hillrom_HR900-Accella_tech_specs_4pp_brox_LR.pdf",
        3,
    )
    specifications = extract_specifications_from_chunks(chunks)
    relevant = {
        item["attribute"]: item
        for item in specifications
        if item["attribute"] in {
            "Safe working load",
            "Maximum Patient Weight",
        }
    }

    assert set(relevant) == {"Safe working load", "Maximum Patient Weight"}
    assert relevant["Safe working load"]["raw_value"] == "250 kg"
    assert relevant["Maximum Patient Weight"]["raw_value"] == "185 kg"
    assert relevant["Safe working load"]["parsed_value"]["unit"] == "kg"
    assert relevant["Maximum Patient Weight"]["parsed_value"]["unit"] == "kg"
    for item in relevant.values():
        assert item["source"]["document"] == (
            "AU_Hillrom_HR900-Accella_tech_specs_4pp_brox_LR"
        )
        assert item["source"]["page"] == 3
        assert item["source"]["section"] == (
            "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ"
        )
        assert item["raw_value"] in item["source"]["evidence"]


def test_affinity_page_three_nested_capacity_table_retains_rows_and_provenance():
    chunks = _extract_affinity_page_three()
    specifications = extract_specifications_from_chunks(chunks)

    lift_specs = [
        item
        for item in specifications
        if item["attribute"] == "Maximum Lift Capacity"
    ]
    assert {
        item.get("component"): item["raw_value"]
        for item in lift_specs
    } == {
        "Bed": "500 lbs (227 kg)",
        "Foot section": "400 lbs (181 kg)",
    }

    independent_specs = {
        item["attribute"]: item["raw_value"]
        for item in specifications
        if item["attribute"] in {"Caster size", "Bed weight"}
    }
    assert independent_specs == {
        "Caster size": '6" (15 cm)',
        "Bed weight": "480 lbs (218 kg)",
    }
    assert not any(
        item["attribute"] in {"Bed", "Foot section"}
        for item in specifications
    )

    for item in lift_specs + [
        item
        for item in specifications
        if item["attribute"] in {"Caster size", "Bed weight"}
    ]:
        assert item["source"]["document"] == (
            "207598-EN-r1_Affinity_SpecSheet-LR"
        )
        assert item["source"]["page"] == 3
        assert item["source"]["section"] == "Technical Specifications"
        assert item["source"]["evidence"]
        assert item["attribute"] in item["source"]["evidence"]
        if item["attribute"] == "Maximum Lift Capacity":
            assert item["component"] in item["source"]["evidence"]
        assert item["raw_value"] in item["source"]["evidence"]


def test_affinity_nested_table_abstains_when_column_geometry_is_ambiguous():
    chunks = _extract_affinity_page_three()
    target_chunk = next(
        chunk for chunk in chunks if "Maximum Lift Capacity" in chunk["text"]
    )
    words = target_chunk["layout"]["words"]
    target_block = next(
        word["block"]
        for word in words
        if word["text"] == "Capacity" and word["bbox"][1] > 300
    )
    for word in words:
        if (
            word["block"] == target_block
            and word["bbox"][1] > 350
            and word["bbox"][0] > 140
        ):
            y0, y1 = word["bbox"][1], word["bbox"][3]
            word["bbox"] = [75, y0, 85, y1]

    specifications = extract_specifications_from_chunks([target_chunk])

    assert not any(
        item["attribute"] in {
            "Maximum Lift Capacity",
            "Bed",
            "Foot section",
        }
        for item in specifications
    )
    assert {
        item["attribute"]: item["raw_value"]
        for item in specifications
        if item["attribute"] in {"Caster size", "Bed weight"}
    } == {
        "Caster size": '6" (15 cm)',
        "Bed weight": "480 lbs (218 kg)",
    }


def test_missing_geometry_abstains_on_nested_rows_but_keeps_independent_specs():
    chunk = {
        "document": "affinity",
        "page": 3,
        "section": "Technical Specifications",
        "chunk_id": "chunk_3",
        "text": (
            "Technical Specifications\n"
            "Maximum Lift Capacity\n"
            "Bed\n500 lbs (227 kg)\n"
            "Foot section\n400 lbs (181 kg)\n"
            'Caster size\n6" (15 cm)\n'
            "Bed weight\n480 lbs (218 kg)"
        ),
    }

    specifications = extract_specifications_from_chunks([chunk])

    assert {
        item["attribute"]: item["raw_value"]
        for item in specifications
    } == {
        "Caster size": '6" (15 cm)',
        "Bed weight": "480 lbs (218 kg)",
    }
    assert not any(
        item.get("component")
        or item["attribute"] in {"Maximum Lift Capacity", "Bed", "Foot section"}
        for item in specifications
    )
