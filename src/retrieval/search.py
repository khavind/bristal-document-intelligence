"""Reusable lexical search over the processed document corpus."""

import json

from src.retrieval.document_retrieval import retrieve_passages
from src.retrieval.product_matcher import _catalogue_records, _load_processed_chunks


def search_documents(query, *, product=None, document=None, limit=5):
    """Return relevant passages, optionally restricted to an indexed product/document."""
    records = _catalogue_records()
    entity_refs = ()
    if product:
        matches = tuple(
            record["product"]
            for record in records
            if record.get("product")
            and record["product"].casefold() == product.casefold()
        )
        if not matches:
            return []
        entity_refs = matches
    chunks = _load_processed_chunks()
    if document:
        chunks = [chunk for chunk in chunks if chunk.get("document") == document]
        if not chunks:
            return []
    return retrieve_passages(
        query,
        chunks,
        catalogue_records=records,
        entity_refs=entity_refs,
        limit=limit,
    )


def main():
    query = input("Enter a document question: ").strip()
    results = search_documents(query)
    if not results:
        print("No sufficiently relevant source passages were found.")
        return
    for result in results:
        print(
            json.dumps(
                {
                    "score": result["score"],
                    "document": result["document"],
                    "page": result["page"],
                    "section": result["section"],
                    "chunk_id": result["chunk_id"],
                    "evidence": result["evidence"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
