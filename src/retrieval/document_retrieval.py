"""Local, provenance-preserving lexical retrieval for processed passages."""

import math
import re
from collections import Counter

from src.retrieval.requirement_parser import extract_search_terms


def _terms(text):
    return Counter(extract_search_terms(text or ""))


def retrieve_passages(
    question,
    chunks,
    catalogue_records=(),
    entity_refs=(),
    product_category=None,
    limit=3,
    focus_terms=(),
):
    """Rank matching chunks; similarity selects evidence but never proves a claim."""
    query_terms = _terms(question)
    if not query_terms:
        return []
    focus = _terms(" ".join(focus_terms)) or query_terms

    records_by_document = {
        record.get("document"): record
        for record in catalogue_records
        if record.get("document")
    }
    if entity_refs:
        allowed_documents = {
            record.get("document")
            for record in catalogue_records
            if record.get("product") in entity_refs
        }
        if not allowed_documents:
            return []
    else:
        allowed_documents = None

    tokenized = []
    document_frequency = Counter()
    for chunk in chunks:
        text = chunk.get("text") or ""
        terms = _terms(f"{chunk.get('section') or ''}\n{text}")
        tokenized.append((chunk, terms))
        document_frequency.update(terms.keys())

    total_documents = max(len(tokenized), 1)
    ranked = []
    for chunk, passage_terms in tokenized:
        document = chunk.get("document")
        if allowed_documents is not None and document not in allowed_documents:
            continue
        record = records_by_document.get(document, {})
        if product_category and record.get("product_kind") != product_category:
            continue

        shared_terms = query_terms.keys() & passage_terms.keys()
        if not shared_terms:
            continue
        if len(query_terms) > 1 and len(shared_terms) < 2:
            continue
        score = sum(
            (1.0 + math.log((total_documents + 1) / (document_frequency[term] + 1)))
            * min(query_terms[term], passage_terms[term])
            for term in shared_terms
        )
        query_coverage = len(shared_terms) / len(query_terms)
        score = score * (0.5 + query_coverage)
        focus_overlap = focus.keys() & passage_terms.keys()
        if focus:
            score += 2.0 * len(focus_overlap) / len(focus)
        passage_lower = (chunk.get("text") or "").lower()
        query_phrase = re.sub(r"\s+", " ", question.strip().lower())
        if len(query_phrase) > 5 and query_phrase in passage_lower:
            score *= 1.5
        if focus and len(focus_overlap) == len(focus):
            focus_phrase = " ".join(focus.keys())
            if focus_phrase in passage_lower:
                score += 1.5
            if re.search(
                r"\b(?:improves?|provides?|enables?|allows?|reduces?|helps?|"
                r"excluding|designed|calculates?)\b",
                passage_lower,
            ):
                score *= 2.5

        source = {
            "document": document,
            "page": chunk.get("page"),
            "section": chunk.get("section"),
            "chunk_id": chunk.get("chunk_id"),
            "evidence": chunk.get("text"),
        }
        ranked.append(
            {
                "score": round(score, 6),
                "product": record.get("product") or chunk.get("product"),
                "document": document,
                "page": source["page"],
                "section": source["section"],
                "chunk_id": source["chunk_id"],
                "evidence": source["evidence"],
                "source": source,
                "sources": [source],
                "source_evidence": source["evidence"],
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["score"],
            item.get("document") or "",
            item.get("page") or 0,
            item.get("chunk_id") or "",
        )
    )
    return ranked[: max(limit, 0)]
