import json
from pathlib import Path

import pytest
import pymupdf

from src.ingestion.chunker import chunk_page
from src.ingestion.layout_inspector import extract_page_data
from src.retrieval import product_matcher
from src.retrieval.requirement_parser import parse_requirement
from src.retrieval.product_matcher import (
    match_requirement,
    validate_requirement_evidence,
)
from src.retrieval.spec_extractor import extract_specifications_from_chunks
from src.retrieval.value_parser import parse_value


def test_match_requirement_returns_stable_result_schema_for_technical_queries():
    results = match_requirement("Weight should be at most 5 kg")

    assert results
    first = results[0]
    assert set(
        [
            "requirement",
            "status",
            "product",
            "document",
            "page",
            "section",
            "evidence",
            "reason",
        ]
    ).issubset(first.keys())
    assert first["status"] in {"PASS", "FAIL", "UNKNOWN"}


def test_match_requirement_produces_presence_schema_for_category_queries():
    results = match_requirement("Is an ICU bed present?")

    assert results
    first = results[0]
    assert first["status"] in {"PRESENT", "NOT_PRESENT", "UNKNOWN"}
    assert "requirement" in first
    assert "evidence" in first


def test_match_requirement_tracks_document_provenance():
    result = product_matcher._empty_result(
        requirement="Battery backup must be at least 4 hours",
        status="PASS",
        product="Example product",
        document="example_document.pdf",
        page=3,
        section="Electrical",
        evidence="4 hours",
        reason="The value matches the requested battery duration.",
        confidence=0.9,
        query_type="technical",
    )

    assert result["document"] == "example_document.pdf"
    assert result["page"] == 3
    assert result["evidence"] == "4 hours"


def test_match_requirement_returns_unknown_for_unsupported_queries():
    results = match_requirement("What is the meaning of life?")

    assert results
    assert results[0]["status"] == "UNKNOWN"


def test_validate_requirement_evidence_rejects_mass_vs_length_mismatch():
    requirement = {"attribute": "Weight", "operator": ">=", "value": 200, "unit": "kg"}
    assert validate_requirement_evidence(requirement, "Weight", "200 cm") is False


def test_validate_requirement_evidence_rejects_voltage_for_mass_requirement():
    requirement = {"attribute": "Weight", "operator": ">=", "value": 200, "unit": "kg"}
    assert validate_requirement_evidence(requirement, "Weight", "100 V") is False


def test_validate_requirement_evidence_rejects_voltage_for_hours_requirement():
    requirement = {"attribute": "Battery Backup", "operator": ">=", "value": 100, "unit": "hours"}
    assert validate_requirement_evidence(requirement, "Battery Backup", "100 V") is False


def test_validate_requirement_evidence_rejects_frequency_for_hours_requirement():
    requirement = {"attribute": "Battery Backup", "operator": ">=", "value": 100, "unit": "hours"}
    assert validate_requirement_evidence(requirement, "Battery Backup", "100 kHz") is False


def test_validate_requirement_evidence_rejects_unrelated_numeric_evidence():
    requirement = {"attribute": "Safe Working Load", "operator": ">=", "value": 200, "unit": "kg"}
    assert validate_requirement_evidence(requirement, "Bed Height", "200 cm") is False
    assert validate_requirement_evidence(requirement, "Bed Height", "2 min ON, 8 min OFF") is False


def test_validate_requirement_evidence_rejects_related_but_not_equivalent_feature():
    requirement = {"attribute": "Trendelenburg Positioning", "operator": "=", "value": 1, "unit": None}
    assert validate_requirement_evidence(requirement, "Head-of-bed angle", "10° head-of-bed angle") is False


def test_validate_requirement_evidence_accepts_explicit_feature_keyword():
    requirement = {"attribute": "Trendelenburg Positioning", "operator": "=", "value": 1, "unit": None}
    assert validate_requirement_evidence(requirement, "Trendelenburg Positioning", "GAS ASSIST TRENDELENBURG") is True


def test_match_requirement_keeps_unknown_for_unsupported_queries():
    results = match_requirement("Is this product suitable for intensive care?")
    assert results
    assert results[0]["status"] == "UNKNOWN"


def test_match_requirement_accepts_real_safe_working_load_evidence():
    results = match_requirement("The bed must have a safe working load of at least 200 kg")
    assert results
    assert any(r["status"] == "PASS" and r["document"] == "AU_Hillrom_HR900-Accella_tech_specs_4pp_brox_LR" for r in results)


def test_match_requirement_preserves_provenance_for_supported_evidence():
    result = product_matcher._empty_result(
        requirement="Weight should be at most 5 kg",
        status="PASS",
        product="Example product",
        document="example_document.pdf",
        page=12,
        section="Technical Specs",
        evidence="4 kg",
        reason="4 kg satisfies the requirement.",
        confidence=0.8,
        query_type="technical",
    )

    assert result["document"] == "example_document.pdf"
    assert result["page"] == 12
    assert result["section"] == "Technical Specs"


def test_match_requirement_rejects_incompatible_units_generically():
    requirement = {"attribute": "Safe Working Load", "operator": ">=", "value": 200, "unit": "kg"}
    assert validate_requirement_evidence(requirement, "Safe Working Load", "250 kg") is True
    assert validate_requirement_evidence(requirement, "Safe Working Load", "250 cm") is False
    assert validate_requirement_evidence(requirement, "Safe Working Load", "250 V") is False

    battery_requirement = {"attribute": "Battery Backup", "operator": ">=", "value": 100, "unit": "hours"}
    assert validate_requirement_evidence(battery_requirement, "Battery Backup", "100 V") is False


