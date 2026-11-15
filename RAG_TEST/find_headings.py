# load_headings.py - reads the first pages of each core document and writes headings.txt.
# Uses the folder where THIS script lives, so it works no matter where the terminal is open.

import pymupdf                  # reads PDF files
from pathlib import Path        # builds file paths that work on Windows

SCRIPT_FOLDER = Path(r"C:\Users\gabby\Documents\NASA_HACKATHON")   # the NASA_HACKATHON folder
NASA_FOLDER = SCRIPT_FOLDER / "nasa_docs"         # full path to the PDFs

CORE_FILES = [
    "NASA Extravehicular Activities Operations Chapter 5.4.pdf",
    "Space Weather 101 Factsheet Final.pdf",
    "Space Flight Human-System Standard.pdf",
    "artemis_plan-20200921.pdf",
    "Human Exploration of Mars Design Reference Architecture 5.0.pdf",
]

print("Looking in:", NASA_FOLDER)
print("Files found there:", [p.name for p in NASA_FOLDER.glob("*.pdf")])

out = []
missing = []

for name in CORE_FILES:
    path = NASA_FOLDER / name
    if not path.exists():
        missing.append(name)
        continue

    doc = pymupdf.open(path)
    out.append(f"===== {name} ({len(doc)} pages) =====")

    # Look at the first 25 pages, or all of them if the file is shorter
    for page_number in range(min(25, len(doc))):
        lines = [line.strip() for line in doc[page_number].get_text().split("\n") if line.strip()]
        out.append(f"--- PDF page {page_number + 1} ---")
        for line in lines[:3]:          # first 3 non-empty lines of the page
            out.append("   " + line[:100])
    out.append("")
    doc.close()

if missing:
    out.insert(0, "MISSING FILES:")
    for i, name in enumerate(missing, start=1):
        out.insert(i, f"   {name}")
    out.insert(len(missing) + 1, "")

Path(SCRIPT_FOLDER / "headings.txt").write_text("\n".join(out), encoding="utf-8")
print(f"Wrote headings.txt ({len(CORE_FILES) - len(missing)} of {len(CORE_FILES)} files read)")
if missing:
    print("Missing:", ", ".join(missing))