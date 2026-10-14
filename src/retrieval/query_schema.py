"""Validated query and evidence records shared by retrieval and evaluation."""

from dataclasses import asdict, dataclass, field
from typing import Literal


QueryIntent = Literal[
    "PRODUCT_PRESENCE",
    "PRODUCT_COUNT",
    "FEATURE_EXISTENCE",
    "INVENTORY_COUNT",
    "NUMERIC_SPECIFICATION",
    "SPECIFICATION_AGGREGATION",
    "PRODUCT_COMPARISON",
    "PRODUCT_SUMMARY",
    "DOCUMENT_RETRIEVAL",
    "UNSUPPORTED_OR_AMBIGUOUS",
]

ComparisonOperator = Literal[">=", ">", "<=", "<", "="]
VALID_INTENTS = {
    "PRODUCT_PRESENCE",
    "PRODUCT_COUNT",
    "FEATURE_EXISTENCE",
    "INVENTORY_COUNT",
    "NUMERIC_SPECIFICATION",
    "SPECIFICATION_AGGREGATION",
    "PRODUCT_COMPARISON",
    "PRODUCT_SUMMARY",
    "DOCUMENT_RETRIEVAL",
    "UNSUPPORTED_OR_AMBIGUOUS",
}


@dataclass(frozen=True)
class QueryCondition:
    attribute: str | None
    operator: ComparisonOperator | None
    value: float | None
    unit: str | None
    raw_text: str

    def __post_init__(self):
        if self.operator not in {None, ">=", ">", "<=", "<", "="}:
            raise ValueError(f"Unsupported comparison operator: {self.operator}")
        if self.value is not None and self.operator is None:
            raise ValueError("A numeric condition requires a comparison operator.")
        if self.operator is not None and self.value is None:
            raise ValueError("A comparison operator requires a value.")


@dataclass(frozen=True)
class QueryPlan:
    question: str
    intent: QueryIntent
    entity_refs: tuple[str, ...] = ()
    focus_terms: tuple[str, ...] = ()
    product_category: str | None = None
    conditions: tuple[QueryCondition, ...] = ()
    logical_operator: Literal["AND", "OR"] = "AND"
    aggregation: str | None = None
    group_by: tuple[str, ...] = ()
    output_type: str = "evidence"
    time_scope: str | None = None
    ambiguities: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    confidence: float = 0.0
    supported: bool = False

    def __post_init__(self):
        if self.intent not in VALID_INTENTS:
            raise ValueError(f"Unsupported query intent: {self.intent}")
        if not all(isinstance(condition, QueryCondition) for condition in self.conditions):
            raise TypeError("Query conditions must be validated QueryCondition instances.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Query confidence must be between 0 and 1.")
        if self.logical_operator not in {"AND", "OR"}:
            raise ValueError(f"Unsupported logical operator: {self.logical_operator}")
        if self.intent == "NUMERIC_SPECIFICATION" and not self.conditions:
            raise ValueError("A numeric query plan requires at least one condition.")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EvidenceReference:
    document: str | None = None
    page: int | None = None
    section: str | None = None
    chunk_id: str | None = None
    evidence: str | None = None

    @classmethod
    def from_mapping(cls, value):
        value = value if isinstance(value, dict) else {}
        page = value.get("page")
        return cls(
            document=value.get("document"),
            page=page if isinstance(page, int) else None,
            section=value.get("section"),
            chunk_id=value.get("chunk_id"),
            evidence=value.get("evidence"),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EvidenceFact:
    subject: str | None
    attribute: str | None
    raw_value: str | None
    normalized_value: dict | None
    source: EvidenceReference
    extraction_method: str | None = None
    validation_status: str | None = None
    conflict: bool = False
    ambiguity: str | None = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value):
        value = value if isinstance(value, dict) else {}
        source = value.get("source")
        if not isinstance(source, dict):
            source = {
                key: value.get(key)
                for key in ("document", "page", "section", "chunk_id")
                if value.get(key) is not None
            }
        source = dict(source)
        source.setdefault("evidence", value.get("raw_value"))
        known_fields = {
            "product",
            "product_family",
            "attribute",
            "raw_value",
            "parsed_value",
            "source",
            "extraction_method",
            "validation_status",
            "conflict",
            "ambiguity",
        }
        return cls(
            subject=value.get("product") or value.get("product_family"),
            attribute=value.get("attribute"),
            raw_value=value.get("raw_value"),
            normalized_value=value.get("parsed_value"),
            source=EvidenceReference.from_mapping(source),
            extraction_method=value.get("extraction_method"),
            validation_status=value.get("validation_status"),
            conflict=bool(value.get("conflict", False)),
            ambiguity=value.get("ambiguity"),
            metadata={key: item for key, item in value.items() if key not in known_fields},
        )

    def to_dict(self):
        return {
            "subject": self.subject,
            "attribute": self.attribute,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "source": self.source.to_dict(),
            "extraction_method": self.extraction_method,
            "validation_status": self.validation_status,
            "conflict": self.conflict,
            "ambiguity": self.ambiguity,
            "metadata": dict(self.metadata),
        }


