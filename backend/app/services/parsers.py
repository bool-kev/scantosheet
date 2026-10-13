"""Value parsers turning raw table-cell text into import-ready fields.

Each parser takes the text of a source cell — as printed, with OCR flaws —
and returns the canonical value, or an empty string when nothing usable is
found. They are deliberately tolerant: the same field is written many ways
across sources (``07h30-09h``, ``7h30-9h``; ``Jury N°1``, ``JURY I``).
"""

from __future__ import annotations

import re
import unicodedata

ALL_CANDIDATES = "Tous les candidats"

_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}  # fmt: skip

_NUMERIC_DATE = re.compile(r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})")
_WORDED_DATE = re.compile(r"(\d{1,2})\s*(?:er)?\s+([a-z]+)\s+(\d{4})")
_TIME_RANGE = re.compile(
    r"(\d{1,2})\s*h\s*(\d{2})?\s*(?:-|–|—|a|au)\s*(\d{1,2})\s*h\s*(\d{2})?"
)
# "matin" / "soir", allowing the usual misreadings of their letter i.
_MORNING = re.compile(r"\bmat[il1|!]n\b")
_EVENING = re.compile(r"\bso[il1t|!]r\b")
_JURY_PART = re.compile(r"/?\s*jury\b.*$", re.IGNORECASE | re.DOTALL)
_NUMBER_SIGN = re.compile(r"^n\s*[°ºo*]\s*", re.IGNORECASE)
_RECEIPT_NUMBER = re.compile(r"\d{4,}")

# Characters a lone roman "I" is commonly read as.
_ROMAN_ONE = frozenset("Il|!1Ti")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}


def fold(text: str) -> str:
    """Lowercase a text and strip its accents, keeping spaces and punctuation."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def clean(text: str) -> str:
    """Collapse whitespace and rejoin words split around a hyphen."""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"(?<=\w)- (?=\w)", "-", text)


def parse_date(text: str) -> str:
    """Return the first date found in ``text`` as ``dd/mm/yyyy``, else ``""``."""
    folded = fold(text)
    match = _NUMERIC_DATE.search(folded)
    if match:
        day, month, year = (int(g) for g in match.groups())
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{day:02d}/{month:02d}/{year}"
    for match in _WORDED_DATE.finditer(folded):
        month = _MONTHS.get(match.group(2))
        if month and 1 <= int(match.group(1)) <= 31:
            return f"{int(match.group(1)):02d}/{month:02d}/{match.group(3)}"
    return ""


def parse_horaire(text: str) -> str:
    """Return a time range as ``HHhMM-HHhMM``, else ``MATIN``/``SOIR``, else ``""``."""
    folded = fold(text)
    # A date such as 15/07/2026 must not be mistaken for part of a time.
    folded = _NUMERIC_DATE.sub(" ", folded)
    match = _TIME_RANGE.search(folded)
    if match:
        h1, m1, h2, m2 = match.groups()
        if int(h1) < 24 and int(h2) < 24:
            return f"{int(h1):02d}h{m1 or '00'}-{int(h2):02d}h{m2 or '00'}"
    has_morning = _MORNING.search(folded) is not None
    has_evening = _EVENING.search(folded) is not None
    if has_morning != has_evening:
        return "MATIN" if has_morning else "SOIR"
    return ""


def parse_lieu(text: str) -> str:
    """Return the venue, dropping a trailing ``/JURY …`` part if present."""
    return clean(_JURY_PART.sub("", text)).strip(" /-")


def _roman_to_int(token: str) -> int | None:
    letters = ["I" if ch in _ROMAN_ONE else ch.upper() for ch in token]
    if not letters or any(ch not in _ROMAN_VALUES for ch in letters):
        return None
    total = 0
    for i, ch in enumerate(letters):
        value = _ROMAN_VALUES[ch]
        following = _ROMAN_VALUES[letters[i + 1]] if i + 1 < len(letters) else 0
        total += -value if value < following else value
    return total if total > 0 else None


def parse_jury(text: str) -> str:
    """Return the jury number as arabic digits, else ``""``.

    Accepts ``Jury N°1``, ``JURY II``, ``YAMWAYA /JURY I`` or a bare ``II``.
    A roman numeral is counted stroke by stroke, so the usual misreadings of
    ``I`` (``l``, ``|``, ``!``, ``1``, ``T``) still give the right number.
    """
    cleaned = clean(text)
    match = re.search(r"jury\b(.*)$", cleaned, re.IGNORECASE | re.DOTALL)
    token = (match.group(1) if match else cleaned).strip(" :./-")
    numbered = _NUMBER_SIGN.match(token) is not None
    token = _NUMBER_SIGN.sub("", token).replace(" ", "")
    if not token:
        return ""
    if numbered and token.isdigit():
        return str(int(token))
    value = _roman_to_int(token)
    if value is not None:
        return str(value)
    return str(int(token)) if token.isdigit() else ""


def parse_tranche(text: str) -> tuple[str, str, str]:
    """Split a candidate range into ``(label, first, last)``.

    ``De Récépissé N°000023 à N°029985`` gives
    ``("000023-029985", "000023", "029985")``; any wording of "all candidates"
    gives ``("Tous les candidats", "", "")``. Unrecognised text gives
    ``("", "", "")``.
    """
    numbers = _RECEIPT_NUMBER.findall(text)
    if len(numbers) >= 2:
        return f"{numbers[0]}-{numbers[1]}", numbers[0], numbers[1]
    if "candidat" in fold(text):
        return ALL_CANDIDATES, "", ""
    return "", "", ""
