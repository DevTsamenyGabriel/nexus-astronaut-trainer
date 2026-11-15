import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import knowledge

ANSWERABLE = [
    "Why is acute radiation syndrome unlikely during a solar particle event?",
    "What dose ranges do large solar particle events contribute?",
    "What are the dose limit categories in Table 1?",
]
MUST_REFUSE = [
    "What is the capital of Ghana?",
    "What are the hematopoietic symptoms?",
]

for q in ANSWERABLE:
    r = knowledge.ask(q)
    print("\nANSWERABLE:", q, "\n", r["answer"], "\n", r["sources"])
for q in MUST_REFUSE:
    r = knowledge.ask(q)
    ok = r["answer"] == knowledge.REFUSAL and r["sources"] == []
    print("\nREFUSE:", q, "->", "PASS" if ok else "FAIL", "\n", r["answer"][:300])

os.environ["GROQ_API_KEY"] = "bad-key"      # offline fallback check
r = knowledge.ask(ANSWERABLE[0])
print("\nOFFLINE CHECK:", "PASS" if r["answer"].startswith("AI: OFFLINE") else "FAIL")
