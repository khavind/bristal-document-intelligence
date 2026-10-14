# Bristal Healthcare Intelligence

An AI-powered document intelligence system designed to help healthcare organizations search, understand, and evaluate medical product and tender-related documents.

The project focuses on converting unstructured healthcare documents such as product catalogues, technical specifications, compliance documents, and tender requirements into structured, searchable information.

---

## 🎯 Project Objective

Healthcare organizations often work with a large number of documents containing:

- Product catalogues
- Technical specifications
- Tender documents
- Product brochures
- Compliance documents
- Certifications
- Warranty information
- Product manuals

Finding the right product for a particular tender requirement can require manually going through multiple documents.

The goal of **Bristal Healthcare Intelligence** is to build an intelligent system that can:

1. Process healthcare documents.
2. Extract and structure important information.
3. Understand natural-language requirements.
4. Search relevant product information.
5. Compare product specifications against requirements.
6. Return **PASS / FAIL / UNKNOWN** results.
7. Provide supporting evidence and document/page references.
8. Eventually provide an AI-powered conversational interface for document analysis.

---

# 🧠 Current Architecture

The query layer produces a validated local query plan and routes supported
queries into `PRODUCT_PRESENCE`, `PRODUCT_COUNT`, `FEATURE_EXISTENCE`,
`INVENTORY_COUNT`, `NUMERIC_SPECIFICATION`, `PRODUCT_COMPARISON`,
`PRODUCT_SUMMARY`, or `DOCUMENT_RETRIEVAL`.
Unsupported or ambiguous questions abstain. Catalogue counts represent
distinct identities found in processed documents, not stock counts. Inventory
queries return `UNKNOWN` until a trusted inventory source is connected.

The runtime corpus index is built from processed chunk and specification
records. It keeps source passages, document/page/section/chunk references,
extracted raw values, normalized values, and inferred metadata evidence
together. Product identity and document type are inferred from content and
existing metadata; uncertain identity is not counted as a known model.
`match_requirement()` preserves its existing result keys and adds a common
envelope (`question`, `intent`, `query_plan`, `execution_status`,
`compliance_status`, `sources`, `missing_information`, and `validation`).

General document questions use local lexical passage ranking. Retrieved
passages are evidence candidates, not proof and not a generated summary;
embeddings are not part of the runtime search path. The optional
`embed_chunks()` adapter requires a caller-supplied encoder and corpus and
selects no model or dependency. Compound numeric queries support uniformly
`AND` or `OR` conditions with tri-state combination. Scalar `maximum`,
`minimum`, `average`, and `sum` aggregations are supported across indexed
products when every identified model has a comparable value. A numeric
threshold without an explicit attribute is not matched to a convenient
candidate attribute. Recognized flow-rate values support `ml/hr` and `l/hr`
conversion; unsupported or missing units remain unevaluable.

Numeric filtering evaluates every reliably indexed product in the requested
category and returns product-scoped `PASS`, `FAIL`, or `UNKNOWN` rows.
Missing attributes remain `UNKNOWN`; unrelated attributes (for example,
product weight instead of safe working load) are not substituted. Product
comparisons resolve each named identity and compare only the requested
attribute. Product summaries are deterministic lists of extracted facts and
retrieved passages, with source locations and explicit standard/optional
labels only when the extractor recorded them. Natural-language document
questions return at most three ranked passages by default; `search_documents`
defaults to five and accepts a configurable `limit`. Retrieval favors
explanatory passages for named features and indexes section headings when
ranking evidence. The interactive matcher retains single-query input; enter
`BATCH` to process one requirement per line and `END` to finish the batch.

This is a deterministic local fallback, not universal natural-language
understanding. It does not yet provide LLM-based answer composition, robust
coreference resolution, time-aware operational facts, arbitrary grouped
aggregations, or a source-authority policy for resolving contradictions.
Aggregations over an incomplete or conflicting fact set abstain. A lexical
match alone cannot answer questions whose wording has no sufficiently
relevant source passage.
The current processed Affinity specification labels `480 lbs (218 kg)` as
`Bed weight`, not safe working load. The matcher intentionally treats that
fact as unrelated to a safe-working-load requirement; it reports `UNKNOWN`
for that product until source-backed safe-working-load evidence is extracted.
The same source page lists a `Maximum Lift Capacity` section with `Bed` and
`Foot section` values, but the current extractor pairs the parent label with
`Bed` and misses the numeric table values. This extraction limitation is also
left visible rather than being used as a safe-working-load substitute.

The current prototype follows a modular pipeline:

```text
                 PDF DOCUMENT
                      │
                      ▼
              ┌─────────────────┐
              │ PDF Extraction  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Text Normalizer │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │    Chunking     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Specification   │
              │   Extraction    │
              └────────┬────────┘
                       │
                       ▼
             Structured Product Data
                       │
                       ├────────────────────┐
                       │                    │
                       ▼                    ▼
              Semantic Retrieval      Requirement Parser
                       │                    │
                       │                    ▼
                       │             Structured Requirement
                       │                    │
                       │                    ▼
                       │              Value Parser
                       │                    │
                       │                    ▼
                       │                Evaluator
                       │                    │
                       └──────────┬─────────┘
                                  ▼
                         Product Matching
                                  │
                                  ▼
                         PASS / FAIL / UNKNOWN