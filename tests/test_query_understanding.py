import json
from pathlib import Path

import pytest

from src.retrieval.corpus_index import CorpusIndex
from src.retrieval.document_retrieval import retrieve_passages
from src.retrieval.embedder import embed_chunks
from src.retrieval.product_matcher import match_requirement
from src.retrieval.query_schema import QueryCondition, QueryPlan
from src.retrieval.query_understanding import understand_query
from src.retrieval.search import search_documents


EVALUATION_CASES = json.loads(
    (Path(__file__).parent / "data" / "query_evaluation.json").read_text(
        encoding="utf-8"
    )
)


def _product_record(product, document):
    return {
        "product": product,
        "document": document,
        "product_kind": "medical_bed",
        "identity_reliable": True,
    }


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What battery backup duration does the model specify?", "DOCUMENT_RETRIEVAL"),
        ("How many different documented models are there?", "PRODUCT_COUNT"),
        ("How many units are on hand?", "INVENTORY_COUNT"),
        ("Is the model documented in the catalogue?", "PRODUCT_PRESENCE"),
    ],
)
def test_understanding_recognizes_supported_paraphrases(question, intent):
    plan = understand_query(question)
    assert isinstance(plan, QueryPlan)
    assert plan.intent == intent
    assert plan.supported


def test_query_plan_parses_multiple_independent_constraints():
    plan = understand_query(
        "A table must have width at least 90 cm and length less than 200 cm"
    )
    assert plan.intent == "NUMERIC_SPECIFICATION"
    assert plan.logical_operator == "AND"
    assert [(item.attribute, item.operator, item.value, item.unit) for item in plan.conditions] == [
        ("Width", ">=", 90.0, "cm"),
        ("Length", "<", 200.0, "cm"),
    ]


def test_query_schema_rejects_operator_without_comparison_value():
    with pytest.raises(ValueError, match="requires a value"):
        QueryCondition("Width", ">=", None, "cm", "width at least")


def test_corpus_index_keeps_raw_and_normalized_facts_and_provenance():
    source = {
        "document": "catalogue.pdf",
        "page": 4,
        "section": "Technical data",
        "chunk_id": "chunk_7",
        "evidence": "Safe working load: 250 kg",
    }
    index = CorpusIndex.build(
        [
            {
                "document": "catalogue.pdf",
                "page": 1,
                "section": "Product",
                "chunk_id": "chunk_1",
                "text": "Model Q7 Hospital Bed",
            }
        ],
        [
            {
                "product": "Model Q7 Hospital Bed",
                "document": "catalogue.pdf",
                "attribute": "Safe working load",
                "raw_value": "250 kg",
                "parsed_value": {"type": "scalar", "value": 250.0, "unit": "kg"},
                "source": source,
                "extraction_method": "line_pair",
                "validation_status": "validated",
            }
        ],
    )
    fact = index.facts[0]
    assert fact.raw_value == "250 kg"
    assert fact.normalized_value == {"type": "scalar", "value": 250.0, "unit": "kg"}
    assert fact.source.to_dict() == source
    assert fact.extraction_method == "line_pair"
    assert index.documents[0].fact_count == 1
    assert index.products[0].document_ids == ("catalogue.pdf",)


def test_corpus_index_infers_document_type_only_from_passage_text():
    index = CorpusIndex.build(
        [
            {
                "document": "arbitrary-name.pdf",
                "page": 1,
                "section": "Instructions for use",
                "chunk_id": "chunk_1",
                "text": (
                    "Model Q7 Hospital Bed\n"
                    "Instructions for use. Read this manual before operating the device.\n"
                    "Manufacturer: Example Health Group"
                ),
            }
        ],
        [],
    )
    document = index.documents[0]
    assert document.document_type == "manual"
    assert document.document_type_evidence[0].document == "arbitrary-name.pdf"
    assert document.document_type_evidence[0].page == 1
    assert index.products[0].manufacturer == "Example Health Group"
    assert index.products[0].manufacturer_evidence[0].evidence == (
        "Manufacturer: Example Health Group"
    )


def test_corpus_index_preserves_conflicting_document_type_evidence():
    index = CorpusIndex.build(
        [
            {
                "document": "mixed.pdf",
                "page": 1,
                "section": "Overview",
                "chunk_id": "chunk_1",
                "text": "Instructions for use",
            },
            {
                "document": "mixed.pdf",
                "page": 2,
                "section": "Specifications",
                "chunk_id": "chunk_2",
                "text": "Technical data and specifications",
            },
        ],
        [],
    )
    document = index.documents[0]
    assert document.document_type is None
    assert set(document.document_type_candidates) == {"manual", "technical_specification"}
    assert {source.page for source in document.document_type_evidence} == {1, 2}


