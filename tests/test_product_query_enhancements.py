import pytest

from src.retrieval.product_matcher import match_requirement
from src.retrieval.query_understanding import understand_query
from src.retrieval.search import search_documents


def _record(product, document, product_kind="medical_bed"):
    source = {
        "document": document,
        "page": 1,
        "section": "Product overview",
        "chunk_id": f"{document}:1",
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


def _spec(
    record,
    attribute,
    value,
    unit,
    page=3,
    section="Specifications",
    availability=None,
):
    document = record["document"]
    raw_value = f"{value:g} {unit}"
    source = {
        "document": document,
        "page": page,
        "section": section,
        "chunk_id": f"{document}:{page}",
        "evidence": f"{attribute}: {raw_value}",
    }
    return {
        "product": record["product"],
        "document": document,
        "page": page,
        "section": section,
        "chunk_id": source["chunk_id"],
        "attribute": attribute,
        "raw_value": raw_value,
        "availability": availability,
        "parsed_value": {"type": "scalar", "value": value, "unit": unit},
        "source": source,
    }


def _patch_corpus(monkeypatch, records, specifications=(), chunks=()):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records", lambda: records
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: list(specifications),
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_chunks",
        lambda: list(chunks),
    )


def test_numeric_bed_filter_evaluates_every_relevant_model(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    specs = [
        _spec(affinity, "Safe working load", 218, "kg"),
        _spec(hillrom, "Safe working load", 250, "kg"),
    ]
    _patch_corpus(monkeypatch, [affinity, hillrom], specs)

    results = match_requirement(
        "Which beds have a safe working load of at least 200 kg?"
    )

    assert [(result["product"], result["status"]) for result in results] == [
        ("Affinity 4 Birthing Bed", "PASS"),
        ("Hillrom 900 Accella bed", "PASS"),
    ]
    assert [result["raw_value"] for result in results] == ["218 kg", "250 kg"]
    assert all(result["source"]["document"] == result["document"] for result in results)
    assert all(result["source"]["page"] == 3 for result in results)
    assert all(result["source"]["section"] == "Specifications" for result in results)
    assert all(result["source"]["chunk_id"] for result in results)
    assert all(result["source"]["evidence"] for result in results)


def test_numeric_bed_filter_marks_each_nonqualifying_verified_value_fail(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    specs = [
        _spec(affinity, "Safe working load", 218, "kg"),
        _spec(hillrom, "Safe working load", 250, "kg"),
    ]
    _patch_corpus(monkeypatch, [affinity, hillrom], specs)

    results = match_requirement(
        "Which beds have a safe working load of at least 300 kg?"
    )

    assert [(result["product"], result["status"]) for result in results] == [
        ("Affinity 4 Birthing Bed", "FAIL"),
        ("Hillrom 900 Accella bed", "FAIL"),
    ]


def test_missing_attribute_returns_product_scoped_unknown(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    _patch_corpus(
        monkeypatch,
        [affinity, hillrom],
        [_spec(hillrom, "Safe working load", 250, "kg")],
    )

    results = match_requirement(
        "Which beds have a safe working load of at least 200 kg?"
    )

    by_product = {result["product"]: result for result in results}
    assert by_product["Affinity 4 Birthing Bed"]["status"] == "UNKNOWN"
    assert "No specification" in by_product["Affinity 4 Birthing Bed"]["reason"]
    assert by_product["Hillrom 900 Accella bed"]["status"] == "PASS"


def test_numeric_filter_does_not_conflate_bed_weight_and_safe_working_load(
    monkeypatch,
):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    _patch_corpus(
        monkeypatch,
        [affinity],
        [_spec(affinity, "Bed weight", 218, "kg")],
    )

    result = match_requirement(
        "Which beds have a safe working load of at least 200 kg?"
    )[0]

    assert result["product"] == affinity["product"]
    assert result["status"] == "UNKNOWN"
    assert result["sources"] == []


def test_incompatible_unit_evidence_is_unknown_and_retained(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    _patch_corpus(
        monkeypatch,
        [affinity],
        [_spec(affinity, "Safe working load", 218, "cm")],
    )

    result = match_requirement(
        "Which beds have a safe working load of at least 200 kg?"
    )[0]

    assert result["status"] == "UNKNOWN"
    assert "218 cm" in result["evidence"]
    assert result["source"]["page"] == 3
    assert "unit" in result["reason"].lower()


def test_comparison_resolves_two_products_and_returns_each_own_fact(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    _patch_corpus(
        monkeypatch,
        [affinity, hillrom],
        [
            _spec(affinity, "Safe working load", 218, "kg"),
            _spec(hillrom, "Safe working load", 250, "kg", page=4),
        ],
    )

    result = match_requirement(
        "Compare the Affinity and Hillrom beds by safe working load."
    )[0]

    assert result["intent"] == "PRODUCT_COMPARISON"
    assert result["status"] == "COMPARISON"
    assert result["attribute"] == "Safe Working Load"
    assert [row["product"] for row in result["comparison"]] == [
        "Affinity 4 Birthing Bed",
        "Hillrom 900 Accella bed",
    ]
    assert [row["raw_value"] for row in result["comparison"]] == ["218 kg", "250 kg"]
    assert [row["source"]["document"] for row in result["comparison"]] == [
        "affinity.pdf",
        "hillrom.pdf",
    ]
    assert all(row["source"]["page"] in {3, 4} for row in result["comparison"])


def test_comparison_with_unresolved_attribute_or_missing_product_abstains(monkeypatch):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    _patch_corpus(monkeypatch, [affinity, hillrom], [])

    unresolved = match_requirement("Compare the Affinity and Hillrom beds.")[0]
    missing_fact = match_requirement(
        "Compare the Affinity and Hillrom beds by safe working load."
    )[0]
    missing_product = match_requirement(
        "Compare the Affinity and Unknown beds by safe working load."
    )[0]

    assert unresolved["status"] == "UNKNOWN"
    assert unresolved["missing_information"] == ["attribute"]
    assert missing_fact["status"] == "UNKNOWN"
    assert all(row["status"] == "UNKNOWN" for row in missing_fact["comparison"])
    assert missing_product["status"] == "UNKNOWN"


def test_comparison_normalizes_compatible_units_and_rejects_incompatible_units(
    monkeypatch,
):
    affinity = _record("Affinity 4 Birthing Bed", "affinity.pdf")
    hillrom = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    _patch_corpus(
        monkeypatch,
        [affinity, hillrom],
        [
            _spec(affinity, "Safe working load", 218, "kg"),
            _spec(hillrom, "Safe working load", 400, "lb"),
        ],
    )

    converted = match_requirement(
        "Compare the Affinity and Hillrom beds by safe working load."
    )[0]
    assert converted["status"] == "COMPARISON"
    assert converted["comparison"][1]["normalized_unit"] == "kg"
    assert converted["comparison"][1]["normalized_value"]["value"] == pytest.approx(
        400 * 0.45359237
    )

    _patch_corpus(
        monkeypatch,
        [affinity, hillrom],
        [
            _spec(affinity, "Safe working load", 218, "kg"),
            _spec(hillrom, "Safe working load", 90, "cm"),
        ],
    )
    incompatible = match_requirement(
        "Compare the Affinity and Hillrom beds by safe working load."
    )[0]
    assert incompatible["status"] == "UNKNOWN"
    assert incompatible["comparison"][1]["status"] == "UNKNOWN"


def test_comparison_does_not_guess_ambiguous_product_aliases(monkeypatch):
    records = [
        _record("Alpha Model One Bed", "alpha-one.pdf"),
        _record("Alpha Model Two Bed", "alpha-two.pdf"),
        _record("Beta Model Bed", "beta.pdf"),
    ]
    _patch_corpus(monkeypatch, records)

    result = match_requirement(
        "Compare Alpha and Beta beds by safe working load."
    )[0]

    assert result["status"] == "UNKNOWN"
    assert result["comparison"] == []
    assert result["missing_information"] == ["products"]


def test_product_summary_returns_traceable_specifications_and_passages(monkeypatch):
    product = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    specs = [
        _spec(product, "Safe working load", 250, "kg"),
        _spec(product, "Height adjustment", 43.1, "cm", availability="optional"),
    ]
    chunks = [
        {
            "document": "hillrom.pdf",
            "product": product["product"],
            "page": 2,
            "section": "Features and Benefits",
            "chunk_id": "hillrom:2",
            "text": (
                "The bed has a 3-Mode Bed Exit Alarm and an audible brake-off "
                "indicator to support caregiver awareness."
            ),
        }
    ]
    _patch_corpus(monkeypatch, [product], specs, chunks)

    result = match_requirement(
        "Summarize the important features of the Hillrom bed."
    )[0]

    assert result["intent"] == "PRODUCT_SUMMARY"
    assert result["status"] == "SUMMARY"
    assert result["product"] == product["product"]
    assert len(result["summary"]["facts"]) >= 2
    assert any(fact["attribute"] == "Safe working load" for fact in result["summary"]["facts"])
    assert all(fact["source"]["page"] == 3 for fact in result["summary"]["facts"])
    assert all(fact["source"]["document"] == "hillrom.pdf" for fact in result["summary"]["facts"])
    assert result["summary"]["passages"][0]["page"] == 2
    assert "audible brake-off indicator" in result["summary"]["passages"][0]["evidence"]
    assert "hillrom.pdf" in result["answer"]
    assert "(optional)" in result["answer"]


def test_product_summary_excludes_generic_about_passages_and_invalid_pairs(monkeypatch):
    product = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    invalid_specification = {
        "product": product["product"],
        "document": "hillrom.pdf",
        "page": 1,
        "section": "Overview",
        "chunk_id": "hillrom:1",
        "attribute": "Manufacturer overview",
        "raw_value": "A global manufacturer serving healthcare providers.",
        "parsed_value": {
            "type": "categorical",
            "value": "A global manufacturer serving healthcare providers.",
        },
        "source": {
            "document": "hillrom.pdf",
            "page": 1,
            "section": "Overview",
            "chunk_id": "hillrom:1",
            "evidence": "A global manufacturer serving healthcare providers.",
        },
    }
    marker_only_specification = {
        "product": product["product"],
        "document": "hillrom.pdf",
        "page": 3,
        "section": "Features",
        "chunk_id": "hillrom:3",
        "attribute": "Simple Weigh",
        "raw_value": "•",
        "availability": "standard",
        "parsed_value": {"type": "boolean", "value": True},
        "source": {
            "document": "hillrom.pdf",
            "page": 3,
            "section": "Features",
            "chunk_id": "hillrom:3",
            "evidence": "Simple Weigh\n•",
        },
    }
    _patch_corpus(
        monkeypatch,
        [product],
        [invalid_specification, marker_only_specification],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher.retrieve_passages",
        lambda *args, **kwargs: [
            {
                "source": {
                    "document": "hillrom.pdf",
                    "page": 1,
                    "section": "About the manufacturer",
                    "chunk_id": "hillrom:1",
                    "evidence": "A global manufacturer serving healthcare providers.",
                }
            },
            {
                "source": {
                    "document": "hillrom.pdf",
                    "page": 2,
                    "section": "Safety",
                    "chunk_id": "hillrom:2",
                    "evidence": "The bed has an audible brake-off indicator.",
                }
            },
        ],
    )

    result = match_requirement(
        "Summarize the important features of the Hillrom bed."
    )[0]

    assert result["status"] == "SUMMARY"
    assert result["summary"]["facts"] == []
    assert len(result["summary"]["passages"]) == 1
    assert result["summary"]["passages"][0]["source"]["page"] == 2
    assert "global manufacturer" not in result["answer"]
    assert "brake-off indicator" in result["answer"]


def test_product_specific_retrieval_prefers_direct_feature_explanation(monkeypatch):
    product = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    other = _record("Other Hospital Bed", "other.pdf")
    chunks = [
        {
            "document": "hillrom.pdf",
            "product": product["product"],
            "page": 1,
            "section": "Title",
            "chunk_id": "hillrom:1",
            "text": "Hillrom 900 Accella bed. Simple Weigh feature.",
        },
        {
            "document": "hillrom.pdf",
            "product": product["product"],
            "page": 2,
            "section": "Features",
            "chunk_id": "hillrom:2",
            "text": (
                "Simple Weigh improves workflow efficiency with an integrated "
                "scale and BMI calculation, excluding hanging accessories and "
                "IV poles and reducing the steps needed to obtain patient weight."
            ),
        },
        {
            "document": "other.pdf",
            "product": other["product"],
            "page": 3,
            "section": "Features",
            "chunk_id": "other:3",
            "text": "Simple Weigh uses an integrated scale on a different model.",
        },
    ]
    _patch_corpus(monkeypatch, [product, other], chunks=chunks)

    results = match_requirement(
        "What does the Hillrom 900 Accella bed say about Simple Weigh?"
    )

    assert results
    assert all(result["product"] == product["product"] for result in results)
    assert results[0]["page"] == 2
    assert "improves workflow efficiency" in results[0]["evidence"]
    assert len(results) <= 3


def test_search_api_ranks_feature_explanation_over_incidental_mention(monkeypatch):
    product = _record("Hillrom 900 Accella bed", "hillrom.pdf")
    chunks = [
        {
            "document": "hillrom.pdf",
            "page": 1,
            "section": "Title",
            "chunk_id": "hillrom:1",
            "text": "Hillrom 900 Accella bed. Simple Weigh feature.",
        },
        {
            "document": "hillrom.pdf",
            "page": 2,
            "section": "Features",
            "chunk_id": "hillrom:2",
            "text": (
                "Simple Weigh improves workflow efficiency with an integrated "
                "scale and BMI calculation."
            ),
        },
        {
            "document": "hillrom.pdf",
            "page": 3,
            "section": "Technical specifications",
            "chunk_id": "hillrom:3",
            "text": "Simple Weigh (Class III OIML).",
        },
    ]
    monkeypatch.setattr(
        "src.retrieval.search._catalogue_records", lambda: [product]
    )
    monkeypatch.setattr(
        "src.retrieval.search._load_processed_chunks", lambda: chunks
    )

    results = search_documents(
        "Simple Weigh",
        product="Hillrom 900 Accella bed",
    )

    assert results[0]["page"] == 2
    assert "improves workflow efficiency" in results[0]["evidence"]
    assert all(result["document"] == "hillrom.pdf" for result in results)


def test_query_parser_recognizes_reusable_comparison_and_summary_intents():
    records = [
        _record("Affinity 4 Birthing Bed", "affinity.pdf"),
        _record("Hillrom 900 Accella bed", "hillrom.pdf"),
    ]

    comparison = understand_query(
        "Compare the Affinity and Hillrom beds by safe working load.", records
    )
    summary = understand_query(
        "List the main specifications of the Hillrom 900 Accella bed.", records
    )

    assert comparison.intent == "PRODUCT_COMPARISON"
    assert comparison.entity_refs == (
        "Affinity 4 Birthing Bed",
        "Hillrom 900 Accella bed",
    )
    assert comparison.conditions[0].attribute == "Safe Working Load"
    assert comparison.supported
    assert summary.intent == "PRODUCT_SUMMARY"
    assert summary.entity_refs == ("Hillrom 900 Accella bed",)
    assert summary.supported

    offered_features = understand_query(
        "What features does the Hillrom bed offer?", records
    )
    assert offered_features.intent == "PRODUCT_SUMMARY"
