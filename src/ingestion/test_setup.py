from pathlib import Path

pdf_path = Path("data/raw/sample_product.pdf")

if pdf_path.exists():
    print("PDF found successfully!")
else:
    print("PDF not found.")