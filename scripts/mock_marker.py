import os
import re
from pathlib import Path
import fitz  # PyMuPDF

CORPUS_DIR = Path("legal_corpus")
OUTPUT_DIR = Path("legal_corpus_md")

OUTPUT_DIR.mkdir(exist_ok=True)

def looks_like_heading(line: str) -> bool:
    line = line.strip()
    if re.match(r'^(Article|Section)\s+\d+', line, re.IGNORECASE):
        return True
    if re.match(r'^\d{1,3}[A-Z]?(?:-[A-Z])?[.\s—\-]+[A-Z]', line):
        return True
    return False

def convert_pdf_to_md(pdf_path: Path):
    doc = fitz.open(pdf_path)
    text_blocks = []
    
    for page in doc:
        text = page.get_text("text")
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if looks_like_heading(line):
                text_blocks.append(f"\n\n## {line}\n")
            elif re.match(r'^PART\s+[IVXLC\d]+', line, re.IGNORECASE):
                text_blocks.append(f"\n\n# {line}\n")
            elif re.match(r'^CHAPTER\s+[\dIVXLC]+', line, re.IGNORECASE):
                text_blocks.append(f"\n\n# {line}\n")
            else:
                text_blocks.append(line + " ")
                
    out_dir = OUTPUT_DIR / pdf_path.stem
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{pdf_path.stem}.md"
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("".join(text_blocks))
    
    print(f"Mocked marker output for {pdf_path.name}")

def main():
    if not CORPUS_DIR.exists():
        print(f"No {CORPUS_DIR} found.")
        return
        
    pdfs = list(CORPUS_DIR.glob("*.pdf"))
    for pdf in pdfs:
        convert_pdf_to_md(pdf)

if __name__ == "__main__":
    main()