def normalize_response(question, plan, result):
    """Add common response fields while retaining the established result keys."""
    result = dict(result)
    sources = result.get("sources")
    if not isinstance(sources, list):
        sources = [result["source"]] if isinstance(result.get("source"), dict) else []
    else:
        sources = [source for source in sources if isinstance(source, dict)]

    status = result.get("status", "UNKNOWN")
    compliance_status = status if plan.intent == "NUMERIC_SPECIFICATION" else None
    execution_status = "ABSTAINED" if status in {"UNKNOWN", "UNSUPPORTED_OR_AMBIGUOUS"} else "COMPLETED"
    answer = result.get("answer")
    if answer is None and plan.intent == "DOCUMENT_RETRIEVAL" and sources:
        answer = "Relevant source passages are returned as evidence; no unsupported summary was generated."
    if answer is None and status == "AGGREGATED":
        answer = (
            f"{result.get('aggregation')} {result.get('attribute')}: "
            f"{result.get('aggregate_value')} {result.get('unit')}."
        )
    if answer is None and plan.intent == "PRODUCT_COUNT" and result.get("count") is not None:
        answer = f"{result['count']} distinct catalogue identities were counted."
    if answer is None and plan.intent == "NUMERIC_SPECIFICATION":
        attribute = result.get("attribute")
        raw_value = result.get("raw_value")
        answer = (
            f"{status}: {attribute} {raw_value}"
            if attribute and raw_value
            else status
        )
    confidence_kind = (
        "retrieval_relevance"
        if plan.intent == "DOCUMENT_RETRIEVAL"
        else "evidence_evaluation"
        if plan.intent in {"NUMERIC_SPECIFICATION", "FEATURE_EXISTENCE"}
        else "source_coverage"
    )

    result.update(
        {
            "question": question,
            "intent": plan.intent,
            "query_plan": plan.to_dict(),
            "execution_status": execution_status,
            "compliance_status": compliance_status,
            "output_type": plan.output_type,
            "answer": answer,
            "entities": {
                "product": result.get("product"),
                "products": result.get("products")
                or result.get("models")
                or [
                    row.get("product")
                    for row in result.get("comparison", [])
                    if row.get("product")
                ],
                "document": result.get("document"),
            },
            "sources": sources,
            "missing_information": list(
                dict.fromkeys(
                    [
                        *plan.missing_information,
                        *result.get("missing_information", []),
                    ]
                )
            ),
            "validation": {
                "interpretation_confidence": plan.confidence,
                "result_confidence": result.get("confidence", 0.0),
                "confidence_kind": confidence_kind,
                "supported": plan.supported,
                "ambiguities": list(plan.ambiguities),
            },
            "explanation": result.get("explanation") or result.get("reason", ""),
        }
    )
    return result
