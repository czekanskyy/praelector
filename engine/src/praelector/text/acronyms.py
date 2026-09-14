# SPDX-License-Identifier: Apache-2.0
"""Acronym detection and phonetic readout generation (AI-02, AI-08).

Detects 2-5 uppercase letter sequences, suppresses Roman numerals and common words,
and proposes Polish phonetic spoken forms (e.g. IT -> aj ti, SMS -> es em es).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praelector.text.numerals_pl import roman_to_int


@dataclass(frozen=True)
class AcronymMatch:
    """A detected acronym match in text."""

    start: int
    end: int
    original: str
    proposed: str
    category: str = "acronym"
    rationale: str = ""
    confidence: float = 0.90


# Special pronunciations for common international and Polish acronyms
ACRONYM_PRONUNCIATION_TABLE: dict[str, str] = {
    # English / tech
    "IT": "aj ti",
    "TV": "ti wi",
    "DJ": "di dżej",
    "PR": "pi ar",
    "AI": "ej aj",
    "UI": "ju aj",
    "UX": "ju eks",
    "IQ": "aj kju",
    "VIP": "wi aj pi",
    "PC": "pi si",
    "VR": "wi ar",
    "AR": "ej ar",
    "FAQ": "fak",
    "PDF": "pe de ef",
    "USB": "u es be",
    "GPS": "dżi pi es",
    "SIM": "sim",
    "PIN": "pin",
    "LED": "led",
    "OLED": "oled",
    "LCD": "el ce de",
    "HTML": "ha te em el",
    "CSS": "ce es es",
    "SQL": "es kju el",
    "API": "a pe i",
    "SDK": "es de ka",
    "URL": "u er el",
    "ID": "aj di",
    "OS": "o es",
    # Organizations / Politics
    "USA": "u es a",
    "UE": "u e",
    "ONZ": "o en zet",
    "NATO": "nato",
    "NASA": "nasa",
    "WHO": "wu ha o",
    "UNESCO": "junesko",
    "FBI": "ef bi aj",
    "CIA": "si aj ej",
    "KGB": "ka gie be",
    "MI6": "em aj siks",
    "BBC": "bi bi si",
    "CNN": "si en en",
    # Polish institutions
    "SMS": "es em es",
    "MMS": "em em es",
    "NIP": "nip",
    "PESEL": "pesel",
    "REGON": "regon",
    "ZUS": "zus",
    "US": "u es",
    "PIT": "pit",
    "CIT": "cit",
    "VAT": "wat",
    "NBP": "en be pe",
    "KNF": "ka en ef",
    "GOPR": "gopr",
    "WOPR": "wopr",
    "TOPR": "topr",
    "PKP": "pe ka pe",
    "PKO": "pe ka o",
    "PKS": "pe ka es",
    "CBA": "ce be a",
    "CBŚ": "ce be eś",
    "ABW": "a be wu",
    "BOR": "bor",
    "SOP": "sop",
    "NFZ": "en ef zet",
    "MZ": "em zet",
    "MEN": "men",
    "MON": "mon",
    "MSZ": "em es zet",
    "MSWiA": "em es wu i a",
    "UW": "u wu",
    "UJ": "u jot",
    "PW": "pe wu",
    "AGH": "a gie ha",
    "KUL": "kul",
    "UAM": "u a em",
    "UWr": "u wu er",
}

# Polish letter spoken names for spelling out acronyms
POLISH_LETTER_NAMES: dict[str, str] = {
    "A": "a",
    "B": "be",
    "C": "ce",
    "D": "de",
    "E": "e",
    "F": "ef",
    "G": "gie",
    "H": "ha",
    "I": "i",
    "J": "jot",
    "K": "ka",
    "L": "el",
    "M": "em",
    "N": "en",
    "O": "o",
    "P": "pe",
    "Q": "ku",
    "R": "er",
    "S": "es",
    "T": "te",
    "U": "u",
    "V": "fał",
    "W": "wu",
    "X": "iks",
    "Y": "igrek",
    "Z": "zet",
}

# Common Polish all-caps words to avoid treating as acronyms
COMMON_WORDS_TO_SKIP: set[str] = {
    "NIE",
    "TAK",
    "ALE",
    "LUB",
    "CZY",
    "ORAZ",
    "LECZ",
    "DLA",
    "NAD",
    "POD",
    "PRZED",
    "POZA",
    "BEZ",
    "PRZY",
    "PRZEZ",
    "MIĘDZY",
    "JEJ",
    "JEGO",
    "ICH",
    "NAS",
    "WAS",
    "ONI",
    "ONE",
    "PAN",
    "PANI",
    "JEST",
    "BĘDZIE",
    "BYŁO",
    "BYŁA",
    "BYŁ",
    "JAK",
    "GDY",
    "TAM",
    "TU",
    "JUŻ",
    "CO",
    "KTO",
    "TO",
    "TEN",
    "TA",
    "TE",
    "TYCH",
    "TYM",
}

RE_ACRONYM = re.compile(r"\b([A-Z]{2,5})\b")


def spell_acronym_pl(acronym: str) -> str:
    """Generate Polish letter-by-letter spoken form for an acronym."""
    upper = acronym.upper()
    if upper in ACRONYM_PRONUNCIATION_TABLE:
        return ACRONYM_PRONUNCIATION_TABLE[upper]

    letters = [POLISH_LETTER_NAMES.get(c, c.lower()) for c in upper]
    return " ".join(letters)


def detect_acronyms(text: str) -> list[AcronymMatch]:
    """Detect uppercase acronyms in text and return proposed spoken forms."""
    matches: list[AcronymMatch] = []

    for m in RE_ACRONYM.finditer(text):
        token = m.group(1)

        # Skip if it is a valid Roman numeral (e.g. IV, VI, XIV)
        if roman_to_int(token) is not None:
            continue

        # Skip common capitalized words
        if token in COMMON_WORDS_TO_SKIP:
            continue

        spoken = spell_acronym_pl(token)
        matches.append(
            AcronymMatch(
                start=m.start(),
                end=m.end(),
                original=token,
                proposed=spoken,
                category="acronym",
                rationale=f"Acronym pronunciation: {token} -> {spoken}",
                confidence=0.90,
            )
        )

    return matches
