# survey_pdfs.py - inspects every PDF in nasa_docs/ and writes survey.txt
# Run once. Then send me survey.txt (or paste its contents).
import pymupdf
from pathlib import Path

out = []
for pdf_path in sorted(Path("../nasa_docs").glob("*.pdf")):
    doc = pymupdf.open(pdf_path)
    out.append(f"FILE: {pdf_path.name} | pages: {len(doc)}")

    toc = doc.get_toc()
    if toc:
        for level, title, page in toc[:25]:
            out.append(f"  TOC L{level} p{page}: {title[:80]}")
    else:
        out.append("  TOC: none")

    # Text layer check on the middle page
    mid = doc[len(doc) // 2].get_text().strip()
    out.append(f"  text layer: {'OK' if len(mid) > 100 else 'WARNING, may need OCR'}")
    out.append("")

Path("../survey.txt").write_text("\n".join(out), encoding="utf-8")
print("Wrote survey.txt")