# test_rag.py - tests search and metadata on the saved chunks. No Groq, no internet needed.
# Run from anywhere. The database path is fixed to the NASA_HACKATHON folder.

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb                 # local vector database

DB_PATH = r"C:\Users\gabby\Documents\NASA_HACKATHON\chroma_db"   # same database ingest.py writes
COLLECTION_NAME = "nasa_docs"

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_collection(COLLECTION_NAME)

# Each test: a question, and what we expect (answerable or refuse)
TESTS = [
    ("Why is acute radiation syndrome unlikely during a solar particle event?", "answerable"),
    ("What dose ranges do large solar particle events contribute?", "answerable"),
    ("What are the dose limit categories in Table 1?", "answerable"),
    ("What are the abort triggers during an extravehicular activity?", "answerable"),
    ("What is the capital of Ghana?", "refuse"),
    ("What are the symptoms of the hematopoietic syndrome?", "refuse"),
]

# How close a match must be before we trust it (lower distance = closer match)
MAX_DISTANCE = 1.2

passed = 0
for question, expected in TESTS:
    results = collection.query(query_texts=[question], n_results=3)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    print("=" * 70)
    print(f"QUESTION: {question}")
    print(f"EXPECTED: {expected}")
    for doc, meta, dist in zip(docs, metas, distances):
        print(f"  distance={dist:.3f}  {meta['source_label']}  p.{meta['page_start']}  section={meta['section_path']}")
        print(f"    {doc[:150].replace(chr(10), ' ')}...")

    best = distances[0]
    verdict = "answerable" if best <= MAX_DISTANCE else "refuse"
    print(f"SEARCH SAYS: {verdict} (best distance {best:.3f})")
    if verdict == expected:
        print("MATCH")
        passed += 1
    else:
        print("MISMATCH, check the chunks above")
    print()

print("=" * 70)
print(f"SEARCH TESTS PASSED: {passed} of {len(TESTS)}")

# Metadata check: every chunk must carry the fields a citation needs
REQUIRED = ["source_label", "section_path", "page_start"]

all_items = collection.get()    # returns every stored chunk
bad = []
for meta in all_items["metadatas"]:
    for field in REQUIRED:
        if field not in meta or meta[field] in (None, ""):
            bad.append((field, meta))

print("=" * 70)
print(f"Total chunks in database: {len(all_items['metadatas'])}")
print(f"Metadata problems: {len(bad)}")
for field, meta in bad[:5]:
    print(f"  missing {field} in: {meta}")
print("METADATA OK" if not bad else "METADATA NEEDS FIXING")