def test_understanding_records_corpus_supported_product_category():
    plan = understand_query(
        "Which hospital beds are listed?",
        [_product_record("Model Alpha Bed", "alpha.pdf")],
    )
    assert plan.product_category == "medical_bed"


def test_retrieval_returns_source_provenance_and_honors_product_filter():
    chunks = [
        {
            "document": "model_a.pdf",
            "page": 4,
            "section": "Warranty",
            "chunk_id": "chunk_4",
            "text": "The warranty period for Model Alpha is two years.",
        },
        {
            "document": "model_b.pdf",
            "page": 7,
            "section": "Warranty",
            "chunk_id": "chunk_7",
            "text": "The warranty period for Model Beta is five years.",
        },
    ]
    records = [
        _product_record("Model Alpha", "model_a.pdf"),
        _product_record("Model Beta", "model_b.pdf"),
    ]
    results = retrieve_passages(
        "What warranty period applies to Model Alpha?",
        chunks,
        records,
        entity_refs=("Model Alpha",),
    )
    assert len(results) == 1
    assert results[0]["document"] == "model_a.pdf"
    assert results[0]["source"] == {
        "document": "model_a.pdf",
        "page": 4,
        "section": "Warranty",
        "chunk_id": "chunk_4",
        "evidence": "The warranty period for Model Alpha is two years.",
    }


def test_search_api_reuses_retriever_and_rejects_unknown_product(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.search._catalogue_records",
        lambda: [_product_record("Model Alpha", "model_a.pdf")],
    )
    monkeypatch.setattr(
        "src.retrieval.search._load_processed_chunks",
        lambda: [
            {
                "document": "model_a.pdf",
                "page": 3,
                "section": "Overview",
                "chunk_id": "chunk_3",
                "text": "Model Alpha has a battery backup feature.",
            },
            {
                "document": "model_b.pdf",
                "page": 5,
                "section": "Overview",
                "chunk_id": "chunk_5",
                "text": "Model Beta has a battery backup feature.",
            },
        ],
    )
    results = search_documents("battery backup", product="Model Alpha")
    assert len(results) == 1
    assert results[0]["document"] == "model_a.pdf"
    assert search_documents("battery backup", product="Unknown model") == []


def test_unknown_named_model_cannot_be_answered_with_another_models_passage(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_product_record("Model Alpha", "model_a.pdf")],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_chunks",
        lambda: [
            {
                "document": "model_a.pdf",
                "page": 4,
                "section": "Warranty",
                "chunk_id": "chunk_4",
                "text": "The Model Alpha warranty period is two years.",
            }
        ],
    )
    result = match_requirement("What warranty applies to Model Zeta?")[0]
    assert result["status"] == "UNKNOWN"
    assert result["sources"] == []
    assert "not present" in result["reason"]


def test_embedding_adapter_requires_explicit_encoder_and_preserves_input():
    class Encoder:
        def encode(self, texts):
            return [[float(index), 1.0] for index, _ in enumerate(texts)]

    original = [{"text": "evidence", "page": 2}]
    embedded = embed_chunks(original, Encoder())
    assert embedded["chunks"][0]["embedding"] == [0.0, 1.0]
    assert "embedding" not in original[0]


def test_query_responses_share_a_machine_readable_envelope(monkeypatch):
    monkeypatch.setattr("src.retrieval.product_matcher._catalogue_records", lambda: [])
    monkeypatch.setattr("src.retrieval.product_matcher._load_processed_chunks", lambda: [])
    result = match_requirement("What does the document say about warranty?")[0]
    assert result["intent"] == "DOCUMENT_RETRIEVAL"
    assert result["execution_status"] == "ABSTAINED"
    assert result["compliance_status"] is None
    assert result["query_plan"]["question"] == result["question"]
    assert result["sources"] == []
    assert "explanation" in result
    assert "validation" in result


