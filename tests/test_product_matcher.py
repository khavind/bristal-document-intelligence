from src.retrieval import product_matcher
from src.retrieval.requirement_parser import parse_requirement
from src.retrieval.product_matcher import (
    match_requirement,
    validate_requirement_evidence,
)


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
