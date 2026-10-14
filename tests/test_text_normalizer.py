import json

from src.ingestion.text_normalizer import normalize_text, process_documents


def test_process_documents_normalizes_only_extracted_page_json(tmp_path):
    extracted = [{"page": 1, "text": "SpOI\t value\n\n\nwith spaces : "}]
    (tmp_path / "document.json").write_text(
        json.dumps(extracted), encoding="utf-8"
    )
    existing_normalized = tmp_path / "keep_normalized.json"
    existing_normalized.write_text("preserve", encoding="utf-8")
    (tmp_path / "document_chunks.json").write_text("preserve", encoding="utf-8")

    process_documents(tmp_path)

    normalized = json.loads(
        (tmp_path / "document_normalized.json").read_text(encoding="utf-8")
    )
    assert normalized[0]["text"] == normalize_text(extracted[0]["text"])
    assert existing_normalized.read_text(encoding="utf-8") == "preserve"
    assert (tmp_path / "document_chunks.json").read_text(encoding="utf-8") == "preserve"
