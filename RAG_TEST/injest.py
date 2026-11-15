# ingest.py - builds the ChromaDB index from several NASA PDFs in one run.
# Paths are fixed to the NASA_HACKATHON folder, so it works from any terminal location.
# Run this whenever the MANIFEST changes. It rebuilds the whole database.

import re                       # regular expressions, used to find headings and table captions
import chromadb                 # local vector database
import pymupdf4llm              # converts PDF pages to Markdown text
from pathlib import Path        # file paths that work on Windows

PROJECT_FOLDER = Path(r"C:\Users\gabby\Documents\NASA_HACKATHON")   # fixed project folder
NASA_FOLDER = PROJECT_FOLDER / "nasa_docs"                         # where the PDFs live
DB_PATH = str(PROJECT_FOLDER / "chroma_db")                        # where the database is saved
COLLECTION_NAME = "nasa_docs"

MAX_CHARS = 1000   # about 250 tokens. Tested on real questions.

# One entry per document. Page numbers are PDF page numbers (1-based).
MANIFEST = [
    {
        "file": "Risk_of_Acute_Radiation_Syndrome.pdf",
        "label": "NASA HRP SPE Report, 2016",
        "title": "Evidence Report: Risk of Acute Radiation Syndromes due to Solar Particle Events",
        "pages": range(5, 10),       # PDF pages 5 to 9
    },
    {
        "file": "NASA Extravehicular Activities Operations Chapter 5.4.pdf",
        "label": "NASA EVA Ops, Ch. 5.4",
        "title": "Extravehicular Activities (Chapter 5.4), Space Physiology and Medicine",
        "pages": range(1, 13),       # PDF pages 1 to 12
    },
    {
        "file": "Space Weather 101 Factsheet Final.pdf",
        "label": "NOAA Space Weather 101",
        "title": "Space Weather 101 Factsheet",
        "pages": range(1, 6),        # PDF pages 1 to 5
    },
    {
        "file": "artemis_plan-20200921.pdf",
        "label": "NASA Artemis Plan, 2020",
        "title": "NASA's Lunar Exploration Program Overview",
        "pages": range(21, 26),      # PDF pages 21 to 25 (lunar surface section)
    },
]


def load_pages(entry):
    """Read the chosen pages of one document. Returns a list of (pdf_page, markdown_text)."""
    path = NASA_FOLDER / entry["file"]
    zero_based = [p - 1 for p in entry["pages"]]     # pymupdf4llm counts pages from 0
    pages = pymupdf4llm.to_markdown(str(path), pages=zero_based, page_chunks=True)
    # 'page_number' is already the real 1-based PDF page number
    return [(p["metadata"]["page_number"], p["text"]) for p in pages]


def clean_name(name):
    """Remove Markdown bold markers (**) and extra spaces from a section name."""
    return name.replace("**", "").strip()


def split_into_sections(text):
    """Split one page at Markdown headings. Returns (section_name, body) pairs."""
    sections = []
    current_name = "Front matter"    # used if text appears before any heading
    current_lines = []

    for line in text.split("\n"):
        # A Markdown heading starts with one to four '#' characters and a space
        if re.match(r"^#{1,4} ", line):
            if current_lines:
                sections.append((current_name, "\n".join(current_lines).strip()))
            current_name = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_name, "\n".join(current_lines).strip()))
    return [s for s in sections if s[1]]    # drop empty sections


def split_long_text(body):
    """Cut a long section into pieces of about MAX_CHARS, at paragraph breaks.
    A paragraph that starts with '|' (a table) is never cut in the middle."""
    paragraphs = body.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if current and len(current) + len(para) > MAX_CHARS and not para.lstrip().startswith("|"):
            chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para) if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def build_chunks(entry):
    """Turn one document's pages into chunk records, each with its own label and title."""
    records = []
    for pdf_page, text in load_pages(entry):
        for section_name, body in split_into_sections(text):
            section_name = clean_name(section_name)
            for piece in split_long_text(body):
                # If the chunk holds a table caption, use it as the section label.
                # It's the report's own wording, so the search can match it.
                caption_match = re.search(r"Table \d+\.[^\n]*", piece)
                label = clean_name(caption_match.group(0)) if caption_match else section_name

                breadcrumb = f"{entry['title']} > {label} (PDF p. {pdf_page})"
                records.append({
                    "text": f"{breadcrumb}\n{piece}",
                    "metadata": {
                        "source_label": entry["label"],
                        "doc_title": entry["title"],
                        "section_path": label,
                        "page_start": pdf_page,
                        "page_end": pdf_page,
                    },
                })
    return records


def save_to_chroma(records):
    """Save all chunks from all documents into one ChromaDB collection."""
    client = chromadb.PersistentClient(path=DB_PATH)

    # Start clean so re-running doesn't create duplicates
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass    # collection didn't exist yet, which is fine

    collection = client.create_collection(COLLECTION_NAME)    # default embedding function
    collection.add(
        ids=[f"chunk_{i}" for i in range(len(records))],
        documents=[r["text"] for r in records],
        metadatas=[r["metadata"] for r in records],
    )
    return len(records)


if __name__ == "__main__":
    print(f"Reading PDFs from: {NASA_FOLDER}")

    all_records = []
    for entry in MANIFEST:
        if not (NASA_FOLDER / entry["file"]).exists():
            print(f"SKIPPED (file not found): {entry['file']}")
            continue
        records = build_chunks(entry)
        print(f"{entry['label']}: {len(records)} chunks")
        all_records.extend(records)

    print("-" * 60)
    print(f"Total chunks: {len(all_records)}")

    # Stop here if nothing was read. Saving an empty list crashes ChromaDB.
    if not all_records:
        print("No chunks created. Check that the PDFs are in nasa_docs\\ with the exact names.")
        raise SystemExit(1)

    # Show the first chunk of each document so you can check the structure
    for entry in MANIFEST:
        matches = [r for r in all_records if r["metadata"]["source_label"] == entry["label"]]
        if matches:
            print("-" * 60)
            print(matches[0]["metadata"])
            print(matches[0]["text"][:200], "...")

    saved = save_to_chroma(all_records)
    print("=" * 60)
    print(f"Saved {saved} chunks to {DB_PATH}")