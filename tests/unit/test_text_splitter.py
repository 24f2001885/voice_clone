"""Unit tests for text passage splitter."""
from __future__ import annotations

import pytest

from voxclone.errors import InvalidTextError
from voxclone.pipelines.text_splitter import split_text_into_chunks


def test_split_empty_text_raises_invalid_text() -> None:
    """Empty or pure whitespace text must raise InvalidTextError (VX-201)."""
    with pytest.raises(InvalidTextError) as exc_info:
        split_text_into_chunks("")
    assert exc_info.value.code == "VX-201"

    with pytest.raises(InvalidTextError) as exc_info2:
        split_text_into_chunks("   \n\t  ")
    assert exc_info2.value.code == "VX-201"


def test_split_single_short_sentence() -> None:
    """A sentence well within the character limit is returned as a single chunk."""
    text = "Hello world, this is a test of voice synthesis."
    chunks = split_text_into_chunks(text, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_multiple_sentences_by_punctuation() -> None:
    """Sentences ending with period, exclamation, or question mark are split."""
    text = "First sentence here. Second sentence starts! What about the third? Yes, done."
    chunks = split_text_into_chunks(text, max_chars=200)
    assert len(chunks) == 4
    assert chunks[0] == "First sentence here."
    assert chunks[1] == "Second sentence starts!"
    assert chunks[2] == "What about the third?"
    assert chunks[3] == "Yes, done."


def test_split_long_sentence_bounded_by_max_chars() -> None:
    """Sentences longer than max_chars are divided into word sub-chunks."""
    words = ["word"] * 50
    long_sentence = " ".join(words) + "."
    chunks = split_text_into_chunks(long_sentence, max_chars=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 50
        assert len(chunk) > 0

    reconstructed = " ".join(chunks)
    assert reconstructed == long_sentence
