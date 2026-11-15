import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import knowledge

QUESTIONS = [
    "Why should crew shelter during a solar particle event?",
    "How long can a solar particle event last?",
    "What is a geomagnetic storm?",
    "How does space weather affect astronauts?",
    "What is the difference between solar flares and coronal mass ejections?",
    "What are the acute radiation syndrome risks for astronauts?",
    "Why is acute radiation syndrome unlikely during a solar particle event?",
    "What dose ranges do large solar particle events contribute?",
    "Why does NASA plan to return to the Moon?",
    "What is the capital of Ghana?",
]

col = knowledge._get_collection()
for q in QUESTIONS:
    print("=" * 78)
    print("Q:", q)
    res = col.query(query_texts=[q], n_results=3)
    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
        flag = "OK " if dist <= knowledge.MAX_DISTANCE else "FAR"
        print(f"  [{flag}] d={dist:.3f}  {meta.get('source_label')}  "
              f"p.{meta.get('page_start')}  {meta.get('section_path')}")
    ev = knowledge.evidence(q)
    print("  EVIDENCE ok:", ev["ok"])
    print("  TEXT  :", ev["text"])
    print("  SOURCE:", ev["source"])
