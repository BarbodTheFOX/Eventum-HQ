"""Persian text normalization (handoff §4.9).

ي → ی, ك → ک, remove zero-width non-joiner (نیم‌فاصله) and diacritics (اعراب),
convert Persian/Arabic digits to Latin.
"""

from __future__ import annotations

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
# Arabic diacritics (fathatan..sukun, superscript alef, etc.) and tatweel
_DIACRITICS_RE = re.compile("[ً-ٰٟـ]")
_ZERO_WIDTH_RE = re.compile("[‌‍‎‏﻿]")
_SPACES_RE = re.compile(r"\s+")


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def normalize_text(text: str) -> str:
    """Normalize for storage/search: letters, digits, no ZWNJ/diacritics, lower, single spaces."""
    text = normalize_digits(text).translate(_LETTERS)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _DIACRITICS_RE.sub("", text)
    return _SPACES_RE.sub(" ", text).strip().lower()