def test_feature_evidence_quality_rejects_navigation_and_accepts_technical_sentence():
    assert product_matcher._is_technical_feature_evidence("5.7.4 Trendelenburg ........ 36") is False
    assert product_matcher._is_technical_feature_evidence("Achieve 8° of Trendelenburg on demand.") is True
    assert product_matcher._is_technical_feature_evidence("Trendelenburg/reverse Trendelenburg\n+17° to -17°") is True


def test_feature_negative_evidence_requires_relevant_negation():
    assert product_matcher._feature_negation_matches("The bed is not suitable for underwater operation.", "underwater operation") is True
    assert product_matcher._feature_negation_matches("Emergency mode ensures the Trendelenburg function in the event of a malfunction.", "trendelenburg") is False
    assert product_matcher._feature_negation_matches("Battery backup is available during transport.", "underwater operation") is False


def test_battery_duration_evidence_requires_a_function_usage_duration():
    chunks = [
        {
            "document": "manual.pdf",
            "page": 3,
            "section": "Warnings",
            "chunk_id": "alarm",
            "text": "Two pulsing tone sequences repeat at intervals of several minutes. The batteries need to be charged.",
        },
        {
            "document": "manual.pdf",
            "page": 4,
            "section": "Battery operation",
            "chunk_id": "runtime",
            "text": "If the batteries are fully charged, the electrical functions can be used for several days.",
        },
        {
            "document": "manual.pdf",
            "page": 5,
            "section": "Battery operation",
            "chunk_id": "switch-off",
            "text": "In battery mode, the column automatically switches off after 8 hours.",
        },
    ]

    evidence = product_matcher._find_battery_duration_evidence(
        chunks, {"manual.pdf"}
    )

    assert [(item["page"], item["chunk_id"]) for item in evidence] == [
        (4, "runtime")
    ]
    assert "electrical functions can be used for several days" in evidence[0]["evidence"]


def test_width_requirement_ignores_unrelated_same_unit_attributes(monkeypatch):
    requirement = parse_requirement("The operating table should have a width of at least 90 cm")
    assert requirement["attribute"] == "Width"

    width_candidate = {"attribute": "Width", "raw_value": "90 cm", "parsed_value": {"type": "scalar", "value": 90.0, "unit": "cm"}}
    height_candidate = {"attribute": "Height adjustment", "raw_value": "43.1 cm to 80.8 cm", "parsed_value": {"type": "range", "min": 43.1, "max": 80.8, "unit": "cm"}}
    siderail_candidate = {"attribute": "Siderail height", "raw_value": "39.3 cm", "parsed_value": {"type": "scalar", "value": 39.3, "unit": "cm"}}
    length_candidate = {"attribute": "Length", "raw_value": "200 cm", "parsed_value": {"type": "scalar", "value": 200.0, "unit": "cm"}}

    assert validate_requirement_evidence(requirement, width_candidate["attribute"], width_candidate["raw_value"]) is True
    assert validate_requirement_evidence(requirement, height_candidate["attribute"], height_candidate["raw_value"]) is False
    assert validate_requirement_evidence(requirement, siderail_candidate["attribute"], siderail_candidate["raw_value"]) is False
    assert validate_requirement_evidence(requirement, length_candidate["attribute"], length_candidate["raw_value"]) is False

    bed = {
        "product": "Example Bed",
        "document": "bed.pdf",
        "product_kind": "medical_bed",
        "identity_reliable": True,
    }
    table = {
        "product": "Example Operating Table",
        "document": "table.pdf",
        "product_kind": "surgical_equipment",
        "identity_reliable": True,
    }
    monkeypatch.setattr(
        product_matcher, "_catalogue_records", lambda: [bed, table]
    )
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: [
            {
                "product": bed["product"],
                "document": bed["document"],
                "attribute": "Width",
                "raw_value": "90 cm",
                "parsed_value": {"type": "scalar", "value": 90, "unit": "cm"},
                "source": {"document": "bed.pdf", "page": 2, "evidence": "Width 90 cm"},
            },
            {
                "product": table["product"],
                "document": table["document"],
                "attribute": "Width",
                "raw_value": "80 cm",
                "parsed_value": {"type": "scalar", "value": 80, "unit": "cm"},
                "source": {"document": "table.pdf", "page": 2, "evidence": "Width 80 cm"},
            },
        ],
    )

    results = product_matcher.match_requirement(
        "The operating table should have a width of at least 90 cm"
    )
    assert len(results) == 1
    assert results[0]["product"] == table["product"]
    assert results[0]["status"] == "FAIL"


def test_numeric_load_queries_are_not_routed_to_capability_path():
    query = "The operating table should support a patient load of at least 500 kg"
    requirement = parse_requirement(query)
    assert requirement["attribute"] == "Patient Load"
    assert requirement["operator"] == ">="
    assert requirement["unit"] == "kg"
    assert product_matcher.classify_query(query) == "technical"

    results = product_matcher.match_requirement(query)
    assert results
    assert not any(r["status"] == "PRESENT" for r in results)
    assert all(r["status"] in {"PASS", "FAIL", "UNKNOWN"} for r in results)


def test_attribute_equivalence_is_shared_and_does_not_merge_load_concepts():
    requirement = {
        "attribute": "Safe Working Load",
        "operator": ">=",
        "value": 200,
        "unit": "kg",
    }
    for equivalent in ("Safe working load", "Working load", "Load capacity"):
        assert validate_requirement_evidence(requirement, equivalent, "250 kg")
        assert product_matcher.evaluate_requirement(
            requirement,
            "250 kg",
            candidate_attribute=equivalent,
        ) == "PASS"

    for unrelated in (
        "Product weight",
        "Maximum patient weight",
        "Patient load",
        "Maximum load",
    ):
        assert not validate_requirement_evidence(requirement, unrelated, "250 kg")
        assert product_matcher.evaluate_requirement(
            requirement,
            "250 kg",
            candidate_attribute=unrelated,
        ) == "UNKNOWN"


