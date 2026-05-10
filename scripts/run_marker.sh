#!/bin/bash
# Run Marker on all PDFs in legal_corpus/.
# Outputs Markdown to legal_corpus_md/.
# Run ONCE on Day 1 evening before build_index.py.
# Requires: pip install marker-pdf

set -e

CORPUS_DIR="legal_corpus"
OUTPUT_DIR="legal_corpus_md"

mkdir -p "$OUTPUT_DIR"

if [ -z "$(ls -A $CORPUS_DIR/*.pdf 2>/dev/null)" ]; then
  echo "ERROR: No PDF files found in $CORPUS_DIR/"
  echo "Place your legal PDFs there first:"
  echo "  - constitution_pakistan.pdf"
  echo "  - ppc_1860.pdf"
  echo "  - crpc_1898.pdf"
  echo "  - cpc_1908.pdf"
  exit 1
fi

echo "Running Marker on all PDFs in $CORPUS_DIR/..."
echo "This will take 15-60 minutes on CPU. Leave it running."
echo ""

for pdf in "$CORPUS_DIR"/*.pdf; do
  filename=$(basename "$pdf" .pdf)
  echo "Processing: $pdf"
  marker_single "$pdf" --output_dir "$OUTPUT_DIR/" --langs English
  echo "  Done: $OUTPUT_DIR/$filename/$filename.md"
  echo ""
done

echo "========================================"
echo "Marker conversion complete!"
echo "IMPORTANT: Manually verify these articles in the output:"
echo "  Constitution: Articles 1, 9, 10, 10-A, 25, 25-A, 199, 232"
echo "  PPC: Sections 299, 300, 302, 320, 364-A"
echo "  CrPC: Sections 54, 61, 167, 496, 497, 498"
echo ""
echo "Fix any garbled articles with a text editor, then run:"
echo "  python scripts/build_index.py"
echo "========================================"
