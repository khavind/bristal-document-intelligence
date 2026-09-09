import json
from pathlib import Path

from sentence_transformers import SentenceTransformer


input_path = "data/processed/sample_product_chunks.json"
output_path = "data/processed/sample_product_embeddings.json"


# Load the embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")


# Load chunks
with open(input_path, "r", encoding="utf-8") as file:
    data = json.load(file)


chunks = data["chunks"]


# Extract text from each chunk
texts = [
    chunk["text"]
    for chunk in chunks
]


# Generate embeddings
embeddings = model.encode(texts)


# Add embedding to each chunk
for chunk, embedding in zip(chunks, embeddings):

    chunk["embedding"] = embedding.tolist()


# Save chunks + embeddings
output_data = {
    "chunks": chunks
}


Path("data/processed").mkdir(
    parents=True,
    exist_ok=True
)


with open(output_path, "w", encoding="utf-8") as file:

    json.dump(
        output_data,
        file,
        indent=4,
        ensure_ascii=False
    )


print(f"Total chunks: {len(chunks)}")
print(f"Total embeddings: {len(embeddings)}")
print(f"Embedding dimensions: {len(embeddings[0])}")
print(f"Embeddings saved to: {output_path}")