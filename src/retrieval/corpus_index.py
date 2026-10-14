"""Build a reusable, provenance-preserving index from processed corpus records."""

import re
from dataclasses import dataclass

from src.retrieval.query_schema import EvidenceFact, EvidenceReference
from src.retrieval.requirement_parser import extract_search_terms


def _clean_product_title(value):
    title = re.sub(r"[®™�]", "", str(value or ""))
    title = re.sub(r"\s+", " ", title).strip(" \t-:;,")
    return re.sub(r"^(?:the|a|an)\s+", "", title, flags=re.IGNORECASE)


def _has_model_identity(title):
    text = re.sub(
        r"\b(?:birthing|hospital|patient|acute\s+care|icu)?\s*bed$|"
        r"\b(?:mobile\s+)?operating\s+table(?:\s+column)?$|"
        r"\bsurgical\s+table$",
        "",
        (title or "").strip(),
        flags=re.IGNORECASE,
    )
    identity_terms = {
        term
        for term in extract_search_terms(text)
        if term not in {
            "medical", "hospital", "patient", "acute", "care", "icu", "birthing",
            "device", "devices", "product", "products", "system",
        }
    }
    return bool(identity_terms)


def _product_kind(title):
    lowered = (title or "").lower()
    if re.search(r"\b(?:surgical|operating)\s+table\b|\btable\s+column\b", lowered):
        return "surgical_equipment"
    if re.search(r"\b(?:birthing|hospital|patient|acute care|icu)?\s*bed\b", lowered):
        return "medical_bed"
    return "other"


