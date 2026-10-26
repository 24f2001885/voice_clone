"""Passage and sentence text splitter bounded by character limits."""
from __future__ import annotations

import re

from voxclone.errors import InvalidTextError

_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?;\n])\s+")


def split_text_into_chunks(text: str, max_chars: int = 200) -> list[str]:
    """Split input text into clean sentences or clauses each bounded by max_chars.

    Raises:
        InvalidTextError: If text is empty, pure whitespace, or contains invalid tokens.
    """
    if not text or not text.strip():
        raise InvalidTextError(
            "Input text cannot be empty or pure whitespace.",
        )

    # Normalize carriage returns and multiple blank lines
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Split initial text by sentence-terminating punctuation
    raw_sentences = [s.strip() for s in _SENTENCE_SPLIT_REGEX.split(normalized) if s.strip()]
    if not raw_sentences:
        raise InvalidTextError("Input text contains no readable sentences.")

    chunks: list[str] = []

    for sentence in raw_sentences:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue

        # If sentence exceeds max_chars, split on sub-sentence pauses (comma, dash) or spaces
        words = sentence.split(" ")
        current_chunk: list[str] = []
        current_len = 0

        for word in words:
            word_len = len(word)
            added_len = word_len if not current_chunk else word_len + 1

            if current_len + added_len <= max_chars:
                current_chunk.append(word)
                current_len += added_len
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk).strip())
                current_chunk = [word]
                current_len = word_len

        if current_chunk:
            chunks.append(" ".join(current_chunk).strip())

    return [c for c in chunks if c]
