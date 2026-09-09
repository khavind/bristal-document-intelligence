import json

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


input_path = "data/processed/sample_product_embeddings.json"


# Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")


# Load chunks and embeddings
with open(input_path, "r", encoding="utf-8") as file:
    data = json.load(file)


chunks = data["chunks"]


# Ask the user for a search query
query = input("Enter your question: ")


# Convert question into an embedding
query_embedding = model.encode([query])


# Extract stored embeddings
chunk_embeddings = [
    chunk["embedding"]
    for chunk in chunks
]


# Calculate similarity
similarities = cosine_similarity(
    query_embedding,
    chunk_embeddings
)[0]


# Attach similarity score to each chunk
results = []

for chunk, score in zip(chunks, similarities):

    results.append({
        "chunk": chunk,
        "score": float(score)
    })


# Sort by highest similarity
results.sort(
    key=lambda item: item["score"],
    reverse=True
)


# Display top 3 results
print("\n--- Top Results ---\n")


for result in results[:3]:

    chunk = result["chunk"]
    score = result["score"]

    print(f"Score: {score:.4f}")
    print(f"Product: {chunk['product']}")
    print(f"Page: {chunk['page']}")
    print(f"Section: {chunk['section']}")
    print(f"Text:\n{chunk['text']}")
    print("-" * 60)