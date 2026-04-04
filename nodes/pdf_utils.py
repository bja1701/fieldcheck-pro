"""
Shared PDF utilities for extract_plans and extract_cabinets nodes.

Subprocesses:
  pdfinfo   — page count
  pdftotext — all-page text extraction (form-feed separated)
  pdftoppm  — page-to-image conversion (JPEG or PNG)
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def get_page_count(pdf_path: str) -> int:
    """Return total page count via pdfinfo."""
    result = subprocess.run(
        ["pdfinfo", pdf_path],
        capture_output=True, text=True, check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"Could not determine page count from pdfinfo: {pdf_path}")


def extract_all_text(pdf_path: str, page_count: int) -> dict[int, str]:
    """Extract text from all pages in one pdftotext call. Returns {page_num: text}."""
    result = subprocess.run(
        ["pdftotext", pdf_path, "-"],
        capture_output=True, text=True,
    )
    pages = result.stdout.split("\f")
    return {i + 1: pages[i] for i in range(page_count)}


def convert_pdf_pages(
    pdf_path: str,
    images_dir: Path,
    page_count: int,
    fmt: str,         # "jpeg" or "png"
    name_prefix: str, # e.g. "plan-" or "page-"
    subdir: str,      # e.g. "plan_images" or "cabinet_images"
) -> dict[int, str]:
    """
    Convert all PDF pages to images via pdftoppm.
    Returns {page_num: relative_path} e.g. {1: "plan_images/plan-01.jpg"}
    """
    tmp_prefix = str(images_dir / "_tmp")
    flag = "-jpeg" if fmt == "jpeg" else "-png"
    ext = "jpg" if fmt == "jpeg" else "png"

    subprocess.run(
        ["pdftoppm", "-r", "150", flag, pdf_path, tmp_prefix],
        capture_output=True, check=True,
    )

    digit_count = len(str(page_count))
    page_images: dict[int, str] = {}

    for page_num in range(1, page_count + 1):
        src_name = f"_tmp-{page_num:0{digit_count}d}.{ext}"
        src = images_dir / src_name
        if not src.exists():
            continue
        dst_name = f"{name_prefix}{page_num:02d}.{ext}"
        dst = images_dir / dst_name
        src.rename(dst)
        page_images[page_num] = f"{subdir}/{dst_name}"

    return page_images
