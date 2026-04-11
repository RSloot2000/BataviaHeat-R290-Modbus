"""Convert all PDF files in the workspace root to .txt files."""
import pdfplumber
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
pdfs = list(workspace.glob("*.pdf"))

if not pdfs:
    print("Geen PDF bestanden gevonden in:", workspace)
    print("Zet de PDF's in deze map en run opnieuw.")
else:
    for pdf_path in pdfs:
        txt_path = pdf_path.with_suffix(".txt")
        print(f"Converteer: {pdf_path.name} -> {txt_path.name}")
        with pdfplumber.open(pdf_path) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    pages.append(f"--- Pagina {i} ---\n{text}")
                
                # Extract tables separately for better formatting
                tables = page.extract_tables()
                for t_idx, table in enumerate(tables):
                    rows = []
                    for row in table:
                        cells = [str(c) if c else "" for c in row]
                        rows.append(" | ".join(cells))
                    pages.append(f"\n[Tabel {t_idx+1} op pagina {i}]\n" + "\n".join(rows))
            
            txt_path.write_text("\n\n".join(pages), encoding="utf-8")
        print(f"  -> {len(pdf.pages)} pagina's geëxtraheerd")
    
    print(f"\nKlaar! {len(pdfs)} PDF('s) geconverteerd.")