def test_product_weight_does_not_match_patient_or_safe_load():
    requirement = {
        "attribute": "Product Weight",
        "operator": "<=",
        "value": 200,
        "unit": "kg",
    }
    assert validate_requirement_evidence(requirement, "Weight", "150 kg")
    assert not validate_requirement_evidence(requirement, "Maximum Patient Weight", "150 kg")
    assert not validate_requirement_evidence(requirement, "Patient Load", "150 kg")
    assert not validate_requirement_evidence(requirement, "Safe Working Load", "150 kg")


def test_lift_capacity_does_not_pass_safe_working_load_requirement(monkeypatch):
    source = {
        "document": "affinity.pdf",
        "page": 3,
        "section": "Technical Specifications",
        "chunk_id": "chunk_4",
        "evidence": "Maximum Lift Capacity\nBed\n500 lbs (227 kg)",
    }
    monkeypatch.setattr(
        product_matcher,
        "_catalogue_records",
        lambda: [
            {
                "product": "Affinity 4 Birthing Bed",
                "document": "affinity.pdf",
                "product_kind": "medical_bed",
                "identity_reliable": True,
            }
        ],
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: [
            {
                "product": "Affinity 4 Birthing Bed",
                "document": "affinity.pdf",
                "page": 3,
                "section": "Technical Specifications",
                "attribute": "Maximum Lift Capacity",
                "component": "Bed",
                "raw_value": "500 lbs (227 kg)",
                "parsed_value": {
                    "type": "mixed",
                    "raw": "500 lbs (227 kg)",
                    "parsed_value": {
                        "type": "scalar",
                        "value": 500,
                        "unit": "lb",
                    },
                    "description": "(227 kg)",
                },
                "source": source,
            }
        ],
    )

    results = match_requirement("Safe working load at least 200 kg")

    assert results
    assert all(result["status"] != "PASS" for result in results)
    assert any(result["status"] == "UNKNOWN" for result in results)


def _match_component_requirement(monkeypatch, query, specifications):
    source_record = {
        "product": "Affinity 4 Birthing Bed",
        "document": "affinity.pdf",
        "product_kind": "medical_bed",
        "identity_reliable": True,
    }
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_chunks",
        lambda: [],
    )
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    return product_matcher._match_technical_requirement(
        query,
        catalogue_records=[source_record],
    )


def _component_spec(component, raw_value, page=3):
    source = {
        "document": "affinity.pdf",
        "page": page,
        "section": "Technical Specifications",
        "chunk_id": "chunk_3",
        "evidence": (
            f"Maximum Lift Capacity\n{component}\n{raw_value}"
        ) if component else f"Maximum Lift Capacity\n{raw_value}",
    }
    return {
        "product": "Affinity 4 Birthing Bed",
        "document": "affinity.pdf",
        "page": page,
        "section": "Technical Specifications",
        "attribute": "Maximum Lift Capacity",
        "component": component,
        "raw_value": raw_value,
        "parsed_value": parse_value(raw_value),
        "source": source,
    }


def _patient_weight_spec(document, raw_value, component=None, page=3):
    evidence = f"Maximum Patient Weight\n{raw_value}"
    if component:
        evidence = (
            f"MAXIMUM PATIENT WEIGHT\n"
            f"{raw_value} {component.casefold()} patient weight limit."
        )
    source = {
        "document": document,
        "page": page,
        "section": (
            "MAXIMUM PATIENT WEIGHT"
            if component
            else "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ"
        ),
        "chunk_id": "chunk_3",
        "evidence": evidence,
    }
    return {
        "product": "Test Medical Bed",
        "document": document,
        "page": page,
        "section": source["section"],
        "attribute": "Maximum Patient Weight",
        "component": component,
        "raw_value": raw_value,
        "parsed_value": parse_value(raw_value),
        "source": source,
    }


def test_bed_lift_requirement_uses_only_bed_component_evidence(monkeypatch):
    results = _match_component_requirement(
        monkeypatch,
        "Maximum Lift Capacity for Bed at least 200 kg",
        [
            _component_spec("Bed", "500 lbs (227 kg)"),
            _component_spec("Foot section", "400 lbs (181 kg)"),
        ],
    )
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")
    assert result["status"] == "PASS"
    assert result["source"]["page"] == 3
    assert result["source"]["section"] == "Technical Specifications"
    assert "Bed" in result["source_evidence"]


def test_foot_section_lift_requirement_uses_foot_section_evidence(monkeypatch):
    results = _match_component_requirement(
        monkeypatch,
        "Maximum Lift Capacity for Foot section at least 150 kg",
        [
            _component_spec("Bed", "500 lbs (227 kg)"),
            _component_spec("Foot section", "400 lbs (181 kg)"),
        ],
    )
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")
    assert result["status"] == "PASS"
    assert "Foot section" in result["source_evidence"]


@pytest.mark.parametrize(
    ("query", "specification"),
    [
        (
            "Maximum Lift Capacity for Bed at least 200 kg",
            _component_spec("Foot section", "400 lbs (181 kg)"),
        ),
        (
            "Maximum Lift Capacity for Foot section at least 150 kg",
            _component_spec("Bed", "500 lbs (227 kg)"),
        ),
    ],
)
def test_lift_requirement_cannot_pass_using_another_component(
    monkeypatch, query, specification
):
    results = _match_component_requirement(monkeypatch, query, [specification])
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")

    assert result["status"] == "UNKNOWN"
    assert "explicitly associated" in result["reason"]
    assert result["sources"][0]["page"] == 3
    assert result["sources"][0]["section"] == "Technical Specifications"


