"""Offline extraction benchmark: score the pipeline against hand-checked pages.

Usage (from ``backend/``)::

    python -m bench.run_bench --label baseline

Each ``bench/truth/*.json`` file names a PDF and, per page, the expected grid.
Truth grids are faithful to the source table, with one convention: a cell
merged over several rows is repeated on every row it spans.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
REPO_DIR = BENCH_DIR.parent.parent
WORK_DIR = REPO_DIR / "data" / "bench"

# Must be set before ``app`` is imported: settings are read once, at import.
os.environ.setdefault("DATA_DIR", str(WORK_DIR))
_LOCAL_TESSDATA = REPO_DIR / "data" / "tessdata"
if _LOCAL_TESSDATA.is_dir():
    os.environ.setdefault("TESSDATA_PREFIX", str(_LOCAL_TESSDATA))

from app.config import get_settings  # noqa: E402
from app.services import pdf, pipeline  # noqa: E402

CLOSE_RATIO = 0.9

TextGrid = list[list[str]]


def _norm(text: str) -> str:
    """Reduce a cell to lowercase unaccented alphanumerics for comparison."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isalnum()).casefold()


def _similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _row_similarity(truth: list[str], pred: list[str]) -> float:
    width = max(len(truth), len(pred))
    total = 0.0
    for c in range(width):
        t = truth[c] if c < len(truth) else ""
        p = pred[c] if c < len(pred) else ""
        total += _similarity(t, p)
    return total / width if width else 0.0


def _align_rows(truth: TextGrid, pred: TextGrid) -> list[int | None]:
    """Align truth rows to predicted rows, preserving order.

    Returns, for each truth row, the index of its predicted row or None.
    """
    n, m = len(truth), len(pred)
    sim = [[_row_similarity(t, p) for p in pred] for t in truth]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best[i][j] = max(
                best[i - 1][j], best[i][j - 1], best[i - 1][j - 1] + sim[i - 1][j - 1]
            )

    mapping: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        if best[i][j] == best[i - 1][j - 1] + sim[i - 1][j - 1] and sim[i - 1][j - 1] > 0:
            mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return mapping


def score_page(truth: TextGrid, pred: TextGrid) -> dict[str, int]:
    """Compare a predicted grid against its truth grid.

    Returns counts: non-empty truth ``cells``, how many are ``exact`` or
    ``close``, truth ``rows`` and how many are entirely right (``rows_ok``).
    """
    truth_n = [[_norm(c) for c in row] for row in truth]
    pred_n = [[_norm(c) for c in row] for row in pred]
    mapping = _align_rows(truth_n, pred_n)

    stats = {"cells": 0, "exact": 0, "close": 0, "rows": len(truth_n), "rows_ok": 0}
    for row, target in zip(truth_n, mapping):
        pred_row = pred_n[target] if target is not None else []
        row_ok = target is not None
        for c in range(max(len(row), len(pred_row))):
            t = row[c] if c < len(row) else ""
            p = pred_row[c] if c < len(pred_row) else ""
            if t != p:
                row_ok = False
            if not t:
                continue
            stats["cells"] += 1
            if t == p:
                stats["exact"] += 1
                stats["close"] += 1
            elif _similarity(t, p) >= CLOSE_RATIO:
                stats["close"] += 1
        stats["rows_ok"] += int(row_ok)
    return stats


def _pct(part: int, total: int) -> str:
    return f"{100 * part / total:5.1f}%" if total else "   n/a"


def run(label: str, only: str | None, language: str) -> dict:
    """Run the benchmark and return the full report."""
    settings = get_settings()
    settings.ensure_dirs()
    dump_dir = WORK_DIR / "out" / label
    dump_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {"label": label, "language": language, "sources": {}}
    for truth_path in sorted((BENCH_DIR / "truth").glob("*.json")):
        truth_doc = json.loads(truth_path.read_text(encoding="utf-8"))
        source = truth_doc["source"]
        if only and only != source:
            continue

        pdf_path = REPO_DIR / truth_doc["pdf"]
        pages_dir = WORK_DIR / "pages" / f"{source}-{settings.ocr_dpi}"
        images = sorted(pages_dir.glob("*.png"))
        if not images:
            images = pdf.pdf_to_images(pdf_path, pages_dir, dpi=settings.ocr_dpi)

        totals = {"cells": 0, "exact": 0, "close": 0, "rows": 0, "rows_ok": 0}
        pages: dict[str, dict] = {}
        elapsed = 0.0
        for page_no, truth_grid in truth_doc["pages"].items():
            started = time.perf_counter()
            _, grid = pipeline.extract_page(
                images[int(page_no) - 1],
                language=language,
                preprocessing=True,
                tables_only=settings.extract_tables_only,
            )
            seconds = time.perf_counter() - started
            elapsed += seconds

            pred = [[text for text, _conf in row] for row in grid]
            (dump_dir / f"{source}_p{page_no}.json").write_text(
                json.dumps(pred, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            stats = score_page(truth_grid, pred)
            stats["seconds"] = round(seconds, 1)
            stats["pred_shape"] = [len(pred), max((len(r) for r in pred), default=0)]
            pages[page_no] = stats
            for key in totals:
                totals[key] += stats[key]

        totals["seconds_per_page"] = round(elapsed / max(len(pages), 1), 1)
        report["sources"][source] = {"total": totals, "pages": pages}

    (WORK_DIR / "results").mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "results" / f"{label}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return report


def print_report(report: dict) -> None:
    """Print a per-page and per-source summary table."""
    print(f"\n=== {report['label']} (lang={report['language']}) ===")
    print(f"{'source':<14}{'page':>5}{'exact':>8}{'proche':>8}{'lignes':>8}{'s':>7}  forme")
    grand = {"cells": 0, "exact": 0, "close": 0, "rows": 0, "rows_ok": 0}
    for source, data in report["sources"].items():
        for page_no, s in data["pages"].items():
            print(
                f"{source:<14}{page_no:>5}{_pct(s['exact'], s['cells']):>8}"
                f"{_pct(s['close'], s['cells']):>8}{_pct(s['rows_ok'], s['rows']):>8}"
                f"{s['seconds']:>7}  {s['pred_shape'][0]}x{s['pred_shape'][1]}"
            )
        t = data["total"]
        print(
            f"{source:<14}{'TOT':>5}{_pct(t['exact'], t['cells']):>8}"
            f"{_pct(t['close'], t['cells']):>8}{_pct(t['rows_ok'], t['rows']):>8}"
            f"{t['seconds_per_page']:>7}"
        )
        for key in grand:
            grand[key] += t[key]
    print(
        f"{'GLOBAL':<14}{'':>5}{_pct(grand['exact'], grand['cells']):>8}"
        f"{_pct(grand['close'], grand['cells']):>8}{_pct(grand['rows_ok'], grand['rows']):>8}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--label", default="run", help="name of this run's result file")
    parser.add_argument("--only", default=None, help="restrict to one source")
    parser.add_argument("--lang", default=get_settings().tesseract_lang)
    args = parser.parse_args()
    print_report(run(args.label, args.only, args.lang))


if __name__ == "__main__":
    main()
