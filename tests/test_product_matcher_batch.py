from src.retrieval import product_matcher


def _input_lines(lines):
    values = iter(lines)
    return lambda _prompt="": next(values)


def test_batch_processes_mixed_query_types_independently_and_prints_provenance(monkeypatch):
    calls = []

    def match(query):
        calls.append(query)
        if query.startswith("How many"):
            return [
                {
                    "query_type": "PRODUCT_COUNT",
                    "status": "COMPLETED",
                    "answer": "Two documented models.",
                    "count": 2,
                    "source_documents": ["catalogue.pdf"],
                }
            ]
        return [
            {
                "query_type": "FEATURE_EXISTENCE",
                "status": "PRESENT",
                "product": "Example bed",
                "answer": "The source describes the feature.",
                "sources": [
                    {
                        "document": "features.pdf",
                        "page": 4,
                        "section": "Controls",
                        "chunk_id": "chunk_4",
                        "evidence": "Feature-specific source passage.",
                    }
                ],
            }
        ]

    monkeypatch.setattr(product_matcher, "match_requirement", match)
    output = []
    product_matcher._run_batch_queries(
        _input_lines(
            [
                "How many beds are documented?",
                "Does Example bed have the feature?",
                "END",
            ]
        ),
        output.append,
    )

    assert calls == [
        "How many beds are documented?",
        "Does Example bed have the feature?",
    ]
    rendered = "\n".join(output)
    assert "Original query: How many beds are documented?" in rendered
    assert "Original query: Does Example bed have the feature?" in rendered
    assert "Query type: PRODUCT_COUNT" in rendered
    assert "Query type: FEATURE_EXISTENCE" in rendered
    assert "Status: COMPLETED" in rendered
    assert "Answer/evidence: Two documented models." in rendered
    assert "Source: Document: features.pdf, Page: 4, Section: Controls, Chunk ID: chunk_4" in rendered
    assert "Feature-specific source passage." in rendered


def test_batch_ignores_blank_lines_and_continues_after_query_failure(monkeypatch):
    calls = []

    def match(query):
        calls.append(query)
        if query == "broken query":
            raise RuntimeError("simulated processing failure")
        return [
            {
                "query_type": "DOCUMENT_RETRIEVAL",
                "status": "FOUND",
                "answer": "Evidence found.",
                "sources": [],
            }
        ]

    monkeypatch.setattr(product_matcher, "match_requirement", match)
    output = []
    product_matcher._run_batch_queries(
        _input_lines(["", "first query", "   ", "broken query", "last query", "END"]),
        output.append,
    )

    assert calls == ["first query", "broken query", "last query"]
    rendered = "\n".join(output)
    assert rendered.count("Blank line ignored.") == 2
    assert "Original query: broken query" in rendered
    assert "Status: ERROR" in rendered
    assert "Query processing failed: simulated processing failure" in rendered
    assert "Original query: last query" in rendered
    assert "Answer/evidence: Evidence found." in rendered


def test_main_preserves_single_query_mode(monkeypatch):
    calls = []
    output = []
    monkeypatch.setattr("builtins.input", lambda _prompt="": "  single requirement  ")
    monkeypatch.setattr("builtins.print", output.append)
    monkeypatch.setattr(
        product_matcher,
        "match_requirement",
        lambda query: calls.append(query)
        or [{"query_type": "UNSUPPORTED_OR_AMBIGUOUS", "status": "UNKNOWN"}],
    )

    product_matcher.main()

    assert calls == ["single requirement"]
    assert any("Original query: single requirement" in line for line in output)
    assert not any("Blank line ignored." in line for line in output)


def test_main_selects_batch_mode(monkeypatch):
    inputs = iter(["BATCH", "requirement one", "END"])
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    monkeypatch.setattr(
        product_matcher,
        "match_requirement",
        lambda query: calls.append(query) or [],
    )

    product_matcher.main()

    assert calls == ["requirement one"]