def test_generic_lift_requirement_is_unknown_when_component_is_unspecified(monkeypatch):
    results = _match_component_requirement(
        monkeypatch,
        "Maximum Lift Capacity at least 200 kg",
        [
            _component_spec("Bed", "500 lbs (227 kg)"),
            _component_spec("Foot section", "400 lbs (181 kg)"),
        ],
    )
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")

    assert result["status"] == "UNKNOWN"
    assert "component is unspecified" in result["reason"]
    assert {source["page"] for source in result["sources"]} == {3}
    assert len(result["sources"]) == 2


def test_requested_component_without_component_evidence_is_unknown(monkeypatch):
    results = _match_component_requirement(
        monkeypatch,
        "Maximum Lift Capacity for Bed at least 200 kg",
        [_component_spec(None, "500 lbs (227 kg)")],
    )
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")

    assert result["status"] == "UNKNOWN"
    assert "explicitly associated with Bed" in result["reason"]
    assert result["source"]["page"] == 3


def test_non_component_specifications_continue_to_match(monkeypatch):
    source = {
        "document": "affinity.pdf",
        "page": 3,
        "section": "Technical Specifications",
        "chunk_id": "chunk_3",
        "evidence": "Width\n90 cm",
    }
    results = _match_component_requirement(
        monkeypatch,
        "Width at least 90 cm",
        [
            {
                "product": "Affinity 4 Birthing Bed",
                "document": "affinity.pdf",
                "page": 3,
                "section": "Technical Specifications",
                "attribute": "Width",
                "raw_value": "90 cm",
                "parsed_value": parse_value("90 cm"),
                "source": source,
            }
        ],
    )
    result = next(item for item in results if item["product"] == "Affinity 4 Birthing Bed")

    assert result["status"] == "PASS"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Safe Working Load at least 200 kg", "PASS"),
        ("Maximum Patient Weight at least 200 kg", "FAIL"),
        ("Maximum Patient Weight at least 150 kg", "PASS"),
    ],
)
def test_hillrom_swl_and_patient_weight_evaluate_independently(
    monkeypatch, query, expected
):
    document = "hillrom-900.pdf"
    specifications = [
        {
            "product": "Test Medical Bed",
            "document": document,
            "page": 3,
            "section": "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ",
            "attribute": "Safe working load",
            "raw_value": "250 kg",
            "parsed_value": parse_value("250 kg"),
            "source": {
                "document": document,
                "page": 3,
                "section": "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ",
                "chunk_id": "chunk_1",
                "evidence": "Safe working load\n250 kg",
            },
        },
        {
            "product": "Test Medical Bed",
            "document": document,
            "page": 3,
            "section": "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ",
            "attribute": "Maximum Patient Weight",
            "raw_value": "185 kg",
            "parsed_value": parse_value("185 kg"),
            "source": {
                "document": document,
                "page": 3,
                "section": "HILLROM 900 ACCELLA BED TECHNICAL SPECIFICATIONS ANZ",
                "chunk_id": "chunk_1",
                "evidence": (
                    "Maximum patient weight (intensive and acute care)\n185 kg"
                ),
            },
        },
    ]
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    results = product_matcher._match_technical_requirement(
        query,
        catalogue_records=[
            {
                "product": "Test Medical Bed",
                "document": document,
                "product_kind": "medical_bed",
                "identity_reliable": True,
            }
        ],
    )
    result = next(item for item in results if item["product"] == "Test Medical Bed")

    assert result["status"] == expected


@pytest.mark.parametrize(
    ("query", "component", "expected"),
    [
        ("Maximum Patient Weight for Bed at least 200 kg", "Bed", "PASS"),
        (
            "Maximum Patient Weight for Foot section at least 150 kg",
            "Foot section",
            "PASS",
        ),
        ("Maximum Patient Weight for Bed at least 200 kg", "Foot section", "UNKNOWN"),
        (
            "Maximum Patient Weight for Foot section at least 150 kg",
            "Bed",
            "UNKNOWN",
        ),
    ],
)
def test_affinity_patient_weight_component_requirements_are_scoped(
    monkeypatch, query, component, expected
):
    document = "affinity.pdf"
    specifications = [
        _patient_weight_spec(document, "500 lb", component="Bed", page=2),
        _patient_weight_spec(
            document,
            "400 lb",
            component="Foot section",
            page=2,
        ),
    ]
    if expected == "UNKNOWN":
        specifications = [
            item for item in specifications if item["component"] == component
        ]
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    results = product_matcher._match_technical_requirement(
        query,
        catalogue_records=[
            {
                "product": "Test Medical Bed",
                "document": document,
                "product_kind": "medical_bed",
                "identity_reliable": True,
            }
        ],
    )
    result = next(item for item in results if item["product"] == "Test Medical Bed")

    assert result["status"] == expected
    if expected == "PASS":
        assert result["source"]["page"] == 2
        assert result["source"]["section"] == "MAXIMUM PATIENT WEIGHT"
        assert component.casefold() in result["source_evidence"].casefold()


def test_generic_affinity_patient_weight_requirement_abstains_for_components(
    monkeypatch,
):
    document = "affinity.pdf"
    specifications = [
        _patient_weight_spec(document, "500 lb", component="Bed", page=2),
        _patient_weight_spec(
            document,
            "400 lb",
            component="Foot section",
            page=2,
        ),
    ]
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    results = product_matcher._match_technical_requirement(
        "Maximum Patient Weight at least 200 kg",
        catalogue_records=[
            {
                "product": "Test Medical Bed",
                "document": document,
                "product_kind": "medical_bed",
                "identity_reliable": True,
            }
        ],
    )
    result = next(item for item in results if item["product"] == "Test Medical Bed")

    assert result["status"] == "UNKNOWN"
    assert "component is unspecified" in result["reason"]
    assert len(result["sources"]) == 2


