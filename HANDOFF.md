handoff.md
4. CODE:
markdown
# HANDOFF

## 14 Nov 2026, ~19:00 GMT: Sage (knowledge layer)

**Status:** knowledge.py works on its own. NOT yet connected to the app. Nothing calls knowledge.ask() today.

**Index:** 116 chunks, 4 documents (ARS report, EVA Ops Ch. 5.4, NOAA Space Weather 101, Artemis Plan 2020). Built by ingest.py. Do not re-run ingest.py: it deletes and rebuilds the whole collection.

**Test results (run on Gabby's machine, reported by the Copilot run, raw output not yet checked by Sage):**
- Q1 ARS unlikely during SPE: answered with citations (needed CITE_MAX = 3; at 2 it refused)
- Q2 dose ranges of large SPEs: answered with citations
- Q3 Table 1 dose-limit categories: answered with citations
- Q4 capital of Ghana: refused, PASS
- Q5 hematopoietic symptoms: refused, PASS
- Offline check (bad API key): AI: OFFLINE with excerpts, PASS

**Contract (what ask returns):**
knowledge.ask(question) returns {"answer": str, "sources": [str]}. Never raises.
- Not in the NASA text: answer is exactly "I don't have that in my NASA sources." and sources is [].
- Groq or internet down: answer starts with "AI: OFFLINE" and shows the retrieved text. Sources are still filled in.
- NOTE: right now "answer" also ends with a safety note and the Source lines. That would be read aloud by the voice. Sage will change knowledge.py so "answer" holds ONLY the spoken explanation and "sources" holds the citations. Until Sage says it is done, do not ship the UI part below.

### For Atlas (backend.py)
1. Add this method to NexusBackend:

    def ask(self, question):
        try:
            import knowledge
            return knowledge.ask(question)
        except Exception:
            return {"answer": "AI: OFFLINE", "sources": []}

2. At the top of respond_stream, before the normal Groq path, route NASA questions to ask:

    KNOWLEDGE_TRIGGER = re.compile(r"^\s*(what|why|how|explain|define|tell me about)\b", re.I)

    if KNOWLEDGE_TRIGGER.search(user_text or ""):
        result = self.ask(user_text)
        for sentence in _SENT_END.split(result["answer"]):
            if sentence.strip():
                yield ("sentence", sentence.strip())
        if result["sources"]:
            yield ("action", {"type": "show_sources", "sources": result["sources"]})
        return

Commands like "delay the EVA" or "use the shelter" do not start with a question word, so they still use the normal path. Change the trigger if you want it wider or narrower.

### For Orion (main.py, ui/chat.py)
1. In Controller.run_action add a branch for action type "show_sources". Show action["sources"] as text under the last NEXUS message. Do NOT send it to the speech queue.
2. Add a small chat.py method to display that source text (muted style, not spoken, selectable).
3. run_action already ignores unknown types safely, so nothing breaks before this ex

## 2026-11-14 | Atlas | balance results (sim_test.py, seeds 1-10, simulation values)
**Tested:** CHECK 1 wiring OK. sim_test.py exit 0, TRADE-OFF CHECK PASS (first tuning).
| dest | strategy | success/10 | avg readiness |
|---|---|---|---|
| moon | max_everything | 8 | 69.8 |
| moon | all_in_power | 0 | 65.5 |
| moon | adaptive | 10 | 80.5 |
| mars | max_everything | 2 | 68.9 |
| mars | all_in_power | 0 | 65.0 |
| mars | adaptive | 10 | 72.9 |
**Value ranges seen (Mars, adaptive, day 30):** power 9.6, oxygen 19.6, water 52.2, food 40.3,
CO2 15 (peaks ~31), crew radiation 25.5 (peak 27.5), readiness 57.8. Readiness stays 55-97.
Resources reach the red zone (<20) late in the run, so Nova's warn/critical thresholds at 30/20 are right.
**Known weakness:** Moon max_everything still succeeds 8/10. A retune (harsher night) is pending a re-run.
**For Orion:** in Controller.__init__ add `self.backend.bind(self.state)`. After onboarding call
`self.backend.start_mission(name, "moon" or "mars")`. Until then advance_day() does nothing (no crash).

### 2026-11-14 | Orion — onboarding integration deferred
Decision: Do not connect LoginView to main.py yet. First run and verify the existing app and finish the interaction flow; integrate onboarding after that.
Reason: Gabby wants to confirm main.py works before adding the login/startup wiring.
Impact: Keep the current app startup unchanged for now. Do not replace main() or change Controller initialization for onboarding until Gabby asks.
Events received: Atlas event option IDs confirmed from events.py, including spe_shelter and spe_postpone.
