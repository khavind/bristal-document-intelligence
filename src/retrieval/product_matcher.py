import json
import logging
import math
import re
from pathlib import Path

from src.retrieval.corpus_index import CorpusIndex, product_name_from_metadata
from src.retrieval.document_retrieval import retrieve_passages
from src.retrieval.evaluator import (
    evaluate_condition_compatibility,
    evaluate_requirement,
)
from src.retrieval.query_schema import normalize_response
from src.retrieval.query_understanding import understand_query
from src.retrieval.requirement_parser import (
    attributes_equivalent,
    classify_query as _classify_query,
    extract_search_terms,
    find_attribute,
    normalize_component,
    normalize_query,
    normalize_attribute,
    parse_requirement,
)
from src.retrieval.spec_extractor import MARKERS, is_valid_attribute_value_pair
from src.retrieval.unit_converter import convert, normalize_unit
from src.retrieval.value_parser import parse_value

PROCESSED_DIR = Path("data/processed")
LOGGER = logging.getLogger(__name__)


def classify_query(query):
    """Compatibility export for callers using the former matcher-level helper."""
    return _classify_query(query)


def _normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _empty_result(requirement, status="UNKNOWN", product=None, document=None, page=None, section=None, evidence="", reason="No reliable evidence was found.", confidence=0.0, query_type=None, chunk_id=None, attribute=None, raw_value=None, source=None, sources=None, source_evidence=""):
    return {
        "requirement": requirement,
        "status": status,
        "product": product,
        "document": document,
        "page": page,
        "section": section,
        "evidence": evidence,
        "reason": reason,
        "confidence": confidence,
        "query_type": query_type,
        "chunk_id": chunk_id,
        "attribute": attribute,
        "raw_value": raw_value,
        "source": source,
        "sources": sources or ([source] if source else []),
        "source_evidence": source_evidence,
    }


def _catalogue_records():
    """Build a corpus index from currently processed, source-backed records."""
    return CorpusIndex.build(
        _load_processed_chunks(),
        _load_processed_specifications(),
    ).catalogue_records()


def _find_supporting_excerpt(text, attribute, raw_value):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    normalize = lambda value: re.sub(r"\s+", " ", str(value or "")).casefold()
    attribute_text = normalize(attribute)
    value_text = normalize(raw_value)
    for index, line in enumerate(lines):
        normalized_line = normalize(line)
        if attribute_text and value_text and attribute_text in normalized_line and value_text in normalized_line:
            return line
        if (
            normalized_line == attribute_text
            and index + 1 < len(lines)
            and normalize(lines[index + 1]) == value_text
        ):
            return f"{line}\n{lines[index + 1]}"
    return None


