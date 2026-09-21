"""Deterministic readability metrics with no model or NLP-runtime dependency.

Implements the two metrics WEBSITE-AUDITOR historically consumed from textstat:
Flesch Reading Ease and Flesch-Kincaid Grade. Syllables use a documented,
deterministic English heuristic so results are reproducible offline.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE_RE = re.compile(r"[.!?]+")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(str(text or ""))


def _sentence_count(text: str) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    marks = len(_SENTENCE_RE.findall(value))
    return max(1, marks)


def _syllables_in_word(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    if len(word) <= 3:
        return 1

    groups = len(_VOWEL_GROUP_RE.findall(word))

    # Common silent-e adjustment, while preserving consonant+le endings.
    if word.endswith("e") and not word.endswith(("le", "ye")) and groups > 1:
        groups -= 1

    # -ed/-es are often silent after a consonant.
    if word.endswith(("ed", "es")) and groups > 1:
        stem = word[:-2]
        if stem and stem[-1] not in "aeiouy":
            groups -= 1

    return max(1, groups)


def _counts(text: str) -> tuple[int, int, int]:
    words = _words(text)
    word_count = len(words)
    if word_count == 0:
        return 0, 0, 0
    sentences = _sentence_count(text)
    syllables = sum(_syllables_in_word(word) for word in words)
    return word_count, sentences, syllables


def flesch_reading_ease(text: str) -> float:
    """Return Flesch Reading Ease using deterministic local syllable estimates."""
    words, sentences, syllables = _counts(text)
    if words == 0 or sentences == 0:
        return 0.0
    return 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)


def flesch_kincaid_grade(text: str) -> float:
    """Return Flesch-Kincaid Grade using deterministic local syllable estimates."""
    words, sentences, syllables = _counts(text)
    if words == 0 or sentences == 0:
        return 0.0
    return 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
