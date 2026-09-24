# SPDX-License-Identifier: Apache-2.0
"""Acronyms, a small toponym list, and English-looking tokens (AI-02, D-12).

Lists live in this module. Nothing is downloaded. An acronym is 2-5 ASCII
capitals that are not a known word, spelled with English letter names in
Polish orthography (``IT`` → ``aj ti``). A toponym wins over an acronym, and
an acronym wins over a foreign-word hit on the same span. The block is not
rewritten.

D-12's full public-domain wordlist is not vendored. A token is
``foreign_word`` when it has no Polish diacritic and either sits in the small
list below or carries English-only orthography (``th``, ``wh``, ``qu``,
``ck``, ``oo``, ``ee``, ``-ing``, ``-tion``, ``-ness``).
"""

from __future__ import annotations

import re

from praelector.domain.enums import SuggestionCategory
from praelector.text.suggestion import Suggestion, make_suggestion

# English letter names, written the way a Polish narrator says them.
_LETTER = {
    "A": "ej",
    "B": "bi",
    "C": "si",
    "D": "di",
    "E": "i",
    "F": "ef",
    "G": "dżi",
    "H": "ejcz",
    "I": "aj",
    "J": "dżej",
    "K": "kej",
    "L": "el",
    "M": "em",
    "N": "en",
    "O": "oł",
    "P": "pi",
    "Q": "kju",
    "R": "ar",
    "S": "es",
    "T": "ti",
    "U": "ju",
    "V": "vi",
    "W": "dablju",
    "X": "eks",
    "Y": "łaj",
    "Z": "zet",
}

# Uppercase tokens that are words or Roman numerals, not spelled acronyms.
_NOT_ACRONYMS = frozenset(
    {
        "NA",
        "OD",
        "DO",
        "PO",
        "WE",
        "ZE",
        "TO",
        "TU",
        "ON",
        "JA",
        "JE",
        "CO",
        "TAK",
        "NIE",
        "PAN",
        "ALE",
        "LUB",
        "JAK",
        "TEN",
        "TAM",
        "DWA",
        "STO",
        "RAZ",
        "ROK",
        "LAT",
        "DOM",
        "LAS",
        "NOC",
        "SYN",
        "MA",
        "MY",
        "WY",
        "ICH",
        "POD",
        "NAD",
        "DLA",
        "BEZ",
        "CZY",
        "OK",
        "THE",
        "AND",
        "FOR",
        "II",
        "III",
        "IV",
        "VI",
        "VII",
        "VIII",
        "IX",
        "XI",
        "XII",
        "XIII",
        "XIV",
        "XV",
        "XVI",
        "XVII",
        "XVIII",
        "XIX",
        "XX",
        "XXI",
        "XXX",
    }
)

# Hand-written. Longer surfaces are matched first so „Washington DC” wins.
_TOPONYMS: tuple[tuple[str, str], ...] = (
    ("Washington D.C.", "Łoszynkton di si"),
    ("Washington DC", "Łoszynkton di si"),
    ("Nowy Jork", "Nowy Jork"),
    ("Los Angeles", "Los Andżeles"),
    ("Washington", "Łoszynkton"),
    ("Warszawa", "Warszawa"),
)

_ENGLISH_WORDS = frozenset(
    {
        "deadline",
        "walker",
        "briefing",
        "meeting",
        "manager",
        "office",
        "email",
        "laptop",
        "software",
        "weekend",
        "design",
        "marketing",
        "feedback",
        "business",
        "online",
        "update",
        "workshop",
        "please",
        "thanks",
        "sorry",
        "hello",
        "clock",
    }
)
_FOREIGN_SPOKEN = {
    "walker": "Łoker",
    "deadline": "dedlajn",
}
_RESPELL: tuple[tuple[str, str], ...] = (
    ("tion", "szyn"),
    ("ness", "nes"),
    ("ee", "i"),
    ("oo", "u"),
    ("th", "t"),
    ("wh", "ł"),
    ("qu", "kw"),
    ("ck", "k"),
    ("ing", "ing"),
)

_POLISH = frozenset("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
_EN_ORTH = re.compile(r"(?:th|wh|qu|ck|oo|ee)|(?:ing|tion|ness)$", re.IGNORECASE)
_ACRONYM = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])")
_WORD = re.compile(r"[A-Za-zÀ-ž]+(?:['\u2019-][A-Za-zÀ-ž]+)*")

_TOPONYM_RES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (
        re.compile(
            r"(?<!\w)" + r"\s+".join(re.escape(part) for part in surface.split()) + r"(?!\w)",
            re.IGNORECASE,
        ),
        spoken,
    )
    for surface, spoken in sorted(_TOPONYMS, key=lambda item: len(item[0]), reverse=True)
)


def spell_acronym(token: str) -> str:
    """``IT`` → ``aj ti``."""
    return " ".join(_LETTER[char] for char in token)


def lexical_suggestions(text: str) -> list[Suggestion]:
    """Toponym, acronym, and foreign-word suggestions. ``text`` is unchanged."""
    occupied = bytearray(len(text))
    found: list[Suggestion] = []
    for pattern, spoken in _TOPONYM_RES:
        for match in pattern.finditer(text):
            _add(
                text,
                occupied,
                found,
                match.start(),
                match.end(),
                spoken,
                SuggestionCategory.TOPONYM,
                "toponym",
                0.92,
            )
    for match in _ACRONYM.finditer(text):
        token = match.group(0)
        if token in _NOT_ACRONYMS or token.casefold() in _ENGLISH_WORDS:
            continue
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            spell_acronym(token),
            SuggestionCategory.ACRONYM,
            "acronym",
            0.86,
        )
    for match in _WORD.finditer(text):
        token = match.group(0)
        if len(token) < 3 or any(char in _POLISH for char in token):
            continue
        folded = token.casefold()
        listed = folded in _ENGLISH_WORDS
        if not listed and _EN_ORTH.search(folded) is None:
            continue
        spoken = _spoken_foreign(token)
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            spoken,
            SuggestionCategory.FOREIGN_WORD,
            "english_word" if listed else "english_orthography",
            0.8 if spoken.casefold() != folded else 0.62,
        )
    found.sort(key=lambda item: (item.start, item.end, item.kind))
    return found


def _spoken_foreign(token: str) -> str:
    folded = token.casefold()
    override = _FOREIGN_SPOKEN.get(folded)
    if override is not None:
        return override
    spoken = folded
    for source, target in _RESPELL:
        spoken = spoken.replace(source, target)
    if token[:1].isupper() and spoken:
        spoken = spoken[:1].upper() + spoken[1:]
    return spoken


def _add(
    text: str,
    occupied: bytearray,
    found: list[Suggestion],
    start: int,
    end: int,
    replacement: str,
    kind: str,
    reason: str,
    confidence: float,
) -> None:
    if end <= start or any(occupied[start:end]):
        return
    occupied[start:end] = b"\x01" * (end - start)
    found.append(
        make_suggestion(
            text=text,
            start=start,
            end=end,
            replacement=replacement,
            kind=kind,
            reason=reason,
            confidence=confidence,
        )
    )
