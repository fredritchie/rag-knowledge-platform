# Development Corpus

`manifest.csv` contains the curated 50-PDF development set prepared for this project.

Download it with:

```bash
make corpus
```

Progress through the corpus in gates:

1. First 10 PDFs: parsing/chunking foundation.
2. First 20 PDFs: broader technical paper variation.
3. All 50 PDFs: standards, similar RFCs, reports/manuals, tables, figures, and long documents.

The downloaded PDFs are intentionally excluded from Git by `.gitignore`.
