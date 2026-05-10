# Run Marker on all PDFs in legal_corpus/.
# Outputs Markdown to legal_corpus_md/.
# Run ONCE on Day 1 evening before build_index.py.
# Requires: pip install marker-pdf

$ErrorActionPreference = "Stop"

$CORPUS_DIR = "legal_corpus"
$OUTPUT_DIR = "legal_corpus_md"

New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

$pdfs = Get-ChildItem -Path $CORPUS_DIR -Filter "*.pdf"

if ($pdfs.Count -eq 0) {
    Write-Host "ERROR: No PDF files found in $CORPUS_DIR/"
    Write-Host "Place your legal PDFs there first:"
    Write-Host "  - constitution_pakistan.pdf"
    Write-Host "  - ppc_1860.pdf"
    Write-Host "  - crpc_1898.pdf"
    Write-Host "  - cpc_1908.pdf"
    exit 1
}

Write-Host "Running Marker on all PDFs in $CORPUS_DIR/..."
Write-Host "This will take 15-60 minutes on CPU. Leave it running.`n"

foreach ($pdf in $pdfs) {
    $filename = $pdf.BaseName
    Write-Host "Processing: $($pdf.FullName)"
    marker_single "$($pdf.FullName)" --output_dir "$OUTPUT_DIR/" --langs English
    Write-Host "  Done: $OUTPUT_DIR/$filename/$filename.md`n"
}

Write-Host "========================================"
Write-Host "Marker conversion complete!"
Write-Host "IMPORTANT: Manually verify these articles in the output:"
Write-Host "  Constitution: Articles 1, 9, 10, 10-A, 25, 25-A, 199, 232"
Write-Host "  PPC: Sections 299, 300, 302, 320, 364-A"
Write-Host "  CrPC: Sections 54, 61, 167, 496, 497, 498`n"
Write-Host "Fix any garbled articles with a text editor, then run:"
Write-Host "  python scripts/build_index.py"
Write-Host "========================================"
