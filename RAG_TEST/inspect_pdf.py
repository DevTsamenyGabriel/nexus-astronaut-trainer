# inspect_pdf.py - checks each PDF before we chunk it
# First install: pip install pymupdf
import fitz  # PyMuPDF
from pathlib import Path

for pdf_path in sorted(Path("../nasa_docs").glob("*.pdf")):
    doc = fitz.open(pdf_path)
    print("=" * 70)
    print(f"FILE: {pdf_path.name}")
    print(f"Pages: {len(doc)}")

    # Table of contents: section names with their real page numbers
    toc = doc.get_toc()
    if toc:
        print("Table of contents (first 15 entries):")
        for level, title, page in toc[:15]:
            print(f"  {'  ' * (level - 1)}{title}  -> page {page}")
    else:
        print("No table of contents found. Use the first page text to find headings.")

    # Text layer check: is the text selectable or is it a scanned image?
    sample_text = doc[min(5, len(doc) - 1)].get_text()
    if len(sample_text.strip()) > 100:
        print("Text layer: OK (selectable text found)")
    else:
        print("Text layer: WARNING, little or no text. May need OCR.")