def test_compound_query_combines_pass_fail_and_unknown_conservatively(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_product_record("Model Alpha", "model_a.pdf")],
    )

    def evaluate_condition(text):
        if "width" in text.lower():
            status = "PASS"
            attribute = "Width"
            raw_value = "95 cm"
        else:
            status = "UNKNOWN"
            attribute = "Length"
            raw_value = None
        return [
            {
                "product": "Model Alpha",
                "status": status,
                "attribute": attribute,
                "raw_value": raw_value,
                "reason": "Test evidence state.",
                "sources": [],
            }
        ]

    monkeypatch.setattr(
        "src.retrieval.product_matcher._match_technical_requirement",
        evaluate_condition,
    )
    result = match_requirement(
        "The bed width at least 90 cm and length less than 200 cm"
    )[0]
    assert result["status"] == "UNKNOWN"
    assert [condition["status"] for condition in result["conditions"]] == [
        "PASS",
        "UNKNOWN",
    ]
    assert result["intent"] == "NUMERIC_SPECIFICATION"


def test_compound_query_can_fail_and_or_requires_uniform_logic(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_product_record("Model Alpha", "model_a.pdf")],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._match_technical_requirement",
        lambda _text: [
            {
                "product": "Model Alpha",
                "status": "FAIL",
                "sources": [],
                "reason": "Comparable evidence failed.",
            }
        ],
    )
    failed = match_requirement("width at least 90 cm and length less than 200 cm")[0]
    assert failed["status"] == "FAIL"

    mixed_logic = understand_query(
        "width at least 90 cm and length less than 200 cm or height at least 40 cm"
    )
    assert mixed_logic.supported is False
    assert mixed_logic.ambiguities


def test_specification_aggregation_normalizes_units_and_preserves_sources(monkeypatch):
    records = [
        _product_record("Model Alpha", "alpha.pdf"),
        _product_record("Model Beta", "beta.pdf"),
    ]
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: records,
    )
    specifications = [
        {
            "product": record["product"],
            "document": record["document"],
            "attribute": "Safe working load",
            "raw_value": raw_value,
            "parsed_value": {"type": "scalar", "value": value, "unit": unit},
            "source": {
                "document": record["document"],
                "page": 4,
                "section": "Specifications",
                "chunk_id": "chunk_4",
                "evidence": f"Safe working load {raw_value}",
            },
        }
        for record, raw_value, value, unit in (
            (records[0], "250 kg", 250.0, "kg"),
            (records[1], "400 lb", 400.0, "lb"),
        )
    ]
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: specifications,
    )

    result = match_requirement(
        "What is the maximum safe working load across all models?"
    )[0]
    assert result["intent"] == "SPECIFICATION_AGGREGATION"
    assert result["status"] == "AGGREGATED"
    assert result["aggregate_value"] == pytest.approx(250.0)
    assert result["unit"] == "kg"
    assert result["product_count"] == 2
    assert len(result["sources"]) == 2


def test_specification_aggregation_abstains_on_conflicting_per_product_values(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.product_matcher._catalogue_records",
        lambda: [_product_record("Model Alpha", "alpha.pdf")],
    )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_specifications",
        lambda: [
            {
                "product": "Model Alpha",
                "document": "alpha.pdf",
                "attribute": "Safe working load",
                "raw_value": f"{value} kg",
                "parsed_value": {"type": "scalar", "value": value, "unit": "kg"},
                "source": {
                    "document": "alpha.pdf",
                    "page": page,
                    "section": "Specifications",
                    "chunk_id": f"chunk_{page}",
                    "evidence": f"Safe working load {value} kg",
                },
            }
            for value, page in ((250, 4), (180, 5))
        ],
    )
    result = match_requirement(
        "What is the maximum safe working load across all models?"
    )[0]
    assert result["status"] == "UNKNOWN"
    assert "conflicting" in result["reason"].lower()
    assert len(result["sources"]) == 2


@pytest.mark.parametrize("case", EVALUATION_CASES, ids=lambda case: case["expected_intent"])
def test_evaluation_dataset_status_and_intent(case, monkeypatch):
    monkeypatch.setattr("src.retrieval.product_matcher._catalogue_records", lambda: [])
    chunks = []
    if case["expected_evidence_term"]:
        chunks.append(
            {
                "document": "indexed_manual.pdf",
                "page": 2,
                "section": "Warranty",
                "chunk_id": "chunk_2",
                "text": "Indexed model warranty details are specified in this section.",
            }
        )
    monkeypatch.setattr(
        "src.retrieval.product_matcher._load_processed_chunks",
        lambda: chunks,
    )
    result = match_requirement(case["question"])[0]
    assert result["intent"] == case["expected_intent"]
    assert result["status"] == case["expected_status"]
    if case["expected_evidence_term"] is not None:
        assert case["expected_evidence_term"] in result["evidence"].lower()
