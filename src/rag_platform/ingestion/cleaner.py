from __future__ import annotations

import re
import unicodedata

_HYPHENATED_LINE_BREAK = re.compile(r"(?<=\w)-\n(?=\w)")
_SINGLE_LINE_BREAK = re.compile(r"(?<!\n)\n(?!\n)")
_MANY_SPACES = re.compile(r"[ \t]+")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize extracted PDF text while retaining paragraph boundaries."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHENATED_LINE_BREAK.sub("", text)
    text = _SINGLE_LINE_BREAK.sub(" ", text)
    text = _MANY_SPACES.sub(" ", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()