def test_missing_candidate_attribute_cannot_be_validated_for_named_requirement():
    requirement = {
        "attribute": "Width",
        "operator": ">=",
        "value": 90,
        "unit": "cm",
    }
    assert not validate_requirement_evidence(requirement, None, "90 cm")
    assert product_matcher.evaluate_requirement(
        requirement,
        "90 cm",
        candidate={"raw_value": "90 cm"},
    ) == "UNKNOWN"


def test_specification_loader_preserves_complete_source_metadata(tmp_path, monkeypatch):
    import json

    source = {
        "document": "device.pdf",
        "page": 4,
        "section": "Dimensions",
        "chunk_id": "chunk_12",
        "evidence": "Width\n90 cm",
    }
    payload = {
        "products": [
            {
                "product_family": "Device X",
                "specifications": [
                    {
                        "attribute": "Width",
                        "component": "Bed",
                        "raw_value": "90 cm",
                        "parsed_value": {"type": "scalar", "value": 90, "unit": "cm"},
                        "source": source,
                    }
                ],
            }
        ]
    }
    (tmp_path / "device_specifications.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)

    loaded = product_matcher._load_processed_specifications()
    assert loaded[0]["source"] == source
    assert loaded[0]["section"] == "Dimensions"
    assert loaded[0]["chunk_id"] == "chunk_12"
    assert loaded[0]["component"] == "Bed"


def test_technical_match_returns_complete_source_provenance(monkeypatch):
    source = {
        "document": "device.pdf",
        "page": 4,
        "section": "Dimensions",
        "chunk_id": "chunk_12",
        "evidence": "Width\n90 cm",
    }
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: [
            {
                "product": "Device X",
                "document": "device.pdf",
                "page": 4,
                "section": "Dimensions",
                "attribute": "Width",
                "raw_value": "90 cm",
                "parsed_value": {"type": "scalar", "value": 90, "unit": "cm"},
                "source": source,
            }
        ],
    )
    result = next(
        item
        for item in match_requirement("Width at least 90 cm")
        if item["product"] == "Device X"
    )
    assert result["status"] == "PASS"
    assert result["source"] == source
    assert result["sources"] == [source]
    assert result["chunk_id"] == "chunk_12"
    assert result["source_evidence"] == "Width\n90 cm"


def test_conflicting_technical_evidence_for_one_product_returns_unknown(monkeypatch):
    base_source = {
        "document": "device-a.pdf",
        "page": 2,
        "section": "Dimensions",
        "chunk_id": "chunk_2",
        "evidence": "Width\n90 cm",
    }
    specifications = [
        {
            "product": "Device X",
            "document": "device-a.pdf",
            "page": 2,
            "section": "Dimensions",
            "attribute": "Width",
            "raw_value": "90 cm",
            "parsed_value": {"type": "scalar", "value": 90, "unit": "cm"},
            "source": base_source,
        },
        {
            "product": "Device X",
            "document": "device-b.pdf",
            "page": 3,
            "section": "Dimensions",
            "attribute": "Width",
            "raw_value": "80 cm",
            "parsed_value": {"type": "scalar", "value": 80, "unit": "cm"},
            "source": {
                **base_source,
                "document": "device-b.pdf",
                "page": 3,
                "chunk_id": "chunk_8",
                "evidence": "Width\n80 cm",
            },
        },
    ]
    monkeypatch.setattr(
        product_matcher, "_load_processed_specifications", lambda: specifications
    )

    results = match_requirement("Width at least 85 cm")
    device_result = next(result for result in results if result["product"] == "Device X")
    assert device_result["status"] == "UNKNOWN"
    assert len(device_result["sources"]) == 2
    assert "conflicting" in device_result["reason"].lower()


def test_conflicting_capability_evidence_returns_unknown(monkeypatch):
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_chunks",
        lambda: [
            {
                "product": "Device X",
                "document": "device.pdf",
                "page": 2,
                "section": "Features",
                "chunk_id": "chunk_2",
                "text": "The bed supports underwater operation.",
            },
            {
                "product": "Device X",
                "document": "device.pdf",
                "page": 3,
                "section": "Features",
                "chunk_id": "chunk_3",
                "text": "Underwater operation is not supported.",
            },
        ],
    )
    monkeypatch.setattr(product_matcher, "_document_product", lambda _document: None)

    results = match_requirement("Does the bed support underwater operation?")
    assert len(results) == 1
    assert results[0]["status"] == "UNKNOWN"
    assert "conflicting" in results[0]["reason"].lower()
    assert len(results[0]["sources"]) == 2