def _load_processed_chunks():
    chunks = []

    if not PROCESSED_DIR.exists():
        return chunks

    for path in sorted(PROCESSED_DIR.glob("*_chunks.json")):
        if path.name.startswith("sample_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as error:
            LOGGER.warning("Skipping unreadable chunk file %s: %s", path, error)
            continue

        for chunk in data.get("chunks", []):
            if not isinstance(chunk, dict):
                continue
            chunk.setdefault("document", path.stem.replace("_chunks", ""))
            chunks.append(chunk)

    return chunks


def _load_processed_specifications():
    specifications = []
    chunks_by_id = {}
    chunks_by_document_page = {}
    for chunk in _load_processed_chunks():
        document = chunk.get("document")
        chunk_id = chunk.get("chunk_id")
        page = chunk.get("page")
        if document and chunk_id:
            chunks_by_id[(document, chunk_id)] = chunk
        if document and page is not None:
            chunks_by_document_page.setdefault((document, page), []).append(chunk)

    if not PROCESSED_DIR.exists():
        return specifications

    for path in sorted(PROCESSED_DIR.glob("*_specifications.json")):
        if path.name.startswith("sample_"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as error:
            LOGGER.warning("Skipping unreadable specification file %s: %s", path, error)
            continue

        for product in data.get("products", []):
            product_name = product_name_from_metadata(product)
            for specification in product.get("specifications", []):
                if not isinstance(specification, dict):
                    continue
                attribute = specification.get("attribute")
                raw_value = specification.get("raw_value")
                parsed_value = specification.get("parsed_value")
                if not is_valid_attribute_value_pair(
                    attribute or "",
                    raw_value or "",
                    parsed_value or parse_value(raw_value or ""),
                ):
                    LOGGER.warning(
                        "Skipping invalid extracted attribute/value pair in %s: %r -> %r",
                        path.name,
                        attribute,
                        raw_value,
                    )
                    continue
                source = specification.get("source") or {}
                source = dict(source) if isinstance(source, dict) else {}
                source.setdefault(
                    "document",
                    path.stem.replace("_specifications", ""),
                )
                source.setdefault("page", specification.get("page"))
                source.setdefault("section", specification.get("section"))
                source.setdefault("chunk_id", specification.get("chunk_id"))
                for field in ("page", "section", "chunk_id"):
                    if source.get(field) is None:
                        source[field] = specification.get(field)
                chunk = chunks_by_id.get(
                    (source.get("document"), source.get("chunk_id"))
                )
                if chunk is None and source.get("page") is not None:
                    same_page = chunks_by_document_page.get(
                        (source.get("document"), source.get("page")), []
                    )
                    if len(same_page) == 1:
                        chunk = same_page[0]
                if chunk is not None:
                    for field in ("page", "section", "chunk_id"):
                        if source.get(field) is None:
                            source[field] = chunk.get(field)
                    excerpt = _find_supporting_excerpt(
                        chunk.get("text"),
                        attribute,
                        raw_value,
                    )
                    if excerpt:
                        source["evidence"] = excerpt
                    elif not source.get("evidence") or source.get("evidence") == raw_value:
                        source["evidence"] = chunk.get("text") or raw_value or ""
                source.setdefault(
                    "evidence",
                    specification.get("evidence") or specification.get("raw_value") or "",
                )
                entry = {
                    "product": product_name,
                    "document": source.get("document"),
                    "page": source.get("page"),
                    "section": source.get("section"),
                    "chunk_id": source.get("chunk_id"),
                    "attribute": attribute,
                    "component": specification.get("component"),
                    "scope": specification.get("scope") or source.get("scope"),
                    "raw_value": raw_value,
                    "parsed_value": parsed_value,
                    "availability": specification.get("status"),
                    "source": source,
                }
                specifications.append(entry)

    return specifications


def _units_compatible(required_unit, candidate_unit):
    if required_unit is None or candidate_unit is None:
        return False

    try:
        req_norm = normalize_unit(required_unit)
        cand_norm = normalize_unit(candidate_unit)
        if req_norm is None or cand_norm is None:
            return False
        convert(1, cand_norm, req_norm)
        return True
    except (TypeError, ValueError):
        return False


def _normalized_candidate_value(parsed_value, target_unit):
    if not isinstance(parsed_value, dict) or not target_unit:
        return None
    if parsed_value.get("type") == "mixed" and isinstance(
        parsed_value.get("parsed_value"), dict
    ):
        parsed_value = parsed_value["parsed_value"]
    value_type = parsed_value.get("type")
    source_unit = parsed_value.get("unit")
    if value_type not in {"scalar", "range"} or not source_unit:
        return None
    try:
        if value_type == "scalar":
            value = convert(
                float(parsed_value["value"]),
                source_unit,
                target_unit,
            )
            return {"type": "scalar", "value": value, "unit": normalize_unit(target_unit)}
        minimum = convert(
            float(parsed_value["min"]),
            source_unit,
            target_unit,
        )
        maximum = convert(
            float(parsed_value["max"]),
            source_unit,
            target_unit,
        )
        return {
            "type": "range",
            "min": minimum,
            "max": maximum,
            "unit": normalize_unit(target_unit),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _attribute_matches(requirement_attribute, candidate_attribute):
    return attributes_equivalent(requirement_attribute, candidate_attribute)


def validate_requirement_evidence(requirement, candidate_attribute, candidate_value, candidate=None):
    """Validate that a candidate evidence item actually matches the requirement attribute and unit type."""
    if requirement is None:
        return False

    req_attribute = requirement.get("attribute") or ""
    req_unit = requirement.get("unit")
    if req_attribute:
        if not _attribute_matches(req_attribute, candidate_attribute):
            return False

    if isinstance(candidate_value, str):
        parsed_value = parse_value(candidate_value)
    elif candidate is not None and isinstance(candidate, dict):
        parsed_value = candidate.get("parsed_value") or parse_value(candidate.get("raw_value") or "")
    else:
        parsed_value = candidate_value

    if not isinstance(parsed_value, dict):
        return False

    if parsed_value.get("type") == "mixed" and isinstance(parsed_value.get("parsed_value"), dict):
        parsed_value = parsed_value["parsed_value"]

    if parsed_value.get("type") in {"unknown", "not_available"}:
        return False

    if req_unit is not None:
        candidate_unit = parsed_value.get("unit")
        if candidate_unit is None:
            return False
        if not _units_compatible(req_unit, candidate_unit):
            return False

    return True


def _feature_terms_for_query(query):
    normalized_attribute = find_attribute(query)
    if normalized_attribute:
        generic_attribute_terms = {"positioning", "adjustment", "feature", "size"}
        terms = set(normalize_attribute(normalized_attribute).split()) - generic_attribute_terms
        return terms

    generic_terms = {
        "support", "supports", "supporting", "available", "present",
        "required", "requires", "bed", "table", "product", "device",
        "system", "does", "have", "has", "is", "are", "this", "that",
        "positioning", "position", "angle", "size", "weight", "height",
        "care", "patient", "operation", "operate", "operating", "hour",
        "hours", "minute", "minutes", "second", "seconds", "day", "days",
        "feature", "adjustment", "adjustments",
    }
    return {
        term for term in extract_search_terms(query)
        if term not in generic_terms and len(term) > 2
    }


def _document_product(document_name):
    if not document_name:
        return None
    for record in _catalogue_records():
        if record["document"] == document_name and record.get("product"):
            return record["product"]
    for specification in _load_processed_specifications():
        if specification.get("document") == document_name and specification.get("product"):
            return specification["product"]
    return None


def _bed_query(query):
    return bool(re.search(r"\b(bed|beds|hospital bed|birthing bed|icu bed)\b", query, re.I))


def _configuration_scope_matches(specification, requested_scope):
    scope = specification.get("scope")
    if not isinstance(scope, dict):
        return False

    configuration = str(scope.get("configuration") or "").casefold()
    for term in requested_scope.get("configuration_terms") or []:
        normalized_term = _normalize_text(term)
        if not re.search(
            rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
            _normalize_text(configuration),
        ):
            return False

    for item_number in requested_scope.get("item_numbers") or []:
        if not re.search(
            rf"\[\s*{int(item_number)}\s*\]",
            configuration,
            re.IGNORECASE,
        ):
            return False

    conditions = _normalize_text(scope.get("conditions"))
    for term in requested_scope.get("position_terms") or []:
        if _normalize_text(term) not in conditions:
            return False

    orientation = requested_scope.get("orientation")
    if orientation and str(scope.get("orientation") or "").casefold() != str(
        orientation
    ).casefold():
        return False

    chapter = requested_scope.get("chapter")
    if chapter and re.sub(
        r"\s+", "", str(scope.get("chapter") or "")
    ).casefold() != re.sub(r"\s+", "", str(chapter)).casefold():
        return False

    return True


def _unknown_configuration_result(query, product_name, attribute, specifications, reason):
    sources = []
    for specification in specifications:
        source = specification.get("source") or {
            "document": specification.get("document"),
            "page": specification.get("page"),
            "section": specification.get("section"),
            "evidence": specification.get("raw_value") or "",
        }
        sources.append(source)
    first_source = sources[0] if sources else {}
    result = _empty_result(
        requirement=query,
        status="UNKNOWN",
        product=product_name,
        document=first_source.get("document"),
        page=first_source.get("page"),
        section=first_source.get("section"),
        evidence="; ".join(source.get("evidence") or "" for source in sources),
        reason=reason,
        query_type="NUMERIC_SPECIFICATION",
        attribute=attribute,
        confidence=0.0,
        source=first_source or None,
        sources=sources,
        source_evidence="; ".join(
            source.get("evidence") or "" for source in sources
        ),
    )
    result["scopes"] = [
        specification.get("scope")
        for specification in specifications
        if specification.get("scope")
    ]
    result["missing_information"] = [
        f"configuration scope for {attribute} for {product_name}"
    ]
    return result


def _query_matches_record(query, record):
    if _bed_query(query) and record["product_kind"] != "medical_bed":
        return False
    if not re.search(r"\b(catalogue|catalog|listed|documented|our products)\b", query, re.I):
        return True

    query_terms = {
        term for term in extract_search_terms(query)
        if term not in {
            "product", "products", "model", "models", "catalogue", "catalog",
            "documented", "listed", "our", "any", "have", "is",
        }
    }
    identity_terms = query_terms - {
        "bed", "beds", "hospital", "birthing", "patient", "icu",
        "table", "tables", "device", "devices", "product",
    }
    if not identity_terms:
        return True
    product_terms = set(extract_search_terms(record.get("product") or ""))
    return bool(product_terms.intersection(identity_terms))


def _catalogue_result(query, query_type, status, reason, records=None, count=None):
    records = records or []
    sources = [source for record in records for source in record.get("sources", [])]
    products = [record.get("product") for record in records if record.get("product")]
    documents = list(
        dict.fromkeys(
            record.get("document")
            for record in records
            if record.get("document")
        )
    )
    primary_source = sources[0] if sources else None
    return {
        "requirement": normalize_query(query),
        "query_type": query_type,
        "status": status,
        "result_type": query_type,
        "product": products[0] if len(products) == 1 else None,
        "products": products,
        "models": products,
        "count": count,
        "document": documents[0] if len(documents) == 1 else None,
        "page": primary_source.get("page") if primary_source else None,
        "section": primary_source.get("section") if primary_source else None,
        "chunk_id": primary_source.get("chunk_id") if primary_source else None,
        "evidence": "\n---\n".join(
            dict.fromkeys(source.get("evidence", "") for source in sources if source.get("evidence"))
        ),
        "source": primary_source,
        "sources": sources,
        "source_documents": documents,
        "source_evidence": "\n---\n".join(
            dict.fromkeys(source.get("evidence", "") for source in sources if source.get("evidence"))
        ),
        "reason": reason,
        "confidence": 0.8 if records else 0.0,
        "attribute": None,
        "raw_value": None,
    }


def _match_product_presence(query):
    records = _catalogue_records()
    bed_query = _bed_query(query)
    matching = [
        record for record in records
        if record["identity_reliable"]
        and (not bed_query or record["product_kind"] == "medical_bed")
        and _query_matches_record(query, record)
    ]
    if matching:
        return [
            _catalogue_result(
                query,
                "PRODUCT_PRESENCE",
                "PRESENT",
                "The identified product is documented in the currently processed catalogue corpus.",
                [record],
            )
            for record in matching
        ]

    if not records or any(not record["identity_reliable"] for record in records):
        return [
            _catalogue_result(
                query,
                "PRODUCT_PRESENCE",
                "UNKNOWN",
                "The processed corpus does not contain enough reliable product identity metadata to confirm catalogue presence.",
            )
        ]
    return [
        _catalogue_result(
            query,
            "PRODUCT_PRESENCE",
            "NOT_FOUND_IN_CORPUS",
            "No supporting product was found in the searched documents. This does not establish that the company does not sell the product.",
        )
    ]


def _match_product_count(query):
    records = _catalogue_records()
    if _bed_query(query):
        records = [record for record in records if record["product_kind"] == "medical_bed"]
    if not records or any(not record["identity_reliable"] for record in records):
        return [
            _catalogue_result(
                query,
                "PRODUCT_COUNT",
                "UNKNOWN",
                "Product identities could not all be deduplicated reliably in the processed corpus.",
            )
        ]

    distinct = {}
    for record in records:
        key = re.sub(r"[^a-z0-9]+", " ", record["product"].lower()).strip()
        current = distinct.get(key)
        if current is None:
            distinct[key] = record
        else:
            current["sources"].extend(
                source for source in record["sources"] if source not in current["sources"]
            )
    result = _catalogue_result(
        query,
        "PRODUCT_COUNT",
        "COUNTED",
        f"Count of distinct product models identified in the currently processed corpus ({len(distinct)}). This is a catalogue-document count, not physical inventory.",
        list(distinct.values()),
        count=len(distinct),
    )
    result["products"] = list(dict.fromkeys(record["product"] for record in distinct.values()))
    result["models"] = result["products"]
    result["source_documents"] = list(
        dict.fromkeys(
            source["document"]
            for record in distinct.values()
            for source in record["sources"]
            if source.get("document")
        )
    )
    return [result]


def _match_inventory_count(query):
    return [
        _catalogue_result(
            query,
            "INVENTORY_COUNT",
            "UNKNOWN",
            "Current inventory records are not connected, so stock quantity cannot be verified from catalogue documents.",
        )
    ]


def _localize_evidence_text(text, feature_terms=None):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        return ""

    if feature_terms:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        best_sentence = ""
        best_score = -1
        for sentence in sentences:
            sentence_text = re.sub(r"\s+", " ", sentence).strip()
            if not sentence_text:
                continue
            score = 0
            for term in feature_terms:
                if term and term.lower() in sentence_text.lower():
                    score += 3
            if re.search(r"\d|°|on demand|enable|supports?|available|position|angle|backup|weight|load|function", sentence_text, re.I):
                score += 1
            if score > best_score:
                best_sentence = sentence_text
                best_score = score
        if best_sentence:
            return best_sentence

    return text[:300]


def _is_navigation_reference(text):
    if not text:
        return False

    normalized = _normalize_text(text)
    if not normalized:
        return False

    heading_patterns = [
        r"\b\d+(?:\.\d+)+\s*(?:[-:.]\s*)?\b(?:trendelenburg|underwater|icu|support|feature|position)\b",
        r"\b(?:trendelenburg|underwater|icu|support|feature|position)\b\s*[.]{2,}\s*\d+",
        r"\b\d+\s*[-:]\s*\b(?:trendelenburg|underwater|icu|support|feature|position)\b",
        r"\b(?:trendelenburg|underwater|icu|support|feature|position)\b\s*(?:\.|:|;)?\s*$",
    ]
    return any(re.search(pattern, normalized) for pattern in heading_patterns)


def _is_technical_feature_evidence(text, feature_terms=None):
    if not text:
        return False

    normalized = _normalize_text(text)
    if not normalized:
        return False
    if _is_navigation_reference(normalized):
        return False

    if feature_terms is None:
        feature_terms = _feature_terms_for_query(text)
    feature_terms = {term.lower() for term in feature_terms if term and len(term) > 2}
    if not feature_terms:
        return bool(re.search(r"\b(?:support|available|present|enabled|feature|function)\b", normalized))

    for term in sorted(feature_terms, key=len, reverse=True):
        if term not in normalized:
            continue

        if re.search(rf"\b{re.escape(term)}\b.*(?:\.{2,}|-+)\s*\d+(?:\.\d+)?", normalized) and not re.search(rf"\b{re.escape(term)}\b.*(?::|°|on demand|achieve|enable|supports?|available|function|position|angle|backup|load)", normalized):
            return False

        if re.search(rf"\b{re.escape(term)}\b.*(?::|°|on demand|achieve|enable|supports?|available|function|position|angle|backup|load)", normalized):
            return True

        if re.search(rf"\b{re.escape(term)}\b.*\d+\s*(?:°|%|kg|g|lb|lbs|cm|mm|m|v|mv|kv|hz|khz|mhz|ghz)", normalized):
            return True

        idx = normalized.find(term)
        window = normalized[max(0, idx - 80): min(len(normalized), idx + 120)]
        if re.search(r"(?:°|on demand|achieve|enable|supports?|available|function|position|angle|backup|weight|load)\b|\d+\s*(?:°|%|kg|g|lb|lbs|cm|mm|m|v|mv|kv|hz|khz|mhz|ghz)", window):
            return True

    return False


def _feature_negation_matches(text, feature_terms=None):
    if not text:
        return False

    text = _normalize_text(text)
    if not text:
        return False

    if feature_terms is None:
        feature_terms = _feature_terms_for_query(text)
    features = {term.lower() for term in feature_terms if term and len(term) > 2}
    if not features:
        features = set(re.findall(r"[a-z0-9]+", text))

    negations = [
        "not supported", "not suitable", "not available", "unsupported",
        "without", "absent", "lacks", "lack", "do not use", "not for",
        "do not support", "does not support", "doesn't support",
        "not recommended for", "prohibited", "not allowed"
    ]

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_lower = sentence.lower()
        if not any(neg in sentence_lower for neg in negations):
            continue
        if features and any(feature in sentence_lower for feature in features):
            return True
    return False


def _positive_feature_evidence(text, feature_terms):
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    affirmative = [
        sentence
        for sentence in sentences
        if sentence.strip() and not _feature_negation_matches(sentence, feature_terms)
    ]
    return _is_technical_feature_evidence("\n".join(affirmative), feature_terms)


def _token_overlap(query, text):
    query_terms = set(extract_search_terms(query))
    text_terms = set(extract_search_terms(text))
    if not query_terms:
        return 0
    return len(query_terms.intersection(text_terms))


def _mark_conflicting_results(results, positive_status, negative_status, reason, group_by_attribute=False):
    grouped = {}
    for result in results:
        identity = result.get("product") or result.get("document") or id(result)
        if group_by_attribute:
            identity = (identity, normalize_attribute(result.get("attribute")))
        grouped.setdefault(identity, []).append(result)

    resolved = []
    for product_results in grouped.values():
        statuses = {result["status"] for result in product_results}
        conflicting_unknown = any(
            result["status"] == "UNKNOWN"
            and "conflicting" in result.get("reason", "").lower()
            for result in product_results
        )
        if (
            positive_status in statuses and negative_status in statuses
        ) or (
            conflicting_unknown
            and (positive_status in statuses or negative_status in statuses)
        ):
            combined = dict(product_results[0])
            combined["status"] = "UNKNOWN"
            combined["reason"] = reason
            combined["confidence"] = 0.0
            combined["sources"] = [
                source
                for result in product_results
                for source in result.get("sources", [])
            ]
            combined["source"] = (
                combined["sources"][0] if combined["sources"] else None
            )
            combined["source_evidence"] = "\n---\n".join(
                dict.fromkeys(
                    result["source_evidence"]
                    for result in product_results
                    if result.get("source_evidence")
                )
            )
            combined["evidence"] = " | ".join(
                dict.fromkeys(
                    str(result["evidence"])
                    for result in product_results
                    if result.get("evidence")
                )
            )
            resolved.append(combined)
        else:
            resolved.extend(product_results)

    return resolved


def _consolidate_numeric_results(results):
    grouped = {}
    for result in results:
        identity = (
            result.get("product") or result.get("document"),
            normalize_attribute(result.get("attribute")),
        )
        grouped.setdefault(identity, []).append(result)

    consolidated = []
    for product_results in grouped.values():
        comparable_values = [
            result.get("normalized_value")
            for result in product_results
            if result.get("normalized_value") is not None
        ]
        if len(comparable_values) == len(product_results) and comparable_values:
            first = comparable_values[0]
            if first.get("type") == "scalar":
                conflict = any(
                    value.get("type") != "scalar"
                    or value.get("unit") != first.get("unit")
                    or not math.isclose(
                        value.get("value", math.nan),
                        first.get("value", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    for value in comparable_values[1:]
                )
            elif first.get("type") == "range":
                conflict = any(
                    value.get("type") != "range"
                    or value.get("unit") != first.get("unit")
                    or not math.isclose(
                        value.get("min", math.nan),
                        first.get("min", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    or not math.isclose(
                        value.get("max", math.nan),
                        first.get("max", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    for value in comparable_values[1:]
                )
            else:
                conflict = any(value != first for value in comparable_values[1:])
        else:
            distinct_values = {
                re.sub(r"\s+", " ", str(result.get("raw_value") or "")).strip().lower()
                for result in product_results
            }
            conflict = len(distinct_values) > 1
        if conflict:
            combined = dict(product_results[0])
            combined["status"] = "UNKNOWN"
            combined["reason"] = (
                "Conflicting sources report different values for this product attribute; "
                "no source-precedence policy is configured."
            )
            combined["confidence"] = 0.0
            combined["sources"] = [
                source
                for result in product_results
                for source in result.get("sources", [])
            ]
            combined["source"] = combined["sources"][0] if combined["sources"] else None
            combined["source_evidence"] = "\n---\n".join(
                dict.fromkeys(
                    result.get("source_evidence", "")
                    for result in product_results
                    if result.get("source_evidence")
                )
            )
            combined["evidence"] = " | ".join(
                dict.fromkeys(result.get("evidence", "") for result in product_results)
            )
            consolidated.append(combined)
            continue

        combined = dict(product_results[0])
        combined["sources"] = [
            source
            for result in product_results
            for source in result.get("sources", [])
        ]
        combined["source"] = combined["sources"][0] if combined["sources"] else None
        combined["source_evidence"] = "\n---\n".join(
            dict.fromkeys(
                result.get("source_evidence", "")
                for result in product_results
                if result.get("source_evidence")
            )
        )
        consolidated.append(combined)
    return consolidated


def _match_technical_requirement(query, plan=None, catalogue_records=None):
    query = normalize_query(query)
    requirement = parse_requirement(query)
    records = catalogue_records if catalogue_records is not None else _catalogue_records()
    specifications = _load_processed_specifications()
    supplementary_records = {}
    indexed_by_document = {
        record.get("document"): record
        for record in records
        if record.get("document")
    }
    for specification in specifications:
        document = specification.get("document")
        product = specification.get("product")
        indexed_record = indexed_by_document.get(document)
        if (
            document
            and product
            and product != document
            and (
                indexed_record is None
                or not indexed_record.get("identity_reliable")
                or not indexed_record.get("product")
            )
        ):
            key = (document, str(product).casefold())
            supplementary_records.setdefault(
                key,
                {
                    "product": str(product),
                    "document": document,
                    "product_kind": "other",
                    "identity_reliable": True,
                    "sources": [specification.get("source") or {}],
                },
            )
    records = [
        record
        for record in records
        if record.get("document") not in {
            supplementary["document"]
            for supplementary in supplementary_records.values()
        }
    ]
    records.extend(supplementary_records.values())
    if plan is not None and plan.entity_refs:
        requested_names = {name.casefold() for name in plan.entity_refs}
        records = [
            record
            for record in records
            if (record.get("product") or "").casefold() in requested_names
        ]
    if plan is not None and plan.product_category:
        records = [
            record
            for record in records
            if record.get("product_kind") == plan.product_category
        ]

    grouped_records = {}
    for record in records:
        if not record.get("identity_reliable", True) or not record.get("product"):
            continue
        key = re.sub(r"[^a-z0-9]+", " ", record["product"].lower()).strip()
        grouped_records.setdefault(key, []).append(record)

    specifications_by_document = {}
    for specification in specifications:
        specifications_by_document.setdefault(
            specification.get("document"), []
        ).append(specification)

    results = []
    product_documents = {}
    for record_group in grouped_records.values():
        record = record_group[0]
        product_name = record["product"]
        documents = {item.get("document") for item in record_group}
        product_documents[product_name] = documents
        product_specs = [
            specification
            for document in documents
            for specification in specifications_by_document.get(document, [])
            if attributes_equivalent(
                requirement.get("attribute"),
                specification.get("attribute"),
            )
        ]
        attribute_specs = product_specs
        has_configured_values = any(
            isinstance(specification.get("scope"), dict)
            and specification["scope"].get("configuration")
            for specification in attribute_specs
        )
        requested_scope = requirement.get("configuration_scope")
        if (
            attribute_specs
            and requested_scope
            and requested_scope.get("configuration_terms")
            and not has_configured_values
        ):
            results.append(
                _unknown_configuration_result(
                    query,
                    product_name,
                    requirement.get("attribute"),
                    attribute_specs,
                    "The source evidence does not associate this attribute with "
                    "the requested configuration.",
                )
            )
            continue
        requires_configuration = (
            attributes_equivalent(
                requirement.get("attribute"),
                "Permissible Load",
            )
            or has_configured_values
        )
        if requires_configuration and attribute_specs:
            scoped_specs = [
                specification
                for specification in attribute_specs
                if isinstance(specification.get("scope"), dict)
                and specification["scope"].get("configuration")
            ]
            if requested_scope and requested_scope.get("configuration_ambiguous"):
                results.append(
                    _unknown_configuration_result(
                        query,
                        product_name,
                        requirement.get("attribute"),
                        attribute_specs,
                        "The request names more than one distinct table configuration.",
                    )
                )
                continue
            if not requested_scope:
                results.append(
                    _unknown_configuration_result(
                        query,
                        product_name,
                        requirement.get("attribute"),
                        attribute_specs,
                        f"The {requirement.get('attribute')} is "
                        "configuration-dependent, but "
                        "the requested configuration is unspecified.",
                    )
                )
                continue
            matching_scope_specs = [
                specification
                for specification in scoped_specs
                if _configuration_scope_matches(
                    specification,
                    requested_scope,
                )
            ]
            if not matching_scope_specs:
                results.append(
                    _unknown_configuration_result(
                        query,
                        product_name,
                        requirement.get("attribute"),
                        attribute_specs,
                        f"No {requirement.get('attribute')} evidence matches the explicitly "
                        "requested configuration and orientation.",
                    )
                )
                continue
            if len(matching_scope_specs) > 1:
                results.append(
                    _unknown_configuration_result(
                        query,
                        product_name,
                        requirement.get("attribute"),
                        matching_scope_specs,
                        "The requested scope matches more than one "
                        f"configuration-specific {requirement.get('attribute')} value; "
                        "provide a more specific configuration or orientation.",
                    )
                )
                continue
            product_specs = matching_scope_specs
        requested_component = requirement.get("component")
        component_specs = [
            specification
            for specification in attribute_specs
            if specification.get("component")
        ]
        if requested_component:
            product_specs = [
                specification
                for specification in attribute_specs
                if normalize_component(specification.get("component"))
                == normalize_component(requested_component)
            ]
            if not product_specs:
                available_specs = attribute_specs
                available_sources = [
                    specification.get("source")
                    or {
                        "document": specification.get("document"),
                        "page": specification.get("page"),
                        "section": specification.get("section"),
                        "evidence": specification.get("raw_value") or "",
                    }
                    for specification in available_specs
                ]
                first_source = available_sources[0] if available_sources else {}
                missing = _empty_result(
                    requirement=query,
                    status="UNKNOWN",
                    product=product_name,
                    document=first_source.get("document"),
                    page=first_source.get("page"),
                    section=first_source.get("section"),
                    evidence="; ".join(
                        source.get("evidence") or ""
                        for source in available_sources
                    ),
                    reason=(
                        f"No specification explicitly associated with "
                        f"{requested_component} was found for "
                        f"{requirement.get('attribute')}."
                    ),
                    query_type="NUMERIC_SPECIFICATION",
                    attribute=requirement.get("attribute"),
                    confidence=0.0,
                    source=first_source or None,
                    sources=available_sources,
                    source_evidence="; ".join(
                        source.get("evidence") or ""
                        for source in available_sources
                    ),
                )
                missing["missing_information"] = [
                    f"{requested_component} {requirement.get('attribute')} for {product_name}"
                ]
                results.append(missing)
                continue
        elif component_specs:
            available_sources = [
                specification.get("source")
                or {
                    "document": specification.get("document"),
                    "page": specification.get("page"),
                    "section": specification.get("section"),
                    "evidence": specification.get("raw_value") or "",
                }
                for specification in component_specs
            ]
            first_source = available_sources[0]
            missing = _empty_result(
                requirement=query,
                status="UNKNOWN",
                product=product_name,
                document=first_source.get("document"),
                page=first_source.get("page"),
                section=first_source.get("section"),
                evidence="; ".join(
                    source.get("evidence") or ""
                    for source in available_sources
                ),
                reason=(
                    f"{requirement.get('attribute')} evidence has "
                    f"component-specific values, but the requested component "
                    f"is unspecified."
                ),
                query_type="NUMERIC_SPECIFICATION",
                attribute=requirement.get("attribute"),
                confidence=0.0,
                source=first_source,
                sources=available_sources,
                source_evidence="; ".join(
                    source.get("evidence") or ""
                    for source in available_sources
                ),
            )
            missing["missing_information"] = [
                f"component for {requirement.get('attribute')} for {product_name}"
            ]
            results.append(missing)
            continue
        if not product_specs:
            missing = _empty_result(
                requirement=query,
                status="UNKNOWN",
                product=product_name,
                reason=(
                    f"No specification directly equivalent to "
                    f"{requirement.get('attribute') or 'the requested attribute'} "
                    "was found for this indexed product."
                ),
                query_type="NUMERIC_SPECIFICATION",
                attribute=requirement.get("attribute"),
                confidence=0.0,
            )
            missing["missing_information"] = [
                f"{requirement.get('attribute') or 'requested attribute'} for {product_name}"
            ]
            results.append(missing)
            continue

        for specification in product_specs:
            attribute = specification.get("attribute") or ""
            raw_value = specification.get("raw_value") or ""
            parsed_value = specification.get("parsed_value")
            candidate_spec = {
                "attribute": attribute,
                "component": specification.get("component"),
                "raw_value": raw_value,
                "parsed_value": parsed_value,
                "unit": parsed_value.get("unit") if isinstance(parsed_value, dict) else None,
                "document": specification.get("document"),
                "page": specification.get("page"),
                "section": specification.get("section")
                or (specification.get("source") or {}).get("section"),
                "chunk_id": specification.get("chunk_id")
                or (specification.get("source") or {}).get("chunk_id"),
                "scope": specification.get("scope")
                or (specification.get("source") or {}).get("scope"),
                "source": specification.get("source"),
                "evidence": raw_value,
            }
            condition_status, condition_reason = evaluate_condition_compatibility(
                requirement,
                candidate_spec,
            )
            status = evaluate_requirement(
                requirement,
                raw_value,
                candidate_attribute=attribute,
                candidate=candidate_spec,
            )
            candidate_unit = candidate_spec["unit"]
            if condition_status != "PASS":
                reason = condition_reason
            elif status in {"PASS", "FAIL"}:
                reason = "Comparable evidence was converted to the required unit and evaluated against the requested operator."
            elif requirement.get("unit") is None or candidate_unit is None:
                reason = "A compatible unit is missing, so this numeric comparison cannot be evaluated."
            elif not _units_compatible(requirement["unit"], candidate_unit):
                reason = (
                    f"The source unit {candidate_unit} is incompatible with the "
                    f"required unit {requirement['unit']}."
                )
            else:
                reason = "The extracted value or evidence type is insufficient for a reliable numeric comparison."

            source = specification.get("source") or {
                "document": specification.get("document"),
                "page": specification.get("page"),
                "section": specification.get("section"),
                "chunk_id": specification.get("chunk_id"),
                "evidence": raw_value,
            }
            score = _token_overlap(query, f"{attribute} {raw_value}")
            result = _empty_result(
                requirement=query,
                status=status,
                product=product_name,
                document=specification.get("document") or source.get("document"),
                page=specification.get("page") or source.get("page"),
                section=specification.get("section") or source.get("section"),
                evidence=raw_value,
                reason=reason,
                confidence=0.6 + min(score, 3) * 0.1 if status in {"PASS", "FAIL"} else 0.0,
                query_type="NUMERIC_SPECIFICATION",
                attribute=attribute,
                raw_value=raw_value,
                chunk_id=specification.get("chunk_id") or source.get("chunk_id"),
                source=source,
                sources=[source],
                source_evidence=source.get("evidence") or raw_value,
            )
            result["normalized_value"] = _normalized_candidate_value(
                parsed_value if isinstance(parsed_value, dict) else parse_value(raw_value),
                requirement.get("unit"),
            )
            if specification.get("scope"):
                result["scope"] = specification["scope"]
            results.append(result)

    results = _consolidate_numeric_results(results)
    results = _mark_conflicting_results(
        results,
        "PASS",
        "FAIL",
        "Conflicting source values produce UNKNOWN; no source-resolution policy is configured.",
        group_by_attribute=True,
    )

    if attributes_equivalent(requirement.get("attribute"), "Battery Backup"):
        chunks = _load_processed_chunks()
        for result in results:
            if result.get("status") != "UNKNOWN":
                continue
            documents = product_documents.get(result.get("product"), set())
            related_evidence = _find_battery_duration_evidence(chunks, documents)
            if related_evidence:
                result["related_evidence"] = related_evidence
                result["reason"] = (
                    "The source contains a qualified battery-operation duration, "
                    "but its conditions or measurement basis are not established "
                    "as equivalent to the requested battery-backup duration."
                )
                result_sources = list(result.get("sources", []))
                result_sources.extend(
                    source
                    for source in related_evidence
                    if source not in result_sources
                )
                result["sources"] = result_sources
                result["source_evidence"] = "\n---\n".join(
                    source["evidence"] for source in related_evidence
                )
            else:
                result["reason"] = (
                    "No comparable source-backed battery runtime duration was found."
                )

    if results:
        return results

    return [
        _empty_result(
            requirement=query,
            status="UNKNOWN",
            product=None,
            document=None,
            page=None,
            section=None,
            evidence="",
            reason="No comparable specification was found in the processed documents for this requirement.",
            confidence=0.0,
            query_type="NUMERIC_SPECIFICATION",
        )
    ]


def _find_battery_duration_evidence(chunks, documents):
    duration_pattern = re.compile(
        r"\b(?:\d+(?:[.,]\d+)?|one|several|few)\s+"
        r"(?:hours?|days?|minutes?)\b",
        re.IGNORECASE,
    )
    battery_pattern = re.compile(r"\b(?:battery|batteries)\b", re.IGNORECASE)
    function_use_pattern = re.compile(
        r"\b(?:functions?|operation)\b.{0,120}\b"
        r"(?:used|guaranteed|operated|available|lasts?)\b|"
        r"\b(?:used|guaranteed|operated|available|lasts?)\b.{0,120}\b"
        r"(?:electrical\s+)?(?:functions?|operation)\b",
        re.IGNORECASE,
    )
    evidence = []
    for chunk in chunks:
        if chunk.get("document") not in documents:
            continue
        text = re.sub(r"\s+", " ", str(chunk.get("text") or ""))
        for match in duration_pattern.finditer(text):
            start = max(0, match.start() - 220)
            end = min(len(text), match.end() + 220)
            excerpt = text[start:end].strip()
            if (
                not battery_pattern.search(excerpt)
                or not function_use_pattern.search(excerpt)
                or re.search(
                    r"\b(?:interval|charging|recharging|switch(?:es)? off|shutdown)\b",
                    excerpt,
                    re.IGNORECASE,
                )
            ):
                continue
            source = {
                "document": chunk.get("document"),
                "page": chunk.get("page"),
                "section": chunk.get("section"),
                "chunk_id": chunk.get("chunk_id"),
                "evidence": excerpt,
            }
            if source not in evidence:
                evidence.append(source)
    return evidence


def _match_presence_or_capability(query):
    query = normalize_query(query)
    chunks = _load_processed_chunks()
    records_by_document = {
        record["document"]: record for record in _catalogue_records()
    }
    requested_terms = set(extract_search_terms(query))
    feature_terms = _feature_terms_for_query(query)
    if not feature_terms:
        feature_terms = requested_terms
    feature_query_tokens = {
        token
        for term in feature_terms
        for token in extract_search_terms(term)
    }
    best_chunks = []
    for chunk in chunks:
        text = chunk.get("text", "") or ""
        record = records_by_document.get(chunk.get("document"))
        if _bed_query(query) and record is not None:
            category_supported = record.get("product_kind") == "medical_bed"
            chunk_subject_supports_category = bool(
                chunk.get("product")
                and re.search(r"\bbed\b", text, re.IGNORECASE)
            )
            if not category_supported and not chunk_subject_supports_category:
                continue
        query_record = record or {"product": "", "product_kind": "other"}
        if (
            _bed_query(query)
            and chunk.get("product")
            and re.search(r"\bbed\b", text, re.IGNORECASE)
            and query_record.get("product_kind") != "medical_bed"
        ):
            query_record = {**query_record, "product_kind": "medical_bed"}
        if not _query_matches_record(query, query_record):
            continue
        text_terms = set(extract_search_terms(text))
        overlap = feature_query_tokens & text_terms
        if overlap:
            best_chunks.append((len(overlap), chunk))
    best_chunks.sort(key=lambda item: item[0], reverse=True)
    best_chunks = [chunk for _, chunk in best_chunks]

    if not best_chunks:
        return [
            _empty_result(
                requirement=query,
                status="UNKNOWN",
                product=None,
                document=None,
                page=None,
                section=None,
                evidence="",
                reason="The processed documents do not contain enough evidence to support the claim.",
                confidence=0.0,
                query_type="FEATURE_EXISTENCE",
            )
        ]

    results = []
    for chunk in best_chunks:
        text = chunk.get("text", "") or ""
        evidence = _localize_evidence_text(text, feature_terms or requested_terms)
        positive = _positive_feature_evidence(text, feature_terms or requested_terms)
        negative = _feature_negation_matches(text, feature_terms or requested_terms)

        if positive and negative:
            status = "UNKNOWN"
            reason = "This source contains conflicting positive and negative evidence for the requested feature."
            confidence = 0.0
        elif positive:
            status = "PRESENT"
            reason = "The document contains explicit technical evidence that supports the requested feature."
            confidence = 0.8
        elif negative:
            status = "NOT_PRESENT"
            reason = "The document contains explicit negative evidence tied to the requested feature."
            confidence = 0.7
        else:
            status = "UNKNOWN"
            reason = "The candidate mention is weak, navigational, or not tied to a concrete technical capability."
            confidence = 0.2

        product_name = (
            chunk.get("product")
            or (records_by_document.get(chunk.get("document")) or {}).get("product")
            or _document_product(chunk.get("document"))
            or chunk.get("document")
            or "UNKNOWN"
        )
        source = {
            "document": chunk.get("document"),
            "page": chunk.get("page"),
            "section": chunk.get("section"),
            "chunk_id": chunk.get("chunk_id"),
            "evidence": text,
        }
        results.append(
            _empty_result(
                requirement=query,
                status=status,
                product=product_name,
                document=chunk.get("document"),
                page=chunk.get("page"),
                section=chunk.get("section"),
                evidence=evidence,
                reason=reason,
                confidence=confidence,
                query_type="FEATURE_EXISTENCE",
                chunk_id=chunk.get("chunk_id"),
                source=source,
                sources=[source],
                source_evidence=text,
            )
        )

    results = _mark_conflicting_results(
        results,
        "PRESENT",
        "NOT_PRESENT",
        "Conflicting positive and negative source evidence produces UNKNOWN; no source-resolution policy is configured.",
    )

    conflicts = [
        result for result in results
        if result["status"] == "UNKNOWN" and "conflicting" in result["reason"].lower()
    ]
    if conflicts:
        return results

    consolidated = {}
    for result in results:
        identity = result.get("product") or result.get("document")
        current = consolidated.get(identity)
        if current is None:
            consolidated[identity] = dict(result)
            continue
        current["sources"].extend(
            source for source in result.get("sources", []) if source not in current["sources"]
        )
        current["source_evidence"] = "\n---\n".join(
            dict.fromkeys(
                part
                for part in (
                    current.get("source_evidence", ""),
                    result.get("source_evidence", ""),
                )
                if part
            )
        )
        current["evidence"] = " | ".join(
            dict.fromkeys((current.get("evidence", ""), result.get("evidence", "")))
        )
    results = list(consolidated.values())

    strong_positive = [result for result in results if result["status"] == "PRESENT"]
    if strong_positive:
        return strong_positive

    strong_negative = [result for result in results if result["status"] == "NOT_PRESENT"]
    if strong_negative:
        return strong_negative

    return [
        _empty_result(
            requirement=query,
            status="UNKNOWN",
            product=results[0]["product"] if results else None,
            document=results[0]["document"] if results else None,
            page=results[0]["page"] if results else None,
            section=results[0]["section"] if results else None,
            evidence=results[0]["evidence"] if results else "",
            reason="No strong positive or negative evidence was found after filtering weak mentions and TOC-style references.",
            confidence=0.0,
            query_type="FEATURE_EXISTENCE",
            chunk_id=results[0]["chunk_id"] if results else None,
        )
    ]


def _unknown_for_query(query, plan, reason, missing_information=()):
    result = _empty_result(
        requirement=query,
        status="UNKNOWN",
        reason=reason,
        query_type=plan.intent,
        confidence=0.0,
    ) | {"missing_information": list(missing_information)}
    if plan.intent == "PRODUCT_COMPARISON":
        result["comparison"] = []
        result["products"] = []
        result["attribute"] = (
            plan.conditions[0].attribute if plan.conditions else None
        )
    elif plan.intent == "PRODUCT_SUMMARY":
        result["summary"] = {"facts": [], "passages": [], "groups": {}}
    return result


def _restrict_to_entities(results, plan):
    if plan.ambiguities:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "; ".join(plan.ambiguities),
                plan.missing_information,
            )
        ]
    if not plan.entity_refs:
        return results

    requested = set(plan.entity_refs)
    filtered = []
    for result in results:
        result_products = set(result.get("products") or result.get("models") or [])
        if result.get("product"):
            result_products.add(result["product"])
        if result_products & requested:
            filtered.append(result)

    if filtered:
        return filtered
    return [
        _unknown_for_query(
            plan.question,
            plan,
            "No evidence for the explicitly referenced product was found in the processed corpus.",
            plan.missing_information,
        )
    ]


def _restrict_to_category(results, plan):
    if not plan.product_category:
        return results
    product_categories = {
        record.get("product"): record.get("product_kind")
        for record in _catalogue_records()
        if record.get("product")
    }
    return [
        result
        for result in results
        if product_categories.get(result.get("product")) == plan.product_category
    ]


def _combine_condition_statuses(statuses, logical_operator):
    if not statuses:
        return "UNKNOWN"
    known = set(statuses)
    if logical_operator == "AND":
        if "FAIL" in known:
            return "FAIL"
        if known == {"PASS"}:
            return "PASS"
        return "UNKNOWN"
    if "PASS" in known:
        return "PASS"
    if known == {"FAIL"}:
        return "FAIL"
    return "UNKNOWN"


def _match_multiple_conditions(plan):
    if not plan.supported or plan.ambiguities:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "; ".join(plan.ambiguities) or "The compound query could not be interpreted safely.",
                plan.missing_information,
            )
        ]
    if any(condition.attribute is None for condition in plan.conditions):
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "At least one numeric condition is missing an attribute, so candidate values cannot be compared safely.",
                plan.missing_information,
            )
        ]

    condition_results = []
    for condition in plan.conditions:
        results = _match_technical_requirement(condition.raw_text)
        condition_results.append(
            _restrict_to_category(_restrict_to_entities(results, plan), plan)
        )

    products = list(plan.entity_refs)
    if not products:
        products = list(
            dict.fromkeys(
                result.get("product")
                for results in condition_results
                for result in results
                if result.get("product")
            )
        )
    if not products:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "No product had comparable evidence for the compound requirement.",
                plan.missing_information,
            )
        ]

    combined = []
    for product in products:
        per_condition = []
        sources = []
        for condition, results in zip(plan.conditions, condition_results):
            matching = [result for result in results if result.get("product") == product]
            status = _combine_condition_statuses(
                [result.get("status", "UNKNOWN") for result in matching],
                "OR",
            )
            per_condition.append(
                {
                    "attribute": condition.attribute,
                    "operator": condition.operator,
                    "required_value": condition.value,
                    "required_unit": condition.unit,
                    "requirement": condition.raw_text,
                    "status": status,
                    "evidence": [
                        {
                            "attribute": result.get("attribute"),
                            "raw_value": result.get("raw_value"),
                            "status": result.get("status"),
                            "sources": result.get("sources", []),
                            "reason": result.get("reason"),
                        }
                        for result in matching
                    ],
                }
            )
            for result in matching:
                for source in result.get("sources", []):
                    if source not in sources:
                        sources.append(source)

        combined.append(
            {
                **_empty_result(
                    requirement=plan.question,
                    status=_combine_condition_statuses(
                        [item["status"] for item in per_condition],
                        plan.logical_operator,
                    ),
                    product=product,
                    document=sources[0].get("document") if sources else None,
                    page=sources[0].get("page") if sources else None,
                    section=sources[0].get("section") if sources else None,
                    chunk_id=sources[0].get("chunk_id") if sources else None,
                    evidence="\n---\n".join(
                        source.get("evidence", "") for source in sources if source.get("evidence")
                    ),
                    reason="Each constraint is evaluated independently; missing or conflicting evidence remains UNKNOWN.",
                    confidence=0.0,
                    query_type=plan.intent,
                    sources=sources,
                ),
                "conditions": per_condition,
                "source_documents": list(
                    dict.fromkeys(source.get("document") for source in sources if source.get("document"))
                ),
            }
        )
    return combined


def _match_document_question(plan, catalogue_records):
    chunks = _load_processed_chunks()
    passages = retrieve_passages(
        plan.question,
        chunks,
        catalogue_records=catalogue_records,
        entity_refs=plan.entity_refs,
        product_category=plan.product_category,
        focus_terms=plan.focus_terms,
    )
    if not passages:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "No sufficiently relevant, source-backed passage was found; the system did not infer an answer.",
            )
        ]
    results = []
    for passage in passages:
        results.append(
            {
                **_empty_result(
                    requirement=plan.question,
                    status="EVIDENCE_RETRIEVED",
                    product=passage.get("product"),
                    document=passage.get("document"),
                    page=passage.get("page"),
                    section=passage.get("section"),
                    chunk_id=passage.get("chunk_id"),
                    evidence=passage.get("evidence") or "",
                    reason="Passages are ranked by lexical relevance. Retrieval is evidence discovery, not proof of a claim.",
                    confidence=min(0.99, passage["score"] / (passage["score"] + 1.0)),
                    query_type=plan.intent,
                    source=passage.get("source"),
                    sources=passage.get("sources"),
                    source_evidence=passage.get("source_evidence") or "",
                ),
                "relevance_score": passage["score"],
                "answer": (
                    f"{_localize_evidence_text(passage.get('evidence') or '', plan.focus_terms)} "
                    f"[{passage.get('document')}, page {passage.get('page')}, "
                    f"chunk {passage.get('chunk_id')}]."
                ),
            }
        )
    return results


def _comparison_source(specification):
    source = specification.get("source")
    if isinstance(source, dict):
        return source
    return {
        "document": specification.get("document"),
        "page": specification.get("page"),
        "section": specification.get("section"),
        "chunk_id": specification.get("chunk_id"),
        "evidence": specification.get("raw_value"),
    }


def _match_product_comparison(plan, catalogue_records):
    target_attribute = plan.conditions[0].attribute
    record_groups = {}
    requested_names = {name.casefold() for name in plan.entity_refs}
    for record in catalogue_records:
        name = record.get("product")
        if (
            not name
            or not record.get("identity_reliable")
            or name.casefold() not in requested_names
        ):
            continue
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        record_groups.setdefault(key, []).append(record)

    specifications = _load_processed_specifications()
    rows = []
    all_sources = []
    target_unit = None
    prepared = []
    for name, records in record_groups.items():
        documents = {record.get("document") for record in records}
        facts = [
            specification
            for specification in specifications
            if specification.get("document") in documents
            and attributes_equivalent(
                target_attribute,
                specification.get("attribute"),
            )
        ]
        for fact in facts:
            parsed = fact.get("parsed_value")
            if not isinstance(parsed, dict):
                parsed = parse_value(fact.get("raw_value") or "")
            if parsed.get("type") == "mixed" and isinstance(parsed.get("parsed_value"), dict):
                parsed = parsed["parsed_value"]
            unit = parsed.get("unit")
            if target_unit is None and unit:
                target_unit = normalize_unit(unit)
            prepared.append((records[0]["product"], name, facts, fact, parsed))

    facts_by_product = {}
    for product, key, facts, fact, parsed in prepared:
        facts_by_product.setdefault(key, (product, facts))

    for key, records in record_groups.items():
        product = records[0]["product"]
        facts = facts_by_product.get(key, (product, []))[1]
        if not facts:
            rows.append(
                {
                    "product": product,
                    "attribute": target_attribute,
                    "raw_value": None,
                    "value": None,
                    "unit": None,
                    "normalized_value": None,
                    "normalized_unit": target_unit,
                    "status": "UNKNOWN",
                    "reason": f"No {target_attribute} evidence was found for this product.",
                    "source": None,
                    "sources": [],
                }
            )
            continue

        values = []
        sources = []
        for fact in facts:
            parsed = fact.get("parsed_value")
            if not isinstance(parsed, dict):
                parsed = parse_value(fact.get("raw_value") or "")
            if parsed.get("type") == "mixed" and isinstance(parsed.get("parsed_value"), dict):
                parsed = parsed["parsed_value"]
            normalized = _normalized_candidate_value(parsed, target_unit)
            source = _comparison_source(fact)
            if source not in sources:
                sources.append(source)
            values.append((fact, parsed, normalized))

        normalized_values = [
            value for _, _, value in values if value is not None
        ]
        first_fact, first_parsed, first_normalized = values[0]
        conflict = False
        if len(values) != len(normalized_values):
            conflict = True
        elif normalized_values:
            first = normalized_values[0]
            if first.get("type") == "scalar":
                conflict = any(
                    value.get("type") != "scalar"
                    or value.get("unit") != first.get("unit")
                    or not math.isclose(
                        value.get("value", math.nan),
                        first.get("value", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    for value in normalized_values[1:]
                )
            elif first.get("type") == "range":
                conflict = any(
                    value.get("type") != "range"
                    or value.get("unit") != first.get("unit")
                    or not math.isclose(
                        value.get("min", math.nan),
                        first.get("min", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    or not math.isclose(
                        value.get("max", math.nan),
                        first.get("max", math.nan),
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    )
                    for value in normalized_values[1:]
                )
            else:
                conflict = any(value != first for value in normalized_values[1:])

        unit = first_parsed.get("unit")
        row_status = "UNKNOWN" if conflict or first_normalized is None else "FOUND"
        if conflict:
            reason = "Conflicting or incomparable source values prevent a reliable comparison."
        elif first_normalized is None:
            reason = "The extracted value is missing or uses a unit that cannot be normalized."
        else:
            reason = "The value is supported by the indexed source evidence."
        row = {
            "product": product,
            "attribute": target_attribute,
            "raw_value": first_fact.get("raw_value"),
            "value": first_parsed.get("value")
            if first_parsed.get("type") == "scalar"
            else first_fact.get("raw_value"),
            "unit": unit,
            "normalized_value": first_normalized,
            "normalized_unit": target_unit,
            "status": row_status,
            "reason": reason,
            "source": sources[0] if sources else None,
            "sources": sources,
        }
        rows.append(row)
        all_sources.extend(source for source in sources if source not in all_sources)

    overall_status = (
        "COMPARISON"
        if rows and all(row["status"] == "FOUND" for row in rows)
        else "UNKNOWN"
    )
    answer_lines = [f"Comparison by {target_attribute}:"]
    for row in rows:
        if row["status"] == "FOUND":
            value = row["raw_value"]
            source = row["source"] or {}
            citation = ", ".join(
                part
                for part in (
                    source.get("document"),
                    f"page {source['page']}" if source.get("page") is not None else None,
                    f"chunk {source['chunk_id']}" if source.get("chunk_id") else None,
                )
                if part
            )
            answer_lines.append(f"- {row['product']}: {value} ({citation})")
        else:
            answer_lines.append(f"- {row['product']}: UNKNOWN — {row['reason']}")

    result = _empty_result(
        requirement=plan.question,
        status=overall_status,
        product=None,
        reason=(
            "Each resolved product is compared only using evidence for the requested attribute."
            if overall_status == "COMPARISON"
            else "The comparison is incomplete because at least one requested value is missing, conflicting, or incomparable."
        ),
        confidence=0.9 if overall_status == "COMPARISON" else 0.0,
        query_type=plan.intent,
        attribute=target_attribute,
        sources=all_sources,
        source_evidence="\n---\n".join(
            str(source.get("evidence") or "")
            for source in all_sources
            if source.get("evidence")
        ),
    )
    result.update(
        {
            "comparison": rows,
            "products": [row["product"] for row in rows],
            "answer": "\n".join(answer_lines),
        }
    )
    return [result]


def _summary_category(attribute):
    text = (attribute or "").lower()
    for category, pattern in (
        ("Dimensions", r"width|length|height|depth|dimension"),
        ("Load and weight", r"load|capacity|weight"),
        ("Positioning", r"position|angle|tilt|trendelenburg"),
        ("Controls", r"control|pendant|switch|cpr"),
        ("Safety", r"safety|alarm|brake|protection|exit"),
        ("Connectivity", r"connect|wireless|network|communication"),
    ):
        if re.search(pattern, text):
            return category
    return "Other specifications"


def _is_generic_summary_passage(passage):
    source = passage.get("source") or {}
    section = _normalize_text(source.get("section"))
    if section.startswith("about"):
        return True
    text = str(source.get("evidence") or "").strip()
    first_line = _normalize_text(text.splitlines()[0] if text else "")
    return bool(
        re.match(
            r"^about\s+(?:the\s+)?(?:company|manufacturer|organization|organisation|us)\b",
            first_line,
        )
    )


def _match_product_summary(plan, catalogue_records):
    product_name = plan.entity_refs[0]
    records = [
        record
        for record in catalogue_records
        if record.get("product") == product_name and record.get("identity_reliable")
    ]
    documents = {record.get("document") for record in records}
    facts = []
    sources = []
    for specification in _load_processed_specifications():
        if specification.get("document") not in documents:
            continue
        attribute = specification.get("attribute")
        raw_value = specification.get("raw_value")
        parsed = specification.get("parsed_value")
        if not attribute or not raw_value:
            continue
        if raw_value.strip() in MARKERS:
            continue
        if isinstance(parsed, dict) and parsed.get("type") in {"unknown", "not_available"}:
            continue
        if not is_valid_attribute_value_pair(attribute, raw_value, parsed or parse_value(raw_value)):
            continue
        source = _comparison_source(specification)
        fact = {
            "category": _summary_category(attribute),
            "attribute": attribute,
            "value": raw_value,
            "availability": specification.get("availability"),
            "source": source,
        }
        facts.append(fact)
        if source not in sources:
            sources.append(source)

    passages = retrieve_passages(
        " ".join(plan.focus_terms) or "features",
        _load_processed_chunks(),
        catalogue_records=catalogue_records,
        entity_refs=(product_name,),
        limit=2,
        focus_terms=plan.focus_terms,
    )
    passages = [
        passage
        for passage in passages
        if not _is_generic_summary_passage(passage)
    ]
    for passage in passages:
        source = passage.get("source")
        if isinstance(source, dict) and source not in sources:
            sources.append(source)

    if not facts and not passages:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                f"No source-backed feature or specification evidence was found for {product_name}.",
            )
        ]

    grouped = {}
    for fact in facts[:16]:
        grouped.setdefault(fact["category"], []).append(fact)
    lines = [f"Documented features and specifications for {product_name}:"]
    for category, category_facts in grouped.items():
        lines.append(f"{category}:")
        for fact in category_facts:
            source = fact["source"]
            citation_parts = [
                source.get("document"),
                f"page {source['page']}" if source.get("page") is not None else None,
                f"chunk {source['chunk_id']}" if source.get("chunk_id") else None,
            ]
            citation = ", ".join(part for part in citation_parts if part)
            qualifier = (
                f" ({fact['availability']})"
                if fact.get("availability")
                else ""
            )
            lines.append(
                f"- {fact['attribute']}: {fact['value']}{qualifier} [{citation}]"
            )
    for passage in passages:
        source = passage.get("source") or {}
        if not source.get("evidence"):
            continue
        citation = ", ".join(
            part
            for part in (
                source.get("document"),
                f"page {source['page']}" if source.get("page") is not None else None,
                f"chunk {source['chunk_id']}" if source.get("chunk_id") else None,
            )
            if part
        )
        lines.append(f"Source passage [{citation}]: {source['evidence']}")

    result = _empty_result(
        requirement=plan.question,
        status="SUMMARY",
        product=product_name,
        reason="The summary contains only extracted specifications and retrieved source passages for the resolved product.",
        confidence=0.7,
        query_type=plan.intent,
        sources=sources,
        source_evidence="\n---\n".join(
            str(source.get("evidence") or "")
            for source in sources
            if source.get("evidence")
        ),
    )
    result.update(
        {
            "summary": {"facts": facts[:16], "passages": passages, "groups": grouped},
            "answer": "\n".join(lines),
        }
    )
    return [result]


def _match_specification_aggregation(plan):
    condition = plan.conditions[0]
    target_attribute = condition.attribute
    records_by_document = {
        record["document"]: record for record in _catalogue_records()
    }
    values_by_product = {}
    all_sources = []
    unresolved = []
    target_unit = None

    for specification in _load_processed_specifications():
        attribute = specification.get("attribute")
        if not attributes_equivalent(target_attribute, attribute):
            continue
        parsed_value = specification.get("parsed_value")
        if not isinstance(parsed_value, dict):
            parsed_value = parse_value(specification.get("raw_value") or "")
        if parsed_value.get("type") != "scalar":
            unresolved.append("A matching specification is not a single scalar value.")
            continue
        unit = parsed_value.get("unit")
        value = parsed_value.get("value")
        if unit is None or value is None:
            unresolved.append("A matching specification is missing a numeric unit or value.")
            continue
        normalized_unit = normalize_unit(unit)
        if target_unit is None:
            target_unit = normalized_unit
        try:
            converted_value = convert(float(value), normalized_unit, target_unit)
        except (TypeError, ValueError):
            unresolved.append("Matching specifications use incompatible or unsupported units.")
            continue

        record = records_by_document.get(specification.get("document"), {})
        if (
            plan.product_category
            and record.get("product_kind") != plan.product_category
        ):
            continue
        product = (
            record.get("product")
            or specification.get("product")
            or specification.get("document")
        )
        product_key = re.sub(r"[^a-z0-9]+", " ", str(product).lower()).strip()
        current = values_by_product.get(product_key)
        if current is None:
            values_by_product[product_key] = {
                "product": product,
                "value": converted_value,
                "unit": target_unit,
                "sources": [],
            }
            current = values_by_product[product_key]
        else:
            try:
                converted = convert(float(value), normalized_unit, current["unit"])
            except (TypeError, ValueError):
                unresolved.append("Matching specifications use incompatible or unsupported units.")
                converted = None
            if converted is not None and not math.isclose(
                converted,
                current["value"],
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                unresolved.append(
                    f"Conflicting values were found for {product} and {target_attribute}."
                )

        source = specification.get("source")
        if not isinstance(source, dict):
            source = {
                "document": specification.get("document"),
                "page": specification.get("page"),
                "section": specification.get("section"),
                "chunk_id": specification.get("chunk_id"),
                "evidence": specification.get("raw_value"),
            }
        if source not in all_sources:
            all_sources.append(source)
        if source not in current["sources"]:
            current["sources"].append(source)

    if unresolved or not values_by_product:
        return [
            _empty_result(
                requirement=plan.question,
                status="UNKNOWN",
                reason=(
                    "; ".join(dict.fromkeys(unresolved))
                    if unresolved
                    else "No scalar specifications with comparable units were found for the requested attribute."
                ),
                confidence=0.0,
                query_type=plan.intent,
                attribute=target_attribute,
                sources=all_sources,
                source_evidence="\n---\n".join(
                    str(source.get("evidence") or "")
                    for source in all_sources
                    if source.get("evidence")
                ),
            )
        ]

    values = list(values_by_product.values())
    identified_products = {
        record.get("product")
        for record in records_by_document.values()
        if record.get("identity_reliable")
        and record.get("product")
        and (
            plan.product_category is None
            or record.get("product_kind") == plan.product_category
        )
    }
    valued_products = {entry["product"] for entry in values}
    missing_products = identified_products - valued_products
    if missing_products:
        return [
            _empty_result(
                requirement=plan.question,
                status="UNKNOWN",
                reason=(
                    "The aggregate may be incomplete because comparable evidence is missing "
                    f"for indexed products: {', '.join(sorted(missing_products))}."
                ),
                confidence=0.0,
                query_type=plan.intent,
                attribute=target_attribute,
                sources=all_sources,
                source_evidence="\n---\n".join(
                    str(source.get("evidence") or "")
                    for source in all_sources
                    if source.get("evidence")
                ),
            )
        ]

    numbers = [entry["value"] for entry in values]
    if plan.aggregation == "maximum":
        aggregate_value = max(numbers)
    elif plan.aggregation == "minimum":
        aggregate_value = min(numbers)
    elif plan.aggregation == "average":
        aggregate_value = sum(numbers) / len(numbers)
    elif plan.aggregation == "sum":
        aggregate_value = sum(numbers)
    else:
        return [
            _unknown_for_query(
                plan.question,
                plan,
                "The requested aggregation operation is not supported.",
            )
        ]

    return [
        {
            **_empty_result(
                requirement=plan.question,
                status="AGGREGATED",
                document=all_sources[0].get("document") if all_sources else None,
                page=all_sources[0].get("page") if all_sources else None,
                section=all_sources[0].get("section") if all_sources else None,
                chunk_id=all_sources[0].get("chunk_id") if all_sources else None,
                evidence="\n---\n".join(
                    str(source.get("evidence") or "")
                    for source in all_sources
                    if source.get("evidence")
                ),
                reason="The aggregate uses source-backed scalar values with compatible units and no unresolved per-product conflicts.",
                confidence=0.8,
                query_type=plan.intent,
                attribute=target_attribute,
                sources=all_sources,
                source_evidence="\n---\n".join(
                    str(source.get("evidence") or "")
                    for source in all_sources
                    if source.get("evidence")
                ),
            ),
            "aggregation": plan.aggregation,
            "aggregate_value": aggregate_value,
            "unit": values[0]["unit"],
            "product_count": len(values),
            "products": [entry["product"] for entry in values],
        }
    ]


def match_requirement(query):
    """Interpret a question, execute supported local retrieval, and retain legacy keys."""
    original_question = str(query or "")
    normalized = normalize_query(original_question)
    if not normalized:
        plan = understand_query("")
        return [
            normalize_response(
                original_question,
                plan,
                _unknown_for_query(
                    "",
                    plan,
                    "A blank question cannot be evaluated.",
                ),
            )
        ]

    catalogue_records = _catalogue_records()
    plan = understand_query(normalized, catalogue_records)

    if plan.ambiguities:
        raw_results = [
            _unknown_for_query(
                normalized,
                plan,
                "; ".join(plan.ambiguities),
                plan.missing_information,
            )
        ]
    elif plan.intent == "SPECIFICATION_AGGREGATION":
        raw_results = _match_specification_aggregation(plan)
    elif plan.intent == "NUMERIC_SPECIFICATION" and any(
        condition.attribute is None for condition in plan.conditions
    ):
        raw_results = [
            _unknown_for_query(
                normalized,
                plan,
                "The numeric threshold does not specify which attribute it constrains; no product specification was treated as interchangeable.",
                plan.missing_information,
            )
        ]
    elif plan.intent == "NUMERIC_SPECIFICATION" and len(plan.conditions) > 1:
        raw_results = _match_multiple_conditions(plan)
    elif plan.intent == "NUMERIC_SPECIFICATION":
        raw_results = _match_technical_requirement(
            normalized,
            plan=plan,
            catalogue_records=catalogue_records,
        )
    elif plan.intent == "FEATURE_EXISTENCE":
        raw_results = _match_presence_or_capability(normalized)
    elif plan.intent == "PRODUCT_PRESENCE":
        raw_results = _match_product_presence(normalized)
    elif plan.intent == "PRODUCT_COUNT":
        raw_results = _match_product_count(normalized)
    elif plan.intent == "INVENTORY_COUNT":
        raw_results = _match_inventory_count(normalized)
    elif plan.intent == "PRODUCT_COMPARISON":
        raw_results = _match_product_comparison(plan, catalogue_records)
    elif plan.intent == "PRODUCT_SUMMARY":
        raw_results = _match_product_summary(plan, catalogue_records)
    elif plan.intent == "DOCUMENT_RETRIEVAL":
        raw_results = _match_document_question(plan, catalogue_records)
    else:
        raw_results = [
            _unknown_for_query(
                normalized,
                plan,
                "The query is unsupported or ambiguous; no answer was inferred.",
                plan.missing_information,
            )
        ]

    if plan.intent in {"NUMERIC_SPECIFICATION", "FEATURE_EXISTENCE"} and plan.entity_refs:
        raw_results = _restrict_to_entities(raw_results, plan)
    return [
        normalize_response(original_question, plan, result)
        for result in raw_results
    ]


def _print_query_results(query, results, output_fn=None):
    output_fn = output_fn or print
    output_fn("\n" + "=" * 72)
    output_fn(f"Original query: {query}")
    if not results:
        output_fn("Query type: UNKNOWN")
        output_fn("Status: UNKNOWN")
        output_fn("Answer/evidence: No results were returned.")
        output_fn("=" * 72)
        return

    for result in results:
        output_fn(f"Query type: {result.get('query_type') or result.get('intent') or 'UNKNOWN'}")
        output_fn(f"Status: {result.get('status', 'UNKNOWN')}")
        if result.get("product"):
            output_fn(f"Product/model: {result['product']}")
        if result.get("products"):
            output_fn(f"Products/models: {', '.join(map(str, result['products']))}")
        if result.get("count") is not None:
            output_fn(f"Distinct catalogue models: {result['count']}")

        answer = result.get("answer")
        if result.get("status") == "UNKNOWN" and (
            not answer or _normalize_text(answer) == "unknown"
        ):
            answer = result.get("reason") or result.get("explanation") or answer
        answer = answer or result.get("reason")
        if answer:
            output_fn(f"Answer/evidence: {answer}")
        missing_information = result.get("missing_information") or []
        if missing_information:
            output_fn(
                "Missing information: "
                + ", ".join(str(item) for item in missing_information)
            )
        evidence = result.get("evidence") or result.get("source_evidence")
        if evidence and evidence != answer:
            output_fn(f"Supporting evidence: {evidence}")
        for related in result.get("related_evidence", []):
            if not isinstance(related, dict):
                continue
            location = ", ".join(
                str(related[field])
                for field in ("document", "page", "section", "chunk_id")
                if related.get(field) is not None
            )
            output_fn(f"Related, non-comparable evidence [{location}]: {related.get('evidence', '')}")

        sources = result.get("sources")
        if not isinstance(sources, list) or not sources:
            source = result.get("source")
            sources = [source] if isinstance(source, dict) else []
        if not sources and any(
            result.get(field) is not None
            for field in ("document", "page", "section", "chunk_id")
        ):
            sources = [result]
        for source in sources:
            if not isinstance(source, dict):
                continue
            provenance = [
                f"{label}: {source[field]}"
                for field, label in (
                    ("document", "Document"),
                    ("page", "Page"),
                    ("section", "Section"),
                    ("chunk_id", "Chunk ID"),
                )
                if source.get(field) is not None
            ]
            if provenance:
                output_fn("Source: " + ", ".join(provenance))
            source_text = source.get("evidence")
            if source_text and source_text != evidence:
                output_fn(f"Source evidence: {source_text}")
    output_fn("=" * 72)


def _run_single_query(query, output_fn=None):
    output_fn = output_fn or print
    try:
        results = match_requirement(query)
    except Exception as error:
        LOGGER.exception("Query processing failed for %r", query)
        _print_query_failure(query, error, output_fn)
        return
    _print_query_results(query, results, output_fn)


def _print_query_failure(query, error, output_fn):
    output_fn("\n" + "=" * 72)
    output_fn(f"Original query: {query}")
    output_fn("Query type: UNKNOWN")
    output_fn("Status: ERROR")
    output_fn(f"Answer/evidence: Query processing failed: {error}")
    output_fn("=" * 72)


def _run_batch_queries(input_fn=None, output_fn=None):
    input_fn = input_fn or input
    output_fn = output_fn or print
    output_fn("Enter one requirement per line. Enter END on a line by itself to finish.")
    while True:
        try:
            query = input_fn("Requirement: ")
        except EOFError:
            output_fn("End of input; batch complete.")
            return
        if query.strip().upper() == "END":
            output_fn("Batch complete.")
            return
        query = query.strip()
        if not query:
            output_fn("Blank line ignored.")
            continue
        _run_single_query(query, output_fn)


def main():
    query = input("\nEnter your requirement (or BATCH for multiple requirements): ")
    if query.strip().upper() == "BATCH":
        _run_batch_queries()
    else:
        _run_single_query(query.strip())


if __name__ == "__main__":
    main()
