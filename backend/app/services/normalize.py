"""Normalization: map extracted tables onto the fixed import schema.

Every source lays the same information out differently — one puts the date in
a column, another in a banner row across the table; one has a ``JURY/LIEU``
column, another two separate ones. This module recognises each source column
from its header (see ``target_schema.json``), parses the values with
``parsers`` and produces one uniform row per exam session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.logging_config import get_logger
from app.services import parsers

log = get_logger(__name__)

_DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "target_schema.json"
# How closely a printed header must match a schema synonym to be recognised.
_HEADER_SIMILARITY = 0.8

TextGrid = list[list[str]]
# For one page: the schema fields fed by each source column (None = unknown).
ColumnMap = list[list[str] | None]


@dataclass
class Schema:
    """The import schema: output columns and the header synonyms feeding them."""

    columns: list[str]
    headers: list[tuple[list[str], list[str]]]  # (folded synonyms, fields)


@dataclass
class NormalizedRow:
    """One import-ready row."""

    values: dict[str, str]
    page: int
    doubtful: list[str] = field(default_factory=list)


@dataclass
class NormalizedTable:
    """The normalized content of a whole document."""

    columns: list[str]
    rows: list[NormalizedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _key(text: str) -> str:
    """Reduce a header to folded alphanumerics for comparison."""
    return "".join(c for c in parsers.fold(text) if c.isalnum())


@lru_cache
def load_schema(path: Path | None = None) -> Schema:
    """Load the import schema from ``path`` (default: the bundled schema)."""
    raw = json.loads((path or _DEFAULT_SCHEMA).read_text(encoding="utf-8"))
    headers = [([_key(m) for m in entry["match"]], entry["fields"]) for entry in raw["headers"]]
    return Schema(columns=raw["columns"], headers=headers)


def _match_header(text: str, schema: Schema) -> list[str] | None:
    """Return the fields a printed header feeds, or None if unrecognised."""
    key = _key(text)
    if not key:
        return None
    best_score, best_fields = 0.0, None
    for synonyms, fields in schema.headers:
        for synonym in synonyms:
            score = 1.0 if key == synonym else SequenceMatcher(None, key, synonym).ratio()
            if score > best_score:
                best_score, best_fields = score, fields
    return best_fields if best_score >= _HEADER_SIMILARITY else None


def _map_header_row(row: list[str], schema: Schema) -> ColumnMap | None:
    """Map a row's cells to schema fields; None unless it is a header row."""
    mapping: ColumnMap = [_match_header(cell, schema) for cell in row]
    fed = {f for fields in mapping if fields for f in fields}
    return mapping if len(fed) >= 2 else None


def _field_text(row: list[str], mapping: ColumnMap, name: str) -> str:
    cells = [row[i] for i, fields in enumerate(mapping) if fields and name in fields and i < len(row)]
    return " ".join(c for c in cells if c)


def _is_total(row: list[str]) -> bool:
    return any(_key(cell).startswith(("soustotal", "total")) for cell in row)


def _build_row(row: list[str], mapping: ColumnMap, context_date: str, page: int) -> NormalizedRow | None:
    """Parse one data row; None if it carries no exam title."""
    concours = parsers.clean(_field_text(row, mapping, "concours"))
    if not concours:
        return None

    date_text = _field_text(row, mapping, "date")
    horaire_text = _field_text(row, mapping, "horaire")
    lieu_text = _field_text(row, mapping, "lieu")
    jury_text = _field_text(row, mapping, "jury")
    tranche_text = _field_text(row, mapping, "tranche")

    date = parsers.parse_date(date_text) or parsers.parse_date(horaire_text) or context_date
    horaire = parsers.parse_horaire(horaire_text) or parsers.parse_horaire(date_text)
    label, first, last = parsers.parse_tranche(tranche_text)
    values = {
        "date": date,
        "horaire": horaire,
        "concours": concours,
        "lieu": parsers.parse_lieu(lieu_text),
        "jury": parsers.parse_jury(jury_text),
        "tranche": label or parsers.clean(tranche_text),
        "tranche_debut": first,
        "tranche_fin": last,
    }
    doubtful = [name for name in ("date", "horaire", "lieu", "jury") if not values[name]]
    if not label:
        doubtful.append("tranche")
    return NormalizedRow(values=values, page=page, doubtful=doubtful)


def normalize_pages(pages: list[TextGrid], schema: Schema | None = None) -> NormalizedTable:
    """Normalize a document's page grids into import-ready rows.

    A page without a header row (a table continued from the previous page)
    reuses the previous page's column mapping when it has the same number of
    columns. A banner row holding only a date (``15 JUILLET 2026 : MATIN``)
    sets the date of the rows below it, across pages. Header, banner and
    sub-total rows produce no output row.

    Args:
        pages: One grid of cell texts per page, in page order.
        schema: The import schema; defaults to the configured one.

    Returns:
        The normalized table, with a warning for each page that could not be
        mapped. Fields that could not be parsed are listed in each row's
        ``doubtful``.
    """
    schema = schema or load_schema(get_settings().target_schema_path)
    result = NormalizedTable(columns=list(schema.columns))
    mapping: ColumnMap | None = None
    context_date = ""

    for page_number, grid in enumerate(pages, start=1):
        if not grid:
            continue
        width = max(len(row) for row in grid)
        page_has_header = any(_map_header_row(row, schema) for row in grid[:2])
        if not page_has_header and (mapping is None or len(mapping) != width):
            result.warnings.append(
                f"Page {page_number} : en-tête non reconnu, page ignorée dans la feuille Import."
            )
            mapping = None if not page_has_header else mapping
            continue

        for row in grid:
            header = _map_header_row(row, schema)
            if header is not None:
                mapping = header
                continue
            filled = [cell for cell in row if cell.strip()]
            if len(filled) == 1:  # banner row
                context_date = parsers.parse_date(filled[0]) or context_date
                continue
            if mapping is None or _is_total(row):
                continue
            built = _build_row(row, mapping, context_date, page_number)
            if built is not None:
                context_date = built.values["date"] or context_date
                result.rows.append(built)

    log.info("normalize.done", rows=len(result.rows), warnings=len(result.warnings))
    return result