def _permissible_load_spec(
    raw_value,
    configuration="Foot end: Carbon 1200 tabletop section Item [53]",
    orientation="Normal",
    chapter="5.11.5",
):
    document = "PST-500-Mobile-Operating-Table_IFU-DEC2019"
    scope = {
        "configuration": configuration,
        "orientation": orientation,
        "chapter": chapter,
        "restriction": "Yes",
    }
    qualification_page = 45
    qualification_section = f"{chapter} Operating tabletop configuration"
    if chapter == "5.11.8":
        qualification_section = "5.11.8 Operating tabletop with shoulder chair"
        position = "pushed in" if raw_value.startswith("225") else "pulled out"
        scope["conditions"] = (
            "Patient weights are permitted if the longitudinal extension "
            "on the head positioning is " + position + "."
        )
        qualification_page = 49
    elif chapter == "5.11.5":
        qualification_section = "5.11.5 Operating tabletop with Carbon 1200 tabletop section"
        travel_end = "foot" if orientation == "Normal" else "head"
        scope["conditions"] = (
            f"Patient weights are possible in the {orientation.lower()} patient "
            f"orientation. Longitudinal travel of the operating tabletop towards "
            f"the {travel_end} end of the patient is restricted by 100 mm."
        )
        qualification_page = 48
    elif chapter == "5.11.2 (1)":
        qualification_section = (
            "5.11.2 (1) Operating tabletop with head section and leg section"
        )
        scope["conditions"] = (
            "Patient weights are permitted under the following conditions: "
            "The longitudinal travel of the operating tabletop must be in "
            "the level position. The operating tabletop must be inclined by "
            "no more than 15 degrees around the lateral and longitudinal axis. "
            "The tilt function must not be tilted beyond 15 degrees."
        )
        qualification_page = 46
    source = {
        "document": document,
        "page": 45,
        "section": f"{chapter} Operating tabletop configuration",
        "chunk_id": "chunk_1",
        "evidence": (
            f"{configuration}; {orientation}; "
            f"Permissible load: {raw_value}; restriction: Yes; "
            f"{scope.get('conditions', '')}"
        ),
        "scope": scope,
    }
    if "conditions" in scope:
        source["qualification_sources"] = [
            {
                "document": document,
                "page": qualification_page,
                "section": qualification_section,
                "evidence": scope["conditions"],
            }
        ]
    return {
        "product": "PST 500 Operating Table",
        "document": document,
        "page": 45,
        "section": source["section"],
        "attribute": "Permissible Load",
        "raw_value": raw_value,
        "parsed_value": parse_value(raw_value),
        "scope": scope,
        "source": source,
    }


def _match_permissible_load_requirement(monkeypatch, query, specifications):
    document = "PST-500-Mobile-Operating-Table_IFU-DEC2019"
    monkeypatch.setattr(
        product_matcher,
        "_load_processed_specifications",
        lambda: specifications,
    )
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    return product_matcher._match_technical_requirement(
        query,
        catalogue_records=[
            {
                "product": "PST 500 Operating Table",
                "document": document,
                "product_kind": "surgical_equipment",
                "identity_reliable": True,
            }
        ],
    )


