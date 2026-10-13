"""Show the cells where a benchmark run differs from the truth.

Usage (from ``backend/``)::

    python -m bench.diff baseline [source]
"""

from __future__ import annotations

import json
import sys

from bench.run_bench import BENCH_DIR, WORK_DIR, _align_rows, _norm


def main() -> None:
    label = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else None
    for truth_path in sorted((BENCH_DIR / "truth").glob("*.json")):
        doc = json.loads(truth_path.read_text(encoding="utf-8"))
        if only and doc["source"] != only:
            continue
        for page_no, truth in doc["pages"].items():
            pred_path = WORK_DIR / "out" / label / f"{doc['source']}_p{page_no}.json"
            pred = json.loads(pred_path.read_text(encoding="utf-8"))
            mapping = _align_rows(
                [[_norm(c) for c in r] for r in truth], [[_norm(c) for c in r] for r in pred]
            )
            for r, (row, target) in enumerate(zip(truth, mapping)):
                pred_row = pred[target] if target is not None else []
                for c, expected in enumerate(row):
                    got = pred_row[c] if c < len(pred_row) else ""
                    if _norm(expected) != _norm(got):
                        print(f"{doc['source']} p{page_no} r{r} c{c}\n   attendu: {expected}\n   obtenu : {got}")


if __name__ == "__main__":
    main()
