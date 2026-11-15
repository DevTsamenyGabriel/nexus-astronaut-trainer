# test_embed.py - checks whether Chroma's default embedding works
import chromadb

client = chromadb.PersistentClient(path="./chroma_test")
collection = client.get_or_create_collection("test")

# Add two sentences, then search with a paraphrase
collection.add(
    ids=["1", "2"],
    documents=[
        "Radiation exposure rises during solar particle events.",
        "Plant the maize seeds after the first rains."
    ],
)

results = collection.query(
    query_texts=["Why is it dangerous outside during a solar storm?"],
    n_results=1,
)
print(results["documents"][0][0])  # should print the radiation sentence