"""Unit tests for services that run without Tesseract/Poppler installed."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from app.services import excel, pdf, table
from app.services.ocr import OcrResult, Word


def test_is_valid_pdf() -> None:
    assert pdf.is_valid_pdf(b"%PDF-1.7\n...")
    assert not pdf.is_valid_pdf(b"PK\x03\x04")  # a zip/xlsx, not a pdf
    assert not pdf.is_valid_pdf(b"")


def _word(text: str, left: int, line: int, conf: float = 90.0) -> Word:
    return Word(
        text=text,
        confidence=conf,
        left=left,
        top=line * 30,
        width=len(text) * 10,
        height=20,
        line_num=line,
        block_num=1,
        par_num=1,
    )


def test_structure_by_lines_fallback(tmp_path: Path) -> None:
    """With no grid image, structuring falls back to line-by-line splitting."""
    words = [
        _word("Name", left=0, line=1),
        _word("Age", left=300, line=1),
        _word("Alice", left=0, line=2),
        _word("30", left=300, line=2),
    ]
    result = OcrResult(text="Name Age\nAlice 30", words=words, mean_confidence=90.0)
    # Point at a non-existent image so grid detection yields nothing.
    grid = table.structure_page(tmp_path / "missing.png", result)

    assert len(grid) == 2
    assert grid[0][0][0] == "Name"
    assert grid[0][1][0] == "Age"
    assert grid[1][0][0] == "Alice"
    assert grid[1][1][0] == "30"


def test_export_xlsx_one_sheet_per_page(tmp_path: Path) -> None:
    pages = [
        [["A", "B"], ["1", "2"]],
        [["C", "D"], ["3", "4"]],
    ]
    out = tmp_path / "out.xlsx"
    excel.export_xlsx(pages, out, merge=False)

    workbook = openpyxl.load_workbook(out)
    assert workbook.sheetnames == ["Page 1", "Page 2"]
    assert workbook["Page 1"]["A1"].value == "A"
    assert workbook["Page 1"]["A1"].font.bold
    assert workbook["Page 2"]["B2"].value == "4"


def test_export_xlsx_merged(tmp_path: Path) -> None:
    pages = [[["A"]], [["B"]]]
    out = tmp_path / "merged.xlsx"
    excel.export_xlsx(pages, out, merge=True)

    workbook = openpyxl.load_workbook(out)
    assert workbook.sheetnames == ["Extraction"]
    assert workbook["Extraction"]["A1"].value == "A"
    assert workbook["Extraction"]["A2"].value == "B"


def test_export_csv_bom_and_delimiter() -> None:
    pages = [[["a", "b"], ["c", "d"]]]
    content = excel.export_csv(pages, delimiter=";")
    assert content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    text = content.decode("utf-8-sig")
    assert "a;b" in text
    assert "c;d" in text
