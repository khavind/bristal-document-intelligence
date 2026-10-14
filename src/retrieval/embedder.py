"""Optional adapter for callers that already provide a compatible encoder."""


def embed_chunks(chunks, encoder):
    """Return copied chunks with encoder vectors; this module selects no model or corpus."""
    if not hasattr(encoder, "encode") or not callable(encoder.encode):
        raise TypeError("encoder must provide a callable encode(texts) method.")

    chunk_records = [dict(chunk) for chunk in chunks]
    texts = [str(chunk.get("text") or "") for chunk in chunk_records]
    if not texts:
        return {"chunks": chunk_records}

    embeddings = encoder.encode(texts)
    if len(embeddings) != len(chunk_records):
        raise ValueError("Encoder output count does not match the number of chunks.")

    for chunk, embedding in zip(chunk_records, embeddings):
        chunk["embedding"] = (
            embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        )
    return {"chunks": chunk_records}
