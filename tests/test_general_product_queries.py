import json

import pytest

from src.retrieval.product_matcher import (
    _catalogue_records,
    match_requirement,
)
from src.retrieval.requirement_parser import classify_query_intent


def _record(product, document, product_kind="medical_bed"):
    source = {
        "document": document,
        "page": 1,
        "section": "Product overview",
        "chunk_id": "chunk_1",
        "evidence": product,
    }
    return {
        "product": product,
        "document": document,
        "product_kind": product_kind,
        "identity_reliable": True,
        "sources": [source],
        "chunks": [],
        "specifications": [],
    }


def _chunk(product, document, text, page=1):
    return {
        "product": product,
        "document": document,
        "page": page,
        "section": "Features",
        "chunk_id": f"chunk_{page}",
        "text": text,
    }


def test_query_routing_classifies_catalogue_inventory_feature_and_numeric_intents():
    expected = {
        "Is a hospital bed listed in our catalogue?": "PRODUCT_PRESENCE",
        "“Is a hospital bed listed in our catalogue?”": "PRODUCT_PRESENCE",
        "How many distinct hospital bed models are documented?": "PRODUCT_COUNT",
        "How many beds are in stock today?": "INVENTORY_COUNT",
        "How many units are available for shipment?": "INVENTORY_COUNT",
        "Does this bed have Trendelenburg?": "FEATURE_EXISTENCE",
        "Which beds support at least 200 kg?": "NUMERIC_SPECIFICATION",
    }
    for query, intent in expected.items():
        assert classify_query_intent(query) == intent


def test_hospital_bed_presence_finds_models_and_source_evidence(monkeypatch):
    records = [
        _record("Affinity 4 Birthing Bed", "affinity.pdf"),
        _record("Hillrom 900 Accella bed", "hillrom.pdf"),
        _record("TS 7500 Surgical Table", "surgical.pdf", "surgical_equipment"),
    ]
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records", lambda: records
    )

    for query in (
        "Is a hospital bed listed in our catalogue?",
        "“Is a hospital bed listed in our catalogue?”",
    ):
        results = match_requirement(query)
        assert [result["product"] for result in results] == [
            "Affinity 4 Birthing Bed",
            "Hillrom 900 Accella bed",
        ]
        assert all(result["status"] == "PRESENT" for result in results)
        assert all(result["source_documents"] for result in results)
        assert all(result["sources"][0]["evidence"] for result in results)


def test_specific_catalogue_product_presence_uses_product_identity(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [
            _record("Affinity 4 Birthing Bed", "affinity.pdf"),
            _record("Hillrom 900 Accella bed", "hillrom.pdf"),
        ],
    )
    result = match_requirement("Is the Affinity bed documented in our catalogue?")[0]
    assert result["status"] == "PRESENT"
    assert result["product"] == "Affinity 4 Birthing Bed"
    assert result["document"] == "affinity.pdf"


def test_no_catalogue_match_does_not_claim_company_does_not_sell_product(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_record("Affinity 4 Birthing Bed", "affinity.pdf")],
    )
    result = match_requirement("Is a ventilator listed in our catalogue?")[0]
    assert result["status"] == "NOT_FOUND_IN_CORPUS"
    assert "does not establish" in result["reason"]