def _product_titles_from_text(text):
    titles = []
    lines = re.split(r"[\r\n]+", text or "")
    for index, line in enumerate(lines):
        line = re.sub(r"\s+", " ", line).strip(" \t-:;")
        if not line or len(line) > 180:
            continue
        line = re.split(
            r"\s+(?:is|was|offers|features|includes|supports|provides|"
            r"contains|requires|has|have)\b",
            line,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        line = re.sub(r"\s+", " ", line).strip(" .,:;-")
        if re.search(
            r"\b(?:can|could|should|using|various|support|supports|supported|"
            r"provides|contains|requires|weight|width|length|height|capacity|"
            r"limit|dimensions|designed|available)\b",
            line,
            re.IGNORECASE,
        ):
            continue
        if not re.search(
            r"\b(?:bed|operating table|surgical table|table column)\b",
            line,
            re.IGNORECASE,
        ):
            continue
        title = _clean_product_title(line)
        if not _has_model_identity(title) and index:
            preceding_line = _clean_product_title(lines[index - 1])
            if re.search(r"\b[A-Z]{2,}[- ]?\d{2,}(?:[- ]?[A-Z0-9]+)?\b", preceding_line):
                title = _clean_product_title(f"{preceding_line} {title}")
        if len(title.split()) >= 2:
            titles.append(title)
    return titles


def product_name_from_metadata(product):
    if not isinstance(product, dict):
        return None
    for key in ("product", "product_family", "model", "name"):
        if product.get(key):
            return str(product[key])
    return None


def _identity_key(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class DocumentRecord:
    identifier: str
    document_type: str | None
    document_type_candidates: tuple[str, ...]
    document_type_evidence: tuple[EvidenceReference, ...]
    product_ids: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    fact_count: int


@dataclass(frozen=True)
class ProductRecord:
    identifier: str
    name: str
    category: str
    category_evidence: tuple[EvidenceReference, ...]
    manufacturer: str | None
    manufacturer_evidence: tuple[EvidenceReference, ...]
    identity_reliable: bool
    document_ids: tuple[str, ...]
    sources: tuple[EvidenceReference, ...]


DOCUMENT_TYPE_TERMS = {
    "tender": ("tender", "invitation to tender", "request for proposal"),
    "purchase_order": ("purchase order", "purchase requisition"),
    "certificate": ("certificate", "certification"),
    "compliance": ("compliance", "declaration of conformity"),
    "manual": ("user manual", "instruction manual", "instructions for use"),
    "brochure": ("brochure", "product overview"),
    "technical_specification": ("technical specification", "technical data"),
}


def infer_document_type(chunks):
    """Infer a document type only from explicit text, retaining the matching passage."""
    matches = []
    for chunk in chunks:
        text = chunk.get("text") or ""
        lowered = text.lower()
        for document_type, phrases in DOCUMENT_TYPE_TERMS.items():
            phrase = next((item for item in phrases if item in lowered), None)
            if phrase:
                matches.append(
                    (
                        document_type,
                        {
                            "document": chunk.get("document"),
                            "page": chunk.get("page"),
                            "section": chunk.get("section"),
                            "chunk_id": chunk.get("chunk_id"),
                            "evidence": text,
                        },
                    )
                )

    matched_types = list(dict.fromkeys(document_type for document_type, _ in matches))
    if len(matched_types) != 1:
        return None, matched_types, [source for _, source in matches]
    matched_type = matched_types[0]
    evidence = [
        source
        for document_type, source in matches
        if document_type == matched_type
    ]
    return matched_type, matched_types, evidence


def infer_manufacturer(chunks):
    """Extract a manufacturer only when the passage labels it explicitly."""
    matches = []
    for chunk in chunks:
        for line in (chunk.get("text") or "").splitlines():
            match = re.search(
                r"^\s*(?:manufacturer|brand)\s*[:\-]\s*(.{2,100})\s*$|"
                r"^\s*manufactured\s+by\s+(.{2,100})\s*$",
                line,
                re.IGNORECASE,
            )
            if not match:
                continue
            name = (match.group(1) or match.group(2) or "").strip(" .,:;-")
            if not name:
                continue
            matches.append(
                (
                    name,
                    {
                        "document": chunk.get("document"),
                        "page": chunk.get("page"),
                        "section": chunk.get("section"),
                        "chunk_id": chunk.get("chunk_id"),
                        "evidence": line.strip(),
                    },
                )
            )
    names = list(dict.fromkeys(name for name, _ in matches))
    if len(names) != 1:
        return None, [source for _, source in matches]
    return names[0], [
        source for name, source in matches if name == names[0]
    ]


@dataclass(frozen=True)
class CorpusIndex:
    documents: tuple[DocumentRecord, ...]
    products: tuple[ProductRecord, ...]
    facts: tuple[EvidenceFact, ...]
    _catalogue_records: tuple[dict, ...]

    def catalogue_records(self):
        return [dict(record) for record in self._catalogue_records]

    @classmethod
    def build(cls, chunks, specifications):
        chunks_by_document = {}
        for chunk in chunks:
            document = chunk.get("document")
            if document:
                chunks_by_document.setdefault(document, []).append(chunk)

        specifications_by_document = {}
        facts = []
        for specification in specifications:
            document = specification.get("document")
            if document:
                specifications_by_document.setdefault(document, []).append(specification)
            facts.append(EvidenceFact.from_mapping(specification))

        records = []
        documents = []
        product_documents = {}
        for document in sorted(set(chunks_by_document) | set(specifications_by_document)):
            document_chunks = sorted(
                chunks_by_document.get(document, []),
                key=lambda item: (item.get("page") or 10**9, item.get("chunk_id") or ""),
            )
            early_chunks = [
                chunk for chunk in document_chunks if (chunk.get("page") or 1) <= 3
            ]
            title_candidates = [
                (chunk, title)
                for chunk in early_chunks
                for title in _product_titles_from_text(chunk.get("text", ""))
            ]

            preferred = next(
                (
                    (chunk, title)
                    for chunk, title in title_candidates
                    if _product_kind(title) == "medical_bed" and _has_model_identity(title)
                ),
                None,
            )
            if preferred is None:
                preferred = next(
                    (
                        (chunk, title)
                        for chunk, title in title_candidates
                        if _has_model_identity(title)
                    ),
                    None,
                )
            source_chunk, product_name = preferred or (
                title_candidates[0] if title_candidates else (None, None)
            )
            metadata_products = list(
                dict.fromkeys(
                    chunk.get("product")
                    for chunk in document_chunks
                    if chunk.get("product")
                )
            )
            metadata_product_source = next(
                (
                    chunk
                    for chunk in document_chunks
                    if metadata_products and chunk.get("product") == metadata_products[0]
                ),
                None,
            )
            if product_name is None and len(metadata_products) == 1:
                product_name = str(metadata_products[0])
                source_chunk = metadata_product_source

            category_title = product_name or (
                title_candidates[0][1] if title_candidates else None
            )
            if _product_kind(category_title) == "other" and metadata_product_source:
                metadata_text = metadata_product_source.get("text")
                if _product_kind(metadata_text) != "other":
                    category_title = metadata_text
            if _product_kind(category_title) == "other":
                category_title = next(
                    (
                        chunk.get("text")
                        for chunk in document_chunks
                        if _product_kind(chunk.get("text")) != "other"
                    ),
                    None,
                )

            sources = []
            if source_chunk and product_name and preferred:
                sources.append(
                    EvidenceReference(
                        document=document,
                        page=source_chunk.get("page"),
                        section=source_chunk.get("section"),
                        chunk_id=source_chunk.get("chunk_id"),
                        evidence=product_name,
                    ).to_dict()
                )
            elif source_chunk:
                sources.append(
                    EvidenceReference(
                        document=document,
                        page=source_chunk.get("page"),
                        section=source_chunk.get("section"),
                        chunk_id=source_chunk.get("chunk_id"),
                        evidence=source_chunk.get("text"),
                    ).to_dict()
                )

            document_specs = specifications_by_document.get(document, [])
            document_type, document_type_candidates, type_evidence = infer_document_type(
                document_chunks
            )
            manufacturer, manufacturer_sources = infer_manufacturer(document_chunks)
            record = {
                "product": product_name,
                "document": document,
                "product_kind": _product_kind(category_title),
                "identity_reliable": bool(product_name and _has_model_identity(product_name)),
                "identity_candidates": list(dict.fromkeys(title for _, title in title_candidates)),
                "sources": sources,
                "chunks": document_chunks,
                "specifications": document_specs,
            }
            records.append(record)

            product_ids = ()
            if product_name:
                identity = _identity_key(product_name)
                product_ids = (identity,)
                product_documents.setdefault(identity, []).append(
                    (
                        product_name,
                        document,
                        record["product_kind"],
                        record["identity_reliable"],
                        sources,
                        manufacturer,
                        manufacturer_sources,
                    )
                )
            documents.append(
                DocumentRecord(
                    identifier=document,
                    document_type=document_type,
                    document_type_candidates=tuple(document_type_candidates),
                    document_type_evidence=tuple(
                        EvidenceReference.from_mapping(source)
                        for source in type_evidence
                    ),
                    product_ids=product_ids,
                    chunk_ids=tuple(
                        chunk["chunk_id"]
                        for chunk in document_chunks
                        if chunk.get("chunk_id")
                    ),
                    fact_count=len(document_specs),
                )
            )

        products = []
        for identity, entries in sorted(product_documents.items()):
            names = list(dict.fromkeys(entry[0] for entry in entries))
            product_name = names[0]
            product_sources = tuple(
                EvidenceReference.from_mapping(source)
                for entry in entries
                for source in entry[4]
            )
            manufacturers = list(dict.fromkeys(entry[5] for entry in entries if entry[5]))
            manufacturer_sources = tuple(
                EvidenceReference.from_mapping(source)
                for entry in entries
                for source in entry[6]
            )
            products.append(
                ProductRecord(
                    identifier=identity,
                    name=product_name,
                    category=entries[0][2],
                    category_evidence=product_sources,
                    manufacturer=manufacturers[0] if len(manufacturers) == 1 else None,
                    manufacturer_evidence=manufacturer_sources,
                    identity_reliable=all(entry[3] for entry in entries),
                    document_ids=tuple(dict.fromkeys(entry[1] for entry in entries)),
                    sources=product_sources,
                )
            )
        return cls(
            documents=tuple(documents),
            products=tuple(products),
            facts=tuple(facts),
            _catalogue_records=tuple(records),
        )
