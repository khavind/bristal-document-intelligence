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