def test_catalogue_identity_classification_excludes_surgical_equipment(tmp_path, monkeypatch):
    (tmp_path / "bed_chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                    _chunk(
                        None,
                        "bed",
                        "Affinity 4 Birthing Bed\nA medical bed for patient care.",
                    ),
                    _chunk(None, "bed", "Affinity 4 Birthing Bed", page=2),
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "table_chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                    _chunk(None, "table", "TS 7500 Surgical Table"),
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "generic_chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                    _chunk(None, "generic", "Hospital Bed"),
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pst_chunks.json").write_text(
        json.dumps(
            {
                "chunks": [
                    _chunk(
                        None,
                        "pst",
                        "PST 500 U\nMobile operating table\n"
                        "The operating table can be custom assembled using various parts.",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "bed_specifications.json").write_text(
        json.dumps({"products": [{"product_family": "bed", "specifications": []}]}),
        encoding="utf-8",
    )
    (tmp_path / "table_specifications.json").write_text(
        json.dumps({"products": [{"product_family": "table", "specifications": []}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher.PROCESSED_DIR", tmp_path
    )

    records = _catalogue_records()
    by_document = {record["document"]: record for record in records}
    assert by_document["bed"]["product"] == "Affinity 4 Birthing Bed"
    assert by_document["bed"]["product_kind"] == "medical_bed"
    assert by_document["bed"]["identity_reliable"] is True
    assert by_document["bed"]["sources"][0]["evidence"] == "Affinity 4 Birthing Bed"
    assert by_document["bed"]["sources"][0] == {
        "document": "bed",
        "page": 1,
        "section": "Features",
        "chunk_id": "chunk_1",
        "evidence": "Affinity 4 Birthing Bed",
    }
    assert by_document["table"]["product_kind"] == "surgical_equipment"
    assert by_document["generic"]["identity_reliable"] is False
    assert by_document["pst"]["product"] == "PST 500 U Mobile operating table"
    assert by_document["pst"]["identity_reliable"] is True
    assert by_document["pst"]["sources"][0]["evidence"] == "PST 500 U Mobile operating table"

    count = match_requirement("How many distinct hospital bed models are documented?")[0]
    assert count["status"] == "UNKNOWN"
    assert count["count"] is None


def test_catalogue_model_count_deduplicates_same_identity_across_documents(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [
            _record("Affinity 4 Birthing Bed", "affinity-brochure.pdf"),
            _record("Affinity 4 Birthing Bed", "affinity-manual.pdf"),
            _record("Hillrom 900 Accella bed", "hillrom.pdf"),
        ],
    )
    result = match_requirement("How many distinct hospital bed models are documented?")[0]
    assert result["query_type"] == "PRODUCT_COUNT"
    assert result["count"] == 2
    assert result["models"] == [
        "Affinity 4 Birthing Bed",
        "Hillrom 900 Accella bed",
    ]
    assert result["source_documents"] == [
        "affinity-brochure.pdf",
        "affinity-manual.pdf",
        "hillrom.pdf",
    ]
    assert "not physical inventory" in result["reason"]


def test_general_product_model_count_is_not_mistaken_for_a_named_model(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [
            _record("Affinity 4 Birthing Bed", "affinity.pdf"),
            _record("Hillrom 900 Accella bed", "hillrom.pdf"),
            _record("TS 7500 Surgical Table", "table.pdf", "surgical_equipment"),
        ],
    )
    result = match_requirement("How many distinct product models are documented?")[0]
    assert result["query_type"] == "PRODUCT_COUNT"
    assert result["status"] == "COUNTED"
    assert result["count"] == 3


@pytest.mark.parametrize(
    ("operator", "threshold", "expected"),
    [
        (">=", 250, "PASS"),
        (">", 250, "FAIL"),
        ("<=", 250, "PASS"),
        ("<", 250, "FAIL"),
        ("=", 250, "PASS"),
    ],
)
def test_model_number_does_not_replace_numeric_requirement_value(
    monkeypatch, operator, threshold, expected
):
    document = "hillrom.pdf"
    source = {
        "document": document,
        "page": 3,
        "section": "Technical specifications",
        "chunk_id": "chunk_3",
        "evidence": "Safe working load: 250 kg",
    }
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_record("Hillrom 900 Accella bed", document)],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: [
            {
                "product": "Hillrom 900 Accella bed",
                "document": document,
                "attribute": "Safe working load",
                "raw_value": "250 kg",
                "parsed_value": {"type": "scalar", "value": 250.0, "unit": "kg"},
                "source": source,
            }
        ],
    )

    result = match_requirement(
        f"Hillrom 900 Accella bed safe working load {operator} {threshold} kg"
    )[0]
    assert result["status"] == expected
    assert result["product"] == "Hillrom 900 Accella bed"
    assert result["source"] == source
    assert result["query_plan"]["conditions"][0]["value"] == threshold
    assert result["query_plan"]["conditions"][0]["unit"] == "kg"


def test_inventory_count_is_unknown_without_inventory_connection(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_record("Affinity 4 Birthing Bed", "affinity.pdf")],
    )
    result = match_requirement("How many beds are in stock today?")[0]
    assert result["query_type"] == "INVENTORY_COUNT"
    assert result["status"] == "UNKNOWN"
    assert result["count"] is None
    assert "inventory records are not connected" in result["reason"]


def test_feature_positive_negative_missing_and_negated_evidence(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_record("Affinity 4 Birthing Bed", "affinity.pdf")],
    )

    for text, expected in (
        ("Trendelenburg is available on demand.", "PRESENT"),
        ("Trendelenburg is not available.", "NOT_PRESENT"),
        ("Trendelenburg is not supported.", "NOT_PRESENT"),
        ("The manual mentions Trendelenburg.", "UNKNOWN"),
    ):
        monkeypatch.setattr(
            "src.retrieval.product_matcher._load_processed_chunks",
            lambda text=text: [_chunk("Affinity 4 Birthing Bed", "affinity.pdf", text)],
        )
        result = match_requirement("Does this bed have Trendelenburg?")[0]
        assert result["status"] == expected


def test_conflicting_feature_sources_for_same_model_return_unknown(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_record("Affinity 4 Birthing Bed", "affinity.pdf")],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_chunks",
        lambda: [
            _chunk("Affinity 4 Birthing Bed", "affinity.pdf", "Trendelenburg is supported."),
            _chunk("Affinity 4 Birthing Bed", "affinity.pdf", "Trendelenburg is not supported.", page=2),
        ],
    )

    result = match_requirement("Does this bed have Trendelenburg?")[0]
    assert result["status"] == "UNKNOWN"
    assert "conflicting" in result["reason"].lower()
    assert len(result["sources"]) == 2


def test_hospital_bed_feature_search_excludes_surgical_tables(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [
            _record("Affinity 4 Birthing Bed", "affinity.pdf"),
            _record("TS 7500 Surgical Table", "table.pdf", "surgical_equipment"),
        ],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_chunks",
        lambda: [
            _chunk("Affinity 4 Birthing Bed", "affinity.pdf", "Trendelenburg is supported."),
            _chunk("TS 7500 Surgical Table", "table.pdf", "Trendelenburg is supported."),
        ],
    )

    results = match_requirement("Which beds support Trendelenburg?")
    assert results
    assert all(result["product"] == "Affinity 4 Birthing Bed" for result in results)


def test_numeric_bed_capacity_excludes_weight_accessory_and_surgical_table(monkeypatch):
    bed = _record("Hillrom 900 Accella bed", "bed.pdf")
    table = _record("TS 7500 Surgical Table", "table.pdf", "surgical_equipment")
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records", lambda: [bed, table]
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: [
            {
                "product": bed["product"],
                "document": "bed.pdf",
                "page": 3,
                "attribute": "Safe working load",
                "raw_value": "250 kg",
                "parsed_value": {"type": "scalar", "value": 250, "unit": "kg"},
                "source": {"document": "bed.pdf", "page": 3, "chunk_id": "c3", "evidence": "Safe working load 250 kg"},
            },
            {
                "product": bed["product"],
                "document": "bed.pdf",
                "page": 3,
                "attribute": "Bed weight",
                "raw_value": "220 kg",
                "parsed_value": {"type": "scalar", "value": 220, "unit": "kg"},
                "source": {"document": "bed.pdf", "page": 3, "chunk_id": "c3", "evidence": "Bed weight 220 kg"},
            },
            {
                "product": bed["product"],
                "document": "bed.pdf",
                "page": 3,
                "attribute": "Accessory load",
                "raw_value": "300 kg",
                "parsed_value": {"type": "scalar", "value": 300, "unit": "kg"},
                "source": {"document": "bed.pdf", "page": 3, "chunk_id": "c3", "evidence": "Accessory load 300 kg"},
            },
            {
                "product": table["product"],
                "document": "table.pdf",
                "page": 4,
                "attribute": "Patient load",
                "raw_value": "400 kg",
                "parsed_value": {"type": "scalar", "value": 400, "unit": "kg"},
                "source": {"document": "table.pdf", "page": 4, "chunk_id": "c4", "evidence": "Patient load 400 kg"},
            },
        ],
    )

    results = match_requirement("Which beds support at least 200 kg?")
    assert len(results) == 1
    assert results[0]["status"] == "UNKNOWN"
    assert "attribute" in results[0]["missing_information"]

    explicit = match_requirement(
        "Which beds have a safe working load of at least 200 kg?"
    )
    assert len(explicit) == 1
    assert explicit[0]["status"] == "PASS"
    assert explicit[0]["product"] == "Hillrom 900 Accella bed"
    assert explicit[0]["attribute"] == "Safe working load"


