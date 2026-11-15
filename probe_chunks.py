"""Read-only probe: print the top raw chunks the index returns. Changes nothing."""
import knowledge

QUESTIONS = [
    "Why should crew shelter during a solar particle event?",
    "Why is radiation shielding important for crew during a solar particle event?",
    "What are the acute radiation syndrome risks for astronauts?",
    "How long can a solar particle event last?",
]

col = knowledge._get_collection()
for q in QUESTIONS:
    print("=" * 90)
    print("Q:", q)
    res = col.query(query_texts=[q], n_results=3)
    for i, (doc, meta, dist) in enumerate(
            zip(res["documents"][0], res["metadatas"][0], res["distances"][0]), 1):
        print(f"\n--- chunk {i} | distance {dist:.3f} | {knowledge._citation(meta or {})}")
        print(" ".join(str(doc).split())[:700])
