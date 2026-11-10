"""Conservative, local interpretation of supported document-intelligence queries."""

import re

from src.retrieval.query_schema import QueryCondition, QueryPlan
from src.retrieval.requirement_parser import (
    ATTRIBUTE_ALIASES,
    classify_query_intent,
    extract_search_terms,
    find_attribute,
    normalize_query,
    parse_requirement,
)


def _condition_segments(question):
    pieces = re.split(
        r"\s+\b(and|or)\b(?!\s+(?:table\s+)?column\b)\s+",
        question,
        flags=re.IGNORECASE,
    )
    segments = []
    logical_operators = []
    for index, piece in enumerate(pieces):
        if index % 2:
            logical_operators.append(piece.upper())
        elif re.search(r"(?:>=|<=|>|<|=|\b(?:at least|at most|minimum|maximum|"
                       r"more than|greater than|less than|fewer than|exactly|"
                       r"or more|or less)\b)\s*\d", piece, re.IGNORECASE):
            segments.append(piece.strip(" ,;"))
    return segments, logical_operators


def _condition_from_text(text):
    parsed = parse_requirement(text)
    if parsed.get("value") is None or parsed.get("operator") is None:
        return None
    return QueryCondition(
        attribute=parsed.get("attribute"),
        operator=parsed["operator"],
        value=float(parsed["value"]),
        unit=parsed.get("unit"),
        raw_text=text,
    )


def _entity_query_prefix(question):
    normalized = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    attribute_starts = []
    for alias in ATTRIBUTE_ALIASES:
        normalized_alias = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
        if not normalized_alias:
            continue
        match = re.search(
            rf"(?<!\w){re.escape(normalized_alias)}(?!\w)",
            normalized,
        )
        if match:
            attribute_starts.append(match.start())
    return normalized[:min(attribute_starts)] if attribute_starts else normalized


def _entity_references(question, product_records, include_all_matches=False):
    query_prefix = _entity_query_prefix(question)
    query_terms = set(extract_search_terms(query_prefix))
    generic_terms = {
        "bed", "beds", "table", "tables", "product", "products", "model",
        "models", "device", "devices", "which", "what", "does", "have",
        "support", "supports", "listed", "documented", "catalogue", "catalog",
        "operating", "surgical", "birthing", "hospital", "patient", "icu",
        "medical", "acute", "care",
    }
    query_terms -= generic_terms
    matches = []
    for record in product_records:
        product = record.get("product")
        if not product or not record.get("identity_reliable", True):
            continue
        product_terms = set(extract_search_terms(product)) - generic_terms
        if not product_terms:
            continue
        overlap = query_terms & product_terms
        normalized_question = re.sub(
            r"[^a-z0-9]+",
            " ",
            question.lower(),
        ).strip()
        normalized_product = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(product).lower(),
        ).strip()
        if normalized_product and normalized_product in normalized_question:
            overlap |= product_terms
        if overlap:
            matches.append((len(overlap), str(product), overlap))

    if not matches:
        return (), ()
    if include_all_matches:
        owners = {}
        for _, product, overlap in matches:
            for term in overlap:
                owners.setdefault(term, set()).add(product)
        selected = tuple(
            dict.fromkeys(
                product
                for _, product, overlap in matches
                if any(len(owners[term]) == 1 for term in overlap)
            )
        )
        if len(selected) >= 2:
            return selected, ()
        return (), ()
    best_score = max(score for score, _, _ in matches)
    best = tuple(dict.fromkeys(name for score, name, _ in matches if score == best_score))
    ambiguities = ("The product reference matches more than one indexed identity.",) if len(best) > 1 else ()
    return best, ambiguities


def _unresolved_entity_mention(question, product_records, resolved_entities):
    if resolved_entities:
        return None
    known_terms = {
        term
        for record in product_records
        for term in extract_search_terms(record.get("product") or "")
    }
    patterns = (
        r"\b(?:model|product|device)\s+([A-Z][A-Za-z0-9-]*(?:\s+(?:[A-Z][A-Za-z0-9-]*|\d+)){0,2})",
        r"\bfor\s+(?:the\s+)?([A-Z][A-Za-z0-9-]*(?:\s+\d+[A-Za-z]?)?)",
        r"\b([A-Z][A-Za-z0-9-]*(?:\s+\d+[A-Za-z]?)?)\s+(?:bed|table|device)\b",
    )
    attribute_terms = set(extract_search_terms(find_attribute(question) or ""))
    generic_entity_terms = {
        "bed", "beds", "table", "tables", "device", "devices", "icu",
        "hospital", "birthing", "medical", "surgical", "operating", "patient",
        "model", "models", "product", "products", "distinct", "different",
        "documented", "listed", "catalogue", "catalog",
    }
    for pattern in patterns:
        for match in re.finditer(pattern, question, re.IGNORECASE):
            if not match.group(1)[:1].isupper():
                continue
            if match.start() == 0 and match.group(1).lower() in {"the", "a", "an"}:
                continue
            candidate_terms = set(extract_search_terms(match.group(1)))
            if candidate_terms <= generic_entity_terms or candidate_terms & attribute_terms:
                continue
            if candidate_terms and not candidate_terms & known_terms:
                return "An explicitly named product or model is not present in the indexed corpus."
    return None


def _category_reference(question, product_records):
    normalized = question.lower()
    categories = set()
    if re.search(r"\b(?:bed|beds|hospital bed|birthing bed|icu bed)\b", normalized):
        categories.add("medical_bed")
    if re.search(r"\b(?:surgical|operating)\s+tables?\b|\btable column\b", normalized):
        categories.add("surgical_equipment")

    indexed_categories = {
        record.get("product_kind")
        for record in product_records
        if record.get("identity_reliable") and record.get("product_kind") != "other"
    }
    matched = categories & indexed_categories
    return next(iter(matched)) if len(matched) == 1 else None


def _aggregation_request(question):
    for pattern, aggregation in (
        (r"\b(?:highest|maximum|max)\b", "maximum"),
        (r"\b(?:lowest|minimum|min)\b", "minimum"),
        (r"\b(?:average|mean)\b", "average"),
        (r"\b(?:sum|total)\b", "sum"),
    ):
        if re.search(pattern, question, re.IGNORECASE):
            return aggregation
    return None


def _is_comparison_request(question):
    return bool(re.search(r"\b(?:compare|comparison|versus|vs\.?)\b", question, re.I))


def _is_summary_request(question):
    return bool(
        re.search(
            r"\b(?:summari[sz]e|summary|list)\b.*\b(?:features?|specifications?|specs?)\b|"
            r"\bwhat features?\b.*\b(?:offer|offers|include|includes|have|has)\b",
            question,
            re.IGNORECASE,
        )
    )


def _focus_terms(question, entity_refs):
    generic_terms = {
        "about", "compare", "comparison", "does", "have", "has", "important",
        "include", "includes", "list", "main", "offer", "offers", "say",
        "says", "specification", "specifications", "specs", "summary",
        "summarize", "summarise", "the", "what", "which", "versus",
    }
    entity_terms = {
        term
        for entity in entity_refs
        for term in extract_search_terms(entity)
    }
    return tuple(
        term
        for term in dict.fromkeys(extract_search_terms(question))
        if term not in generic_terms and term not in entity_terms
    )


def _extract_time_scope(question):
    match = re.search(
        r"\b(?:as of \d{4}(?:-\d{2}(?:-\d{2})?)?|in \d{4}|during \d{4}|"
        r"between \d{4} and \d{4}|since \d{4}|before \d{4}|after \d{4}|"
        r"currently|current|today|latest|most recent)\b",
        question,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


def understand_query(question, product_records=()):
    """Return a validated plan; unsupported parsing is represented explicitly."""
    normalized = normalize_query(question)
    base_intent = classify_query_intent(normalized)
    segments, logical_operators = _condition_segments(normalized)
    conditions = tuple(
        condition
        for segment in segments
        if (condition := _condition_from_text(segment)) is not None
    )

    if base_intent == "NUMERIC_SPECIFICATION" and not conditions:
        conditions = tuple(
            condition
            for condition in [_condition_from_text(normalized)]
            if condition is not None
        )

    aggregation = _aggregation_request(normalized)
    aggregation_attribute = find_attribute(normalized)
    comparison_request = _is_comparison_request(normalized)
    summary_request = _is_summary_request(normalized)
    time_scope = _extract_time_scope(normalized)
    aggregation_scope = re.search(
        r"\b(?:across|among|overall|in the (?:catalogue|catalog|corpus)|"
        r"all (?:documented )?(?:products|models)|which (?:product|model) has)\b",
        normalized,
        re.IGNORECASE,
    )

    if conditions:
        intent = "NUMERIC_SPECIFICATION"
        output_type = "compliance"
        supported = True
    elif comparison_request:
        intent = "PRODUCT_COMPARISON"
        output_type = "comparison"
        supported = True
        if aggregation_attribute:
            conditions = (
                QueryCondition(
                    attribute=aggregation_attribute,
                    operator=None,
                    value=None,
                    unit=None,
                    raw_text=normalized,
                ),
            )
    elif aggregation and aggregation_attribute and aggregation_scope:
        intent = "SPECIFICATION_AGGREGATION"
        output_type = "aggregation"
        supported = True
        conditions = (
            QueryCondition(
                attribute=aggregation_attribute,
                operator=None,
                value=None,
                unit=None,
                raw_text=normalized,
            ),
        )
    elif summary_request:
        intent = "PRODUCT_SUMMARY"
        output_type = "summary"
        supported = True
    elif re.match(
        r"^(?:what|where|when|why|who)\b",
        normalized,
        re.IGNORECASE,
    ):
        intent = "DOCUMENT_RETRIEVAL"
        output_type = "evidence"
        supported = True
    elif base_intent in {
        "PRODUCT_PRESENCE",
        "PRODUCT_COUNT",
        "FEATURE_EXISTENCE",
        "INVENTORY_COUNT",
    }:
        intent = base_intent
        output_type = "count" if base_intent == "PRODUCT_COUNT" else "evidence"
        supported = True
    elif re.match(r"^how\b", normalized, re.IGNORECASE):
        intent = "DOCUMENT_RETRIEVAL"
        output_type = "evidence"
        supported = True
    else:
        intent = "UNSUPPORTED_OR_AMBIGUOUS"
        output_type = "evidence"
        supported = False

    entity_refs, identity_ambiguities = _entity_references(
        normalized,
        product_records,
        include_all_matches=comparison_request,
    )
    product_category = _category_reference(normalized, product_records)
    ambiguities = list(identity_ambiguities)
    unresolved_entity = _unresolved_entity_mention(
        normalized,
        product_records,
        entity_refs,
    )
    if unresolved_entity:
        ambiguities.append(unresolved_entity)
    missing = []
    if intent == "NUMERIC_SPECIFICATION":
        for condition in conditions:
            if condition.attribute is None:
                missing.append("attribute")
            if condition.unit is None:
                missing.append("unit")
    if intent == "PRODUCT_COMPARISON":
        if len(entity_refs) < 2:
            ambiguities.append(
                "At least two distinct product identities could not be resolved for comparison."
            )
            missing.append("products")
        if not conditions:
            missing.append("attribute")
            ambiguities.append("The comparison attribute could not be resolved.")
    elif intent == "PRODUCT_SUMMARY" and len(entity_refs) != 1:
        ambiguities.append(
            "A product summary requires exactly one resolved product identity."
        )
        missing.append("product")
    if conditions and len(logical_operators) and len(set(logical_operators)) > 1:
        ambiguities.append("Mixed AND/OR expressions require explicit grouping and are not interpreted.")
        supported = False
    if time_scope and intent in {
        "DOCUMENT_RETRIEVAL",
        "SPECIFICATION_AGGREGATION",
        "NUMERIC_SPECIFICATION",
    }:
        ambiguities.append(
            "The requested time scope cannot be applied because source-date metadata is not indexed."
        )
        supported = False
    if ambiguities:
        supported = False

    confidence = (
        0.65
        if supported and intent == "DOCUMENT_RETRIEVAL" and not ambiguities
        else 0.9
        if supported and not ambiguities
        else 0.5
        if supported
        else 0.0
    )
    if intent == "UNSUPPORTED_OR_AMBIGUOUS":
        confidence = 0.0

    operator = logical_operators[0] if logical_operators else "AND"
    return QueryPlan(
        question=normalized,
        intent=intent,
        entity_refs=entity_refs,
        focus_terms=_focus_terms(normalized, entity_refs),
        product_category=product_category,
        conditions=conditions,
        logical_operator=operator,
        aggregation=(
            "count_distinct"
            if intent == "PRODUCT_COUNT"
            else aggregation
            if intent == "SPECIFICATION_AGGREGATION"
            else None
        ),
        output_type=output_type,
        time_scope=time_scope,
        ambiguities=tuple(ambiguities),
        missing_information=tuple(dict.fromkeys(missing)),
        confidence=confidence,
        supported=supported,
    )