def test_pst_permissible_load_matches_only_explicit_compatible_scope(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg",
        [_permissible_load_spec("160 kg / 352 lbs")],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "PASS"
    assert result["page"] == 45
    assert result["scope"]["orientation"] == "Normal"
    assert "Carbon 1200" in result["source_evidence"]
    assert "restricted by 100 mm" in result["scope"]["conditions"]
    assert result["source"]["qualification_sources"][0]["page"] == 48


def test_pst_carbon_normal_passes_when_restriction_is_not_excluded(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg",
        [_permissible_load_spec("160 kg / 352 lbs")],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "PASS"
    assert "restricted by 100 mm" in result["source_evidence"]


def test_pst_carbon_normal_without_restrictions_does_not_pass(monkeypatch):
    query = (
        "Permissible load for Carbon 1200 in normal patient orientation "
        "without restrictions at least 150 kg"
    )
    requirement = parse_requirement(query)
    assert requirement["condition_scope"] == {"restriction": "none"}

    results = _match_permissible_load_requirement(
        monkeypatch,
        query,
        [_permissible_load_spec("160 kg / 352 lbs")],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "FAIL"
    assert "restriction applies" in result["reason"].lower()
    assert "restricted by 100 mm" in result["source_evidence"]
    assert result["source"]["qualification_sources"][0]["page"] == 48


def test_pst_missing_restriction_evidence_is_unknown(monkeypatch):
    specification = _permissible_load_spec("160 kg / 352 lbs")
    specification["scope"].pop("restriction")
    specification["scope"].pop("conditions")
    specification["source"].pop("qualification_sources")
    query = (
        "Permissible load for Carbon 1200 in normal patient orientation "
        "without restrictions at least 150 kg"
    )
    results = _match_permissible_load_requirement(
        monkeypatch,
        query,
        [specification],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "does not establish whether restrictions apply" in result["reason"].lower()


def test_pst_carbon_inverted_load_fails_numeric_threshold(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 in inverted patient orientation "
        "at least 150 kg",
        [
            _permissible_load_spec(
                "135 kg / 297 lbs",
                orientation="Inverted",
            )
        ],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "FAIL"
    assert result["raw_value"] == "135 kg / 297 lbs"


def _chapter_511_2_specification():
    return _permissible_load_spec(
        "454 kg / 1000 lbs",
        configuration=(
            "Foot end: Leg section Item [58] or [62]; "
            "Head end: Head section Item [59] or [60]"
        ),
        chapter="5.11.2 (1)",
    )


def test_pst_chapter_511_2_twenty_degree_requirement_fails(monkeypatch):
    query = (
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "tilted 20 degrees, at least 400 kg"
    )
    requirement = parse_requirement(query)
    assert requirement["value"] == 400
    assert requirement["condition_scope"]["inclination"]["value"] == 20

    results = _match_permissible_load_requirement(
        monkeypatch,
        query,
        [_chapter_511_2_specification()],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "FAIL"
    assert "exceeds the source limit of 15 degrees" in result["reason"]
    assert result["source"]["qualification_sources"][0]["page"] == 46
    assert "no more than 15 degrees" in result["source_evidence"]


def test_pst_chapter_511_2_supported_conditions_can_pass(monkeypatch):
    query = (
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "longitudinal travel level and inclination no more than 15 degrees, "
        "at least 400 kg"
    )
    requirement = parse_requirement(query)
    assert requirement["condition_scope"] == {
        "longitudinal_travel": "level",
        "inclination": {
            "operator": "<=",
            "value": 15,
            "unit": "degrees",
        },
    }

    results = _match_permissible_load_requirement(
        monkeypatch,
        query,
        [_chapter_511_2_specification()],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "PASS"
    assert result["raw_value"] == "454 kg / 1000 lbs"
    assert result["source"]["qualification_sources"][0]["page"] == 46


def test_pst_explicit_condition_without_source_qualification_is_unknown(monkeypatch):
    specification = _chapter_511_2_specification()
    specification["scope"].pop("conditions")
    specification["source"].pop("qualification_sources")
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for chapter 5.11.2 (1), normal orientation, "
        "longitudinal travel level and inclination no more than 15 degrees, "
        "at least 400 kg",
        [specification],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "does not establish" in result["reason"].lower()


def test_pst_unrecognized_requested_condition_returns_unknown(monkeypatch):
    query = (
        "Permissible load for Carbon 1200 normal orientation with accessory "
        "configuration X at least 150 kg"
    )
    results = _match_permissible_load_requirement(
        monkeypatch,
        query,
        [_permissible_load_spec("160 kg / 352 lbs")],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "not recognized" in result["reason"].lower()


def test_pst_permissible_load_rejects_incompatible_configuration(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg",
        [
            _permissible_load_spec(
                "160 kg / 352 lbs",
                configuration="Foot end: Carbon 600 tabletop section Item [54]",
                orientation="Inverted",
                chapter="5.11.6",
            )
        ],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "configuration" in result["reason"].lower()


def test_pst_generic_permissible_load_is_unknown_for_multiple_scopes(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load at least 150 kg",
        [
            _permissible_load_spec("160 kg / 352 lbs", orientation="Normal"),
            _permissible_load_spec(
                "135 kg / 297 lbs",
                orientation="Inverted",
            ),
        ],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "configuration is unspecified" in result["reason"].lower()
    assert len(result["sources"]) == 2


def test_pst_carbon_configuration_without_orientation_is_unknown(monkeypatch):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 at least 150 kg",
        [
            _permissible_load_spec("160 kg / 352 lbs", orientation="Normal"),
            _permissible_load_spec("135 kg / 297 lbs", orientation="Inverted"),
        ],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "more than one" in result["reason"].lower()


def test_pst_permissible_load_without_scope_metadata_is_unknown(monkeypatch):
    specification = _permissible_load_spec("160 kg / 352 lbs")
    specification.pop("scope")
    specification["source"].pop("scope")
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load at least 150 kg",
        [specification],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == "UNKNOWN"
    assert "configuration" in result["reason"].lower()


@pytest.fixture(scope="module")
def pst_pdf_permissible_load_specs():
    pdf_path = (
        Path(__file__).parents[1]
        / "data"
        / "raw"
        / "PST-500-Mobile-Operating-Table_IFU-DEC2019.pdf"
    )
    document = pymupdf.open(pdf_path)
    chunks = []
    next_chunk_id = 1
    qualification_pages = {}
    try:
        for page_number in range(44, 50):
            page = document[page_number - 1]
            qualification_pages[page_number] = page.get_text()
            page_data = extract_page_data(page, page_number)
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

    extracted = extract_specifications_from_chunks(chunks, pdf_path.stem)
    return extracted, qualification_pages


def _match_real_pst_permissible_load(
    monkeypatch,
    query,
    extracted_specifications,
):
    product = "PST 500 Operating Table"
    specifications = [
        {
            **item,
            "product": product,
            "document": item["source"]["document"],
            "page": item["source"]["page"],
            "section": item["source"]["section"],
            "scope": item["scope"],
        }
        for item in extracted_specifications
        if item["attribute"] == "Permissible Load"
    ]
    return _match_permissible_load_requirement(
        monkeypatch,
        query,
        specifications,
    )


@pytest.mark.parametrize(
    ("query", "expected_status", "expected_value"),
    [
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "Trendelenburg position at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "unevenly loaded at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for Carbon 1200 normal orientation without "
            "limiting operating table functions at least 150 kg",
            "FAIL",
            "160 kg / 352 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination >=15 degrees, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination <=15 degrees, at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination =15 degrees, at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination >15 degrees, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination >10 degrees, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination <20 degrees, at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "inclination <15 degrees, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tilted 20 degrees, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "head-down position at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for Carbon 1200 normal patient orientation "
            "at least 150 kg",
            "PASS",
            "160 kg / 352 lbs",
        ),
        (
            "Permissible load for Carbon 1200 inverted patient orientation "
            "at least 150 kg",
            "FAIL",
            "135 kg / 297 lbs",
        ),
        (
            "Permissible load for chapter 5.11.3, normal orientation, "
            "without restrictions, at least 300 kg",
            "PASS",
            "300 kg / 661 lbs",
        ),
        (
            "Permissible load for chapter 5.11.3, normal orientation, "
            "without limiting operating table functions, at least 300 kg",
            "PASS",
            "300 kg / 661 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "longitudinal travel level and inclination <=15 degrees, "
            "at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "longitudinal travel not level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "longitudinal travel level, at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "non-level tabletop, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "level tabletop, at least 400 kg",
            "PASS",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "travel non-level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "travel not-level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "not-level tabletop, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tabletop non-level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tabletop must not be level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "travel must not be level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "travel shall not be level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "travel is not at level, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "at 20°, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "lateral decubitus position, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "sloped tabletop, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "supine, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "side-lying, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "on an incline, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tabletop on an incline, at least 400 kg",
            "UNKNOWN",
            "454 kg / 1000 lbs",
        ),
        (
            "Permissible load for chapter 5.11.2 (1), normal orientation, "
            "tilted 20 degrees, at least 400 kg",
            "FAIL",
            "454 kg / 1000 lbs",
        ),
    ],
)
def test_pst_original_pdf_conditions_flow_through_parser_matcher_and_evaluator(
    monkeypatch,
    pst_pdf_permissible_load_specs,
    query,
    expected_status,
    expected_value,
):
    extracted, qualification_pages = pst_pdf_permissible_load_specs
    load_records = [item for item in extracted if item["attribute"] == "Permissible Load"]
    assert len(load_records) == 10
    assert "454 kg / 1,000 lbs" in qualification_pages[44]
    assert "evenly loaded" in qualification_pages[45].lower()

    result = next(
        item
        for item in _match_real_pst_permissible_load(
            monkeypatch,
            query,
            extracted,
        )
        if item["product"] == "PST 500 Operating Table"
    )

    assert result["status"] == expected_status
    assert result["raw_value"] == expected_value
    assert result["source"]["qualification_sources"][0]["page"] == 44
    assert result["source"]["qualification_sources"][1]["page"] == 45
    if "5.11.2 (1)" in query:
        row_qualification = next(
            item
            for item in result["source"]["qualification_sources"]
            if item["page"] == 46
        )
        assert "must be in the level position" in row_qualification["evidence"]
        assert result["scope"]["chapter"] == "5.11.2 (1)"


def test_pst_original_pdf_shared_and_row_qualifications_stay_attached_to_rows(
    pst_pdf_permissible_load_specs,
):
    extracted, _ = pst_pdf_permissible_load_specs
    loads = [item for item in extracted if item["attribute"] == "Permissible Load"]

    carbon = next(
        item
        for item in loads
        if item["scope"]["chapter"] == "5.11.5"
        and item["scope"]["orientation"] == "Normal"
    )
    chapter_511_2 = next(
        item
        for item in loads
        if item["scope"]["chapter"] == "5.11.2 (1)"
    )
    carbon_qualifications = carbon["source"]["qualification_sources"]
    chapter_qualifications = chapter_511_2["source"]["qualification_sources"]

    assert [item["page"] for item in carbon_qualifications] == [44, 45, 48, 48]
    assert [item["page"] for item in chapter_qualifications] == [44, 45, 46, 46]
    assert "evenly loaded" in carbon["scope"]["conditions"].lower()
    assert "restricted by 100 mm" in carbon["scope"]["conditions"].lower()
    assert "must be inclined by no more than 15" in (
        chapter_511_2["scope"]["conditions"].lower()
    )


def test_pst_missing_shared_condition_evidence_returns_unknown(
    monkeypatch,
    pst_pdf_permissible_load_specs,
):
    extracted, _ = pst_pdf_permissible_load_specs
    carbon = next(
        item
        for item in extracted
        if item["attribute"] == "Permissible Load"
        and item["scope"]["chapter"] == "5.11.5"
        and item["scope"]["orientation"] == "Normal"
    )
    incomplete = {**carbon, "scope": dict(carbon["scope"])}
    incomplete["scope"].pop("conditions")
    incomplete["scope"].pop("restriction")
    incomplete_source = {**carbon["source"], "scope": incomplete["scope"]}
    incomplete_source.pop("qualification_sources")
    incomplete["source"] = incomplete_source
    incomplete["source"]["scope"] = incomplete["scope"]

    result = next(
        item
        for item in _match_permissible_load_requirement(
            monkeypatch,
            "Permissible load for Carbon 1200 normal orientation without "
            "limiting operating table functions at least 150 kg",
            [
                {
                    **incomplete,
                    "product": "PST 500 Operating Table",
                    "document": incomplete_source["document"],
                    "page": incomplete_source["page"],
                    "section": incomplete_source["section"],
                    "scope": incomplete["scope"],
                }
            ],
        )
        if item["product"] == "PST 500 Operating Table"
    )

    assert result["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("position", "expected_status", "expected_value"),
    [
        ("pushed in", "PASS", "225 kg / 496 lbs"),
        ("pulled out", "FAIL", "160 kg / 352 lbs"),
    ],
)
def test_pst_shoulder_chair_load_uses_explicit_head_position_condition(
    monkeypatch,
    position,
    expected_status,
    expected_value,
):
    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Shoulder chair in inverted orientation with "
        f"head positioning extension {position} at least 200 kg",
        [
            _permissible_load_spec(
                "225 kg / 496 lbs",
                configuration="Foot end: Shoulder chair Item [63]",
                orientation="Inverted",
                chapter="5.11.8",
            ),
            _permissible_load_spec(
                "160 kg / 352 lbs",
                configuration="Foot end: Shoulder chair Item [63]",
                orientation="Inverted",
                chapter="5.11.8",
            ),
        ],
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert result["status"] == expected_status
    assert result["raw_value"] == expected_value
    assert result["source"]["qualification_sources"][0]["page"] == 49
    assert position in result["source_evidence"]


def test_pst_truncated_permissible_load_is_not_matchable(monkeypatch, tmp_path):
    raw_value = "160 kg /"
    specification_file = tmp_path / "pst_specifications.json"
    specification_file.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "product_family": "PST 500 Operating Table",
                        "specifications": [
                            _permissible_load_spec(raw_value),
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])
    loaded_specifications = product_matcher._load_processed_specifications()

    results = _match_permissible_load_requirement(
        monkeypatch,
        "Permissible load for Carbon 1200 in normal patient orientation "
        "at least 150 kg",
        loaded_specifications,
    )
    result = next(item for item in results if item["product"] == "PST 500 Operating Table")

    assert loaded_specifications == []
    assert result["status"] == "UNKNOWN"


def test_pst_processed_spec_loader_preserves_configuration_scope(
    monkeypatch,
    tmp_path,
):
    specification = _permissible_load_spec("160 kg / 352 lbs")
    specification_file = tmp_path / "pst_specifications.json"
    specification_file.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "product_family": "PST 500 Operating Table",
                        "specifications": [specification],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(product_matcher, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(product_matcher, "_load_processed_chunks", lambda: [])

    loaded_specifications = product_matcher._load_processed_specifications()

    assert len(loaded_specifications) == 1
    assert loaded_specifications[0]["scope"] == specification["scope"]