def test_duplicate_numeric_evidence_is_consolidated_and_sources_retained(monkeypatch):
    bed = _record("Hillrom 900 Accella bed", "bed.pdf")
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records", lambda: [bed]
    )
    source = {
        "document": "bed.pdf",
        "page": 3,
        "section": "Specifications",
        "chunk_id": "chunk_3",
        "evidence": "Safe working load 250 kg",
    }
    spec = {
        "product": bed["product"],
        "document": "bed.pdf",
        "page": 3,
        "attribute": "Safe working load",
        "raw_value": "250 kg",
        "parsed_value": {"type": "scalar", "value": 250, "unit": "kg"},
        "source": source,
    }
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: [spec, {**spec, "source": {**source, "chunk_id": "chunk_4"}}],
    )

    results = match_requirement("Safe working load at least 200 kg")
    assert len(results) == 1
    assert results[0]["status"] == "PASS"
    assert len(results[0]["sources"]) == 2


def test_conflicting_numeric_evidence_for_same_attribute_returns_unknown(monkeypatch):
    bed = _record("Hillrom 900 Accella bed", "bed.pdf")
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records", lambda: [bed]
    )
    specifications = []
    for value, page in ((250, 3), (180, 4)):
        source = {
            "document": "bed.pdf",
            "page": page,
            "section": "Specifications",
            "chunk_id": f"chunk_{page}",
            "evidence": f"Safe working load {value} kg",
        }
        specifications.append(
            {
                "product": bed["product"],
                "document": "bed.pdf",
                "page": page,
                "attribute": "Safe working load",
                "raw_value": f"{value} kg",
                "parsed_value": {"type": "scalar", "value": value, "unit": "kg"},
                "source": source,
            }
        )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: specifications,
    )

    result = match_requirement("Safe working load at least 200 kg")[0]
    assert result["status"] == "UNKNOWN"
    assert "different values" in result["reason"]
    assert len(result["sources"]) == 